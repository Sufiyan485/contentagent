import json
from copy import deepcopy
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from backend.app.config import Settings
from backend.tests.app_fixture import create_app
from backend.app.services.providers import ProviderError


class DistinctText:
    def __init__(self):
        self.calls = 0
    def generate(self, prompt, *args):
        self.calls += 1
        request = json.JSONDecoder().raw_decode(prompt.split('\n',1)[1])[0]['request']
        platform = request['platforms'][0]
        return {'concepts': [{'title':f'Concept {i}', 'background_design':f'{platform} distinct scene {i}',
            'captions':[{'platform':platform,'text':'Learn from data (c1).','claim_ids':['c1'],'hashtags':['#Data','#Learning','#Research']}],
            'slides':[{'headline':f'{platform} insight {i} (c1)', 'body':'Models learn from data [c1].', 'cta':'Explore (c1)', 'layout':'educational','claim_ids':['c1']} for _ in range(request['slide_count'])]}
            for i in range(request['concept_count'])]}


@pytest.mark.parametrize('concepts,slides', [(1,1),(2,2),(3,5)])
def test_distinct_creatives_retry_edit_restart(tmp_path, concepts, slides):
    settings=Settings(_env_file=None,app_data_dir=tmp_path,content_api_key='',pollinations_api_key='')
    app=create_app(settings,start_worker=False)
    fixture=DistinctText()
    with TestClient(app) as client:
        app.state.workflow.agent.text_service=fixture
        report=next(r for r in client.get('/api/v1/research-reports').json() if r['id'].endswith('001'))
        request={'topic':report['topic'],'report_id':report['id'],'creative_mode':'distinct_platforms',
            'concept_count':concepts,'slide_count':slides,'platforms':['instagram','facebook','linkedin'],'artwork_mode':'application_gradient'}
        actual=app.state.workflow.artwork.generate
        def artwork_failure(req,concept,seed):
            if concept.background_design.startswith('facebook'):
                raise ProviderError('Explicit fixture artwork failure')
            return actual(req,concept,seed)
        app.state.workflow.artwork.generate=artwork_failure
        job=client.post('/api/v1/generation-jobs',json=request,headers={'Idempotency-Key':str(uuid4())}).json()['id']
        app.state.workflow.run(job)
        assert client.get(f'/api/v1/generation-jobs/{job}').json()['status']=='partial'
        partial=client.get('/api/v1/content').json()['items']
        assert len(partial)==concepts
        assert all(set(i['platform_backgrounds'])=={'instagram','linkedin'} for i in partial)
        app.state.workflow.artwork.generate=actual
        retry=client.post(f'/api/v1/generation-jobs/{job}/retry',json={}).json()['id']
        app.state.workflow.run(retry)
        assert client.get(f'/api/v1/generation-jobs/{retry}').json()['status']=='succeeded'
        assert fixture.calls==3*concepts
        saved=client.get('/api/v1/content').json()['items']
        for item in saved:
            assert all(any(w.startswith(platform+' caption has') for w in item['concept']['warnings']) for platform in ('instagram','facebook','linkedin'))
            old=next(i for i in partial if i['id']==item['id'])
            assert len(set(item['platform_backgrounds'].values()))==3
            assert len(item['renders'])==slides*3
            assert item['platform_exports']['instagram']==old['platform_exports']['instagram']
            for platform,export in item['platform_exports'].items():
                assert export['background_asset_id']==item['platform_backgrounds'][platform]
                for image in export['renders']:
                    assert app.state.workflow.assets.metadata(image)['background_asset_id']==item['platform_backgrounds'][platform]
                variant=item['concept']['platform_variants'][platform]
                assert platform in variant['slides'][0]['headline']
                assert '(c1)' not in variant['slides'][0]['headline']
                assert '[c1]' not in variant['slides'][0]['body']
                assert variant['slides'][0]['claim_ids']==['c1']
        selected=saved[0]
        edited=deepcopy(selected['concept'])
        edited['platform_variants']['facebook']['slides'][0]['headline']='Changed Facebook only'
        revision=client.post(f"/api/v1/content/{selected['id']}/revisions",json={'base_version_id':selected['version_id'],'concept':edited}).json()['id']
        app.state.workflow.run(revision)
        assert client.get(f'/api/v1/generation-jobs/{revision}').json()['status']=='succeeded'
        history=client.get(f"/api/v1/content/{selected['id']}/versions").json()
        assert history[1]==selected
        assert history[0]['platform_backgrounds']==selected['platform_backgrounds']
        assert fixture.calls==3*concepts
    with TestClient(create_app(settings,start_worker=False)) as client:
        assert client.get(f"/api/v1/content/{selected['id']}/versions").json()==history

@pytest.mark.parametrize('scene', ['A notebook with handwritten notes', 'A brass barometer on a desk'])
def test_text_prone_scene_is_rejected_before_artwork(tmp_path, scene):
    from backend.app.agents.content import ContentCreationAgent
    from backend.app.contracts import GenerationRequest, ResearchReport
    settings=Settings(_env_file=None,app_data_dir=tmp_path)
    with TestClient(create_app(settings,start_worker=False)) as client:
        report=ResearchReport.model_validate(next(r for r in client.get('/api/v1/research-reports').json() if r['id'].endswith('001')))
        class UnsafeText(DistinctText):
            def generate(self,prompt,*args):
                batch=super().generate(prompt,*args)
                for concept in batch['concepts']:
                    concept['background_design']=scene
                return batch
        fixture=UnsafeText()
        with pytest.raises(ProviderError,match='validation'):
            ContentCreationAgent(fixture).generate(GenerationRequest(topic='Fixture',report_id=report.id),report,'groq','fixture')
        assert fixture.calls==2


def test_distinct_text_checkpoint_survives_provider_failure(tmp_path):
    settings=Settings(_env_file=None,app_data_dir=tmp_path,content_api_key='',pollinations_api_key='')
    app=create_app(settings,start_worker=False)
    attempts=[]
    class FlakyText(DistinctText):
        def generate(self,prompt,*args):
            platform=json.JSONDecoder().raw_decode(prompt.split('\n',1)[1])[0]['request']['platforms'][0]
            attempts.append(platform)
            if platform=='facebook' and attempts.count(platform)==1:
                raise ProviderError('Explicit text fixture failure')
            return super().generate(prompt,*args)
    with TestClient(app) as client:
        app.state.workflow.agent.text_service=FlakyText()
        report=next(r for r in client.get('/api/v1/research-reports').json() if r['id'].endswith('001'))
        job=client.post('/api/v1/generation-jobs',json={'topic':'Fixture','report_id':report['id'],
            'creative_mode':'distinct_platforms','platforms':['instagram','facebook']},headers={'Idempotency-Key':str(uuid4())}).json()['id']
        app.state.workflow.run(job)
        assert client.get(f'/api/v1/generation-jobs/{job}').json()['status']=='failed'
        retry=client.post(f'/api/v1/generation-jobs/{job}/retry',json={}).json()['id']
        app.state.workflow.run(retry)
        assert attempts==['instagram','facebook','facebook']
        assert client.get(f'/api/v1/generation-jobs/{retry}').json()['status']=='partial'  # No artwork credential; no fallback.
