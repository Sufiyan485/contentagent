import json
import time
from copy import deepcopy
from uuid import uuid4
import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from backend.app.config import Settings
from backend.app.contracts import GeneratedBatch, ResearchReport
from backend.app.models import GenerationJob
from backend.app.services.providers import TextService, ProviderError, ProviderDeferred, reset_seconds
from backend.app.services.text_budget import compact_report, compact_schema, completion_budget
from backend.tests.app_fixture import create_app
from backend.tests.test_distinct_creatives import DistinctText


def test_compaction_preserves_evidence_and_constraints(tmp_path):
    app=create_app(Settings(_env_file=None,app_data_dir=tmp_path),start_worker=False)
    with TestClient(app) as client:
        report=ResearchReport.model_validate(client.get('/api/v1/research-reports').json()[0])
        original=report.model_dump(mode='json')
        compact=compact_report(report)
        assert report.model_dump(mode='json')==original
        for old,new in zip(original['claims'],compact['claims']):
            assert all(old[key]==new[key] for key in ('id','text','verification_status','limitations'))
            assert [compact['evidence_passages'][i] for i in new['evidence_refs']]==[{k:v for k,v in e.items() if v is not None} for e in old['evidence']]
        schema=compact_schema(GeneratedBatch.model_json_schema())
        assert 'platform_variants' not in schema['$defs']['GeneratedConcept']['properties']
        assert schema['$defs']['SlideText']['properties']['headline']['maxLength']==160
        assert len(json.dumps(schema))<len(json.dumps(GeneratedBatch.model_json_schema()))


def test_http_errors_waits_and_groq_budget():
    calls=[]
    def respond(request):
        calls.append(json.loads(request.content))
        return httpx.Response(429,headers={'retry-after':'41.43'},json={'error':{'message':'SECRET'}})
    service=TextService(Settings(_env_file=None,content_api_key='secret'),httpx.MockTransport(respond))
    service.defer_retries=True
    prompt='Instructions\n'+json.dumps({'request':{'slide_count':1,'concept_count':1,'platforms':['instagram'],'caption_length':'balanced'}})
    with pytest.raises(ProviderDeferred) as error: service.generate(prompt,'groq','openai/gpt-oss-120b')
    assert 41<error.value.seconds<44 and 'SECRET' not in str(error.value)
    assert len(calls)==1 and calls[0]['reasoning_effort']=='low'
    assert calls[0]['max_completion_tokens']<6000
    assert completion_budget(prompt)<completion_budget(prompt.replace('"slide_count": 1','"slide_count": 5'))
    service.groq_blocked_until=0
    service.transport=httpx.MockTransport(lambda _:httpx.Response(413,text='SECRET'))
    with pytest.raises(ProviderError,match='too large'): service.generate(prompt,'groq','openai/gpt-oss-120b')
    assert reset_seconds('1m26.4s')==86.4
    assert reset_seconds('200ms')==.2
    assert reset_seconds('nan') is None


def test_success_headers_pace_next_call():
    calls=[]
    def respond(request):
        calls.append(request)
        return httpx.Response(200,headers={'x-ratelimit-remaining-tokens':'100','x-ratelimit-reset-tokens':'41s'},json={'choices':[{'finish_reason':'stop','message':{'content':'{}'}}]})
    service=TextService(Settings(_env_file=None,content_api_key='secret'),httpx.MockTransport(respond))
    service.defer_retries=True
    assert service.generate('fixture','groq','openai/gpt-oss-120b')=={}
    with pytest.raises(ProviderDeferred): service.generate('fixture','groq','openai/gpt-oss-120b')
    assert len(calls)==1


def test_wait_restart_resume_and_concept_checkpoints(tmp_path):
    settings=Settings(_env_file=None,app_data_dir=tmp_path)
    app=create_app(settings,start_worker=False)
    class Interrupted(DistinctText):
        def generate(self,*args):
            if self.calls==1: raise ProviderDeferred(42,throttled=True)
            return super().generate(*args)
    with TestClient(app) as client:
        report=client.get('/api/v1/research-reports').json()[0]
        job=client.post('/api/v1/generation-jobs',json={'topic':report['topic'],'report_id':report['id'],'concept_count':3,'creative_mode':'distinct_platforms','slide_count':1,'artwork_mode':'application_gradient'},headers={'Idempotency-Key':str(uuid4())}).json()['id']
        fixture=Interrupted();app.state.workflow.agent.text_service=fixture
        app.state.workflow.run(job)
        view=client.get('/api/v1/generation-jobs/'+job).json()
        assert view['status']=='queued' and view['stages'][-1]['status']=='waiting'
        with Session(app.state.engine) as db:
            row=db.get(GenerationJob,job)
            assert len(row.checkpoint['text_parts']['instagram'])==1
            saved=deepcopy(row.checkpoint['text_parts'])
        app.state.workflow.run(job)
        assert fixture.calls==1  # Early dispatch cannot ignore the deadline.
    app=create_app(settings,start_worker=False)
    with TestClient(app) as client:
        with Session(app.state.engine) as db:
            row=db.get(GenerationJob,job)
            assert row.checkpoint['text_parts']==saved
            row.checkpoint={**row.checkpoint,'provider_resume_at':time.time()-1};db.commit()
        fixture=DistinctText();app.state.workflow.agent.text_service=fixture
        app.state.workflow.run(job)
        assert fixture.calls==2
        assert client.get('/api/v1/generation-jobs/'+job).json()['status']=='succeeded'
        assert client.get('/api/v1/content').json()['total']==3



def test_correction_survives_capacity_wait(tmp_path):
    app=create_app(Settings(_env_file=None,app_data_dir=tmp_path),start_worker=False)
    class Corrected(DistinctText):
        attempt=0
        def generate(self,prompt,*args):
            self.attempt+=1
            if self.attempt==2: raise ProviderDeferred(42)
            result=super().generate(prompt,*args)
            if self.attempt==1: result['concepts'][0]['captions'][0]['hashtags']=[]
            if self.attempt==3: assert 'Previous response failed validation' in prompt
            return result
    with TestClient(app) as client:
        report=client.get('/api/v1/research-reports').json()[0]
        job=client.post('/api/v1/generation-jobs',json={'topic':report['topic'],'report_id':report['id'],'artwork_mode':'application_gradient'},headers={'Idempotency-Key':str(uuid4())}).json()['id']
        fixture=Corrected();app.state.workflow.agent.text_service=fixture
        app.state.workflow.run(job)
        with Session(app.state.engine) as db:
            row=db.get(GenerationJob,job)
            assert 'Wrong hashtag count' in row.checkpoint['text_correction']
            row.checkpoint={**row.checkpoint,'provider_resume_at':time.time()-1};db.commit()
        app.state.workflow.run(job)
        assert client.get('/api/v1/generation-jobs/'+job).json()['status']=='succeeded'
        assert fixture.attempt==3


def test_quota_exhaustion_is_not_retried():
    service=TextService(Settings(_env_file=None,content_api_key='secret'),httpx.MockTransport(lambda _:httpx.Response(429,json={'error':{'code':'rate_limit_exceeded','message':'tokens per day (TPD) SECRET'}})))
    service.defer_retries=True
    with pytest.raises(ProviderError,match='daily allowance') as error: service.generate('fixture','groq','openai/gpt-oss-120b')
    assert not isinstance(error.value,ProviderDeferred) and 'SECRET' not in str(error.value)
