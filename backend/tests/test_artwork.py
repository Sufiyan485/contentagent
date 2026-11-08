from io import BytesIO
from uuid import uuid4
from types import SimpleNamespace

import httpx
import pytest
from PIL import Image, ImageDraw, ImageFont
from sqlalchemy import select
from sqlalchemy.orm import Session
from fastapi.testclient import TestClient

from backend.app.config import Settings
from backend.app.contracts import GenerationRequest, GeneratedConcept
from backend.app.database import make_engine, migrate
from backend.app.models import Asset
from backend.app.models import GenerationJob
from backend.tests.app_fixture import create_app
from backend.app.services.assets import AssetStore
from backend.app.services.artwork import ArtworkService, background_prompt
from backend.app.services.background_check import BackgroundTextCheck, evaluate_regions
from backend.app.services.providers import ProviderError


def png(lettering=False):
    image = Image.new('RGB', (1080,1080), 'white')
    if lettering:
        ImageDraw.Draw(image).text((70,400), 'UNWANTED TEXT 123', fill='black', font=ImageFont.load_default(size=70))
    data = BytesIO()
    image.save(data,format='PNG')
    return data.getvalue()


def concept():
    return GeneratedConcept(title='Cybersecurity',background_design='A polished physical padlock shielding a delicate glass sphere.', captions=[{'platform':'instagram','text':'Protect access.'}],slides=[{'headline':'Protect access','body':'Use multiple authentication factors.','layout':'educational'}])


@pytest.mark.parametrize('theme', ['light','dark','colorful'])
def test_concept_and_style_drive_prompt(theme):
    request=GenerationRequest(topic='DO NOT TYPE THIS TITLE',report_id=uuid4(),background_theme=theme,visual_style='Watercolor painting')
    prompt=background_prompt(request,concept(),'letters, numbers, logos')
    assert 'padlock' in prompt and 'Watercolor painting' in prompt
    assert 'DO NOT TYPE THIS TITLE' not in prompt
    assert 'letters, numbers, logos' in prompt
    assert 'translucent geometric shapes' not in prompt and 'deep navy' not in prompt


def test_local_detector_rejects_lettering_and_accepts_blank():
    detector=BackgroundTextCheck()
    assert detector.inspect(png(True))['status']=='rejected'
    assert detector.inspect(png())['status']=='no_text_detected'


def test_ocr_confidence_and_recognition_are_both_considered():
    empty=SimpleNamespace(txts=None,scores=None)
    assert evaluate_regions(SimpleNamespace(scores=[.55,.7]),empty)['status']=='no_text_detected'
    assert evaluate_regions(SimpleNamespace(scores=[.85]),empty)['status']=='rejected'
    assert evaluate_regions(SimpleNamespace(scores=[.7]),SimpleNamespace(txts=['ABC'],scores=[.9]))['status']=='rejected'


@pytest.mark.parametrize('always_reject', [False, True])
def test_rejected_backgrounds_never_become_carousel_assets(tmp_path,always_reject):
    settings=Settings(_env_file=None,app_data_dir=tmp_path,pollinations_api_key='test-only',pollinations_model='test-model',artwork_max_attempts=2)
    engine=make_engine(settings);migrate(engine)
    store=AssetStore(engine,settings)
    calls=[]
    def respond(request):
        calls.append(request)
        return httpx.Response(200,content=png())
    class Check:
        count=0
        def ready(self): pass
        def inspect(self,data):
            self.count+=1
            return {'status':'rejected' if always_reject or self.count==1 else 'no_text_detected','regions':1}
    service=ArtworkService(settings,store,httpx.MockTransport(respond),Check())
    request=GenerationRequest(topic='Security',report_id=uuid4(),background_theme='light')
    try:
        if always_reject:
            with pytest.raises(ProviderError,match='Background rejected'):
                service.generate(request,concept(),42)
        else:
            accepted=service.generate(request,concept(),42)
            assert store.metadata(accepted)['text_check']['status']=='no_text_detected'
        assert len(calls)==2
        assert [r.url.params['seed'] for r in calls]==['42','43']
        assert all('negative_prompt' not in r.url.params for r in calls)
        with Session(engine) as db:
            rows=list(db.scalars(select(Asset)))
            assert len(rows)==2 and rows[0].metadata_json['text_check']['status']=='rejected'
    finally:engine.dispose()


def test_unavailable_detector_stops_before_spending_credits(tmp_path):
    class Unavailable:
        def ready(self): raise ProviderError('OCR unavailable')
    settings=Settings(_env_file=None,app_data_dir=tmp_path,pollinations_api_key='test-only',pollinations_model='test-model')
    calls=[]
    transport=httpx.MockTransport(lambda r: calls.append(r))
    service=ArtworkService(settings,None,transport,Unavailable())
    with pytest.raises(ProviderError,match='OCR unavailable'):
        service.generate(GenerationRequest(topic='Test',report_id=uuid4()),concept(),1)
    assert calls==[]


def test_explicit_retry_after_rejection_changes_seed_without_losing_completed_work(tmp_path):
    app=create_app(Settings(_env_file=None,app_data_dir=tmp_path),start_worker=False)
    with TestClient(app) as client:
        report=client.get('/api/v1/research-reports').json()[0]
        job_id=client.post('/api/v1/generation-jobs',json={'topic':report['topic'],'report_id':report['id']},headers={'Idempotency-Key':str(uuid4())}).json()['id']
        with Session(app.state.engine) as db:
            row=db.get(GenerationJob,job_id)
            row.status='partial'
            row.checkpoint={'concepts':{'0':{'artwork_error':'Background rejected: possible lettering'},'1':{'background':'saved-background-id'}}}
            old_seed=row.snapshot['seed_id'];db.commit()
        retry=client.post(f'/api/v1/generation-jobs/{job_id}/retry',json={})
        assert retry.status_code==202
        with Session(app.state.engine) as db:
            row=db.get(GenerationJob,retry.json()['id'])
            assert row.snapshot['seed_id']!=old_seed
            assert row.checkpoint['concepts']['1']['background']=='saved-background-id'
