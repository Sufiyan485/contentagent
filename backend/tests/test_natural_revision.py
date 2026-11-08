from copy import deepcopy
import json
import pytest
from uuid import uuid4
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from backend.app.config import Settings
from backend.tests.app_fixture import create_app
from backend.app.models import GenerationJob
from backend.app.services.providers import ProviderError
from backend.tests.test_platform_exports import PlatformText


class RevisionTextFixture(PlatformText):
    revision_calls=0
    bad=False
    def generate(self,*args):
        data=json.JSONDecoder().raw_decode(args[0].split('\n',1)[1])[0]
        if data['schema']['title']!='TextPatch': return super().generate(*args)
        self.revision_calls+=1
        original=data['original'];captions=[];slides=[]
        for platform in data['caption_targets']:
            caption=deepcopy(next(c for c in original['captions'] if c['platform']==platform))
            caption['text']='A concise, source-grounded explanation.'
            if self.bad=='citation': caption['claim_ids']=['invented']
            captions.append(caption)
        for platform,number in data['slide_targets']:
            slide=deepcopy((original['slides'] if platform=='shared' else original['platform_variants'][platform]['slides'])[number-1])
            slide['headline']='A simpler explanation'
            slides.append({'platform':platform,'slide_number':number,'text':slide})
        if self.bad=='scope': captions.append(deepcopy(next(c for c in original['captions'] if c['platform']=='facebook')))
        return {'captions':captions,'slides':slides}


def seed(app,c,distinct=True):
    fixture=RevisionTextFixture();app.state.workflow.agent.text_service=fixture
    report=c.get('/api/v1/research-reports').json()[0]
    j=c.post('/api/v1/generation-jobs',json={'topic':report['topic'],'report_id':report['id'],'platforms':['instagram','facebook'],'slide_count':2,'creative_mode':'distinct_platforms' if distinct else 'shared','artwork_mode':'application_gradient'},headers={'Idempotency-Key':str(uuid4())}).json()['id']
    app.state.workflow.run(j)
    return c.get('/api/v1/content').json()['items'][0],fixture


def submit(c,item,**overrides):
    body={'base_version_id':item['version_id'],'instruction':'Make it shorter without adding facts.','scope':'captions','platforms':['instagram'],**overrides}
    headers={'Idempotency-Key':str(uuid4())}
    response=c.post(f"/api/v1/content/{item['id']}/natural-revisions",json=body,headers=headers)
    assert response.status_code==202,response.text
    assert c.post(f"/api/v1/content/{item['id']}/natural-revisions",json=body,headers=headers).json()['id']==response.json()['id']
    assert c.post(f"/api/v1/content/{item['id']}/natural-revisions",json={**body,'instruction':'Another instruction'},headers=headers).status_code==409
    return response.json()['id']


def test_scope_assets_retry_and_restart(tmp_path):
    settings=Settings(_env_file=None,app_data_dir=tmp_path)
    app=create_app(settings,start_worker=False)
    with TestClient(app) as c:
        original,fixture=seed(app,c)
        calls=[];render=app.state.workflow.renderer.render
        def tracked(*args,**kwargs): calls.append(kwargs.get('platform'));return render(*args,**kwargs)
        app.state.workflow.renderer.render=tracked
        def no_art(*args,**kwargs): raise AssertionError('Text revision must not generate artwork')
        app.state.workflow.artwork.generate=no_art
        job=submit(c,original);app.state.workflow.run(job)
        revised=c.get('/api/v1/content/'+original['id']).json()
        assert revised['version_number']==2 and revised['approval_status']=='unapproved'
        assert revised['platform_exports']==original['platform_exports'] and not calls
        assert revised['concept']['captions'][1]==original['concept']['captions'][1]
        assert revised['concept']['platform_variants']==original['concept']['platform_variants']
        assert fixture.revision_calls==1
        job=submit(c,revised,scope='slides',slide_number=2)
        def fail(*args,**kwargs): raise ProviderError('Explicit rendering failure fixture')
        app.state.workflow.renderer.render=fail
        app.state.workflow.run(job)
        assert c.get('/api/v1/generation-jobs/'+job).json()['status']=='partial'
        retried=c.post(f'/api/v1/generation-jobs/{job}/retry',json={}).json()['id']
        app.state.workflow.renderer.render=tracked
        app.state.workflow.run(retried)
        result=c.get('/api/v1/content/'+original['id']).json()
        assert c.get('/api/v1/generation-jobs/'+retried).json()['status']=='succeeded'
        assert calls==['instagram'] and fixture.revision_calls==2
        assert result['platform_backgrounds']==original['platform_backgrounds']
        assert result['platform_exports']['facebook']==original['platform_exports']['facebook']
        assert result['concept']['platform_variants']['instagram']['slides'][0]==original['concept']['platform_variants']['instagram']['slides'][0]
        assert result['concept']['platform_variants']['instagram']['slides'][1]['headline']=='A simpler explanation'
        history=c.get(f"/api/v1/content/{original['id']}/versions").json()
        assert history[-1]['concept']==original['concept']
    with TestClient(create_app(settings,start_worker=False)) as c:
        assert c.get('/api/v1/content/'+original['id']).json()==result



@pytest.mark.parametrize('bad',['citation','scope'])
def test_validation_failure_preserves_original_and_can_retry(tmp_path,bad):
    app=create_app(Settings(_env_file=None,app_data_dir=tmp_path),start_worker=False)
    with TestClient(app) as c:
        original,fixture=seed(app,c,distinct=False)
        url=f"/api/v1/content/{original['id']}/natural-revisions"
        base={'base_version_id':original['version_id'],'instruction':'Simplify this text','platforms':['instagram'],'scope':'slides'}
        assert c.post(url,json=base,headers={'Idempotency-Key':str(uuid4())}).status_code==422
        assert c.post(url,json={**base,'platforms':['linkedin']},headers={'Idempotency-Key':str(uuid4())}).status_code==422
        assert c.post(url,json={**base,'platforms':['instagram','facebook'],'slide_number':5},headers={'Idempotency-Key':str(uuid4())}).status_code==422
        fixture.bad=bad;job=submit(c,original);app.state.workflow.run(job)
        assert c.get('/api/v1/generation-jobs/'+job).json()['status']=='failed'
        assert c.get('/api/v1/content/'+original['id']).json()['version_id']==original['version_id']
        assert fixture.revision_calls==2
        fixture.bad=False;retry=c.post(f'/api/v1/generation-jobs/{job}/retry',json={}).json()['id'];app.state.workflow.run(retry)
        assert c.get('/api/v1/generation-jobs/'+retry).json()['status']=='succeeded'
        assert fixture.revision_calls==3
