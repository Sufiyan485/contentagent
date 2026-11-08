from pathlib import Path
D=Path(__file__).resolve().parent
def write(name,text):
 p=D/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(text,encoding='utf-8')
# Freeze schema operations from the reviewed migrations rather than tying revision to future ORM metadata.
import ast
S=Path(r'D:\Projects\AI_Social_Media')
def upgrade_body(name):
 text=(S/'backend/migrations/versions'/name).read_text();node=next(n for n in ast.parse(text).body if isinstance(n,ast.FunctionDef) and n.name=='upgrade')
 return '\n'.join(text.splitlines()[node.body[0].lineno-1:node.end_lineno])
migration='''"""Initial frozen standalone schema derived from original content migrations."""
from alembic import op
import sqlalchemy as sa
revision = 'content_0001'
down_revision = None
branch_labels = None
depends_on = None

def upgrade():
'''+upgrade_body('0001_foundation.py')+'\n'+upgrade_body('0002_content_workflow.py')+'\n'+upgrade_body('0003_immutable_versions.py')+'''
    op.add_column('content_items', sa.Column('trashed_at', sa.String(40), nullable=True))
    op.create_index('ix_content_items_trashed_at', 'content_items', ['trashed_at'])
    op.add_column('content_items', sa.Column('deleted_at', sa.String(40), nullable=True))
    op.execute('DROP TRIGGER content_versions_no_delete')
    op.execute("CREATE TRIGGER content_versions_no_delete BEFORE DELETE ON content_versions WHEN NOT EXISTS (SELECT 1 FROM content_items WHERE id=OLD.item_id AND trashed_at IS NOT NULL AND deleted_at IS NOT NULL) BEGIN SELECT RAISE(ABORT, 'Content versions are immutable'); END")

def downgrade():
    raise RuntimeError('Destructive downgrade is not supported; choose a fresh standalone data directory.')
'''
write('backend/migrations/versions/0001_content_standalone.py',migration)
write('backend/tests/test_standalone.py', '''"""Standalone boundary tests; synthetic fixture input, no external services."""
from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys
from uuid import uuid4
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import inspect, text
from sqlalchemy.orm import Session
from backend.app.config import ROOT, Settings
from backend.app.main import create_app
from backend.app.contracts import ResearchReport, GenerationRequest
from backend.app.models import ResearchRun, GenerationJob
from backend.app.workflow import JobRunner
from backend.tests.test_distinct_creatives import DistinctText

def synthetic_report():
    data=json.loads((ROOT/'tests/fixtures/reports/01-machine-learning.json').read_text())
    # This is an explicitly synthetic test of an incoming live-report contract.
    data.update(id=str(uuid4()), origin='live', researched_at=data['prepared_at'])
    data['warnings'].append('SYNTHETIC OFFLINE ACCEPTANCE FIXTURE; no research was performed.')
    return data

def test_storage_and_environment_are_isolated(tmp_path,monkeypatch):
    monkeypatch.setenv('APP_DATA_DIR',str(tmp_path/'own-data'))
    monkeypatch.setenv('CONTENT_API_KEY','synthetic-test-value')
    settings=Settings(_env_file=None)
    assert settings.data_dir==tmp_path/'own-data'
    assert settings.content_api_key.get_secret_value()=='synthetic-test-value'
    assert 'synthetic-test-value' not in repr(settings)
    for path in [ROOT,ROOT.parent/'outside',Path(r'D:\\Projects\\AI_Social_Media\\data')]:
        with pytest.raises(ValueError,match='subdirectory'):
            _=Settings(_env_file=None,app_data_dir=path).data_dir
    # A directory symlink/junction must not escape the copy after resolution.
    import os
    link=tmp_path/'escape'
    result=subprocess.run(['cmd','/c','mklink','/J',str(link),str(ROOT.parent)],capture_output=True,text=True)
    assert result.returncode==0,result.stderr
    try:
        with pytest.raises(ValueError,match='subdirectory'):
            _=Settings(_env_file=None,app_data_dir=link/'data').data_dir
    finally:
        os.rmdir(link)  # Removes only the junction entry, never its target.

def test_contracts_and_normal_startup_do_not_seed_demo(tmp_path):
    with TestClient(create_app(Settings(_env_file=None,app_data_dir=tmp_path),start_worker=False)) as client:
        assert client.get('/api/v1/research-reports').json()==[]
        demo=json.loads((ROOT/'tests/fixtures/reports/01-machine-learning.json').read_text())
        assert client.post('/api/v1/research-reports',json=demo).status_code==409
        schema=client.get('/openapi.json').json()
        assert schema['info']['title']=='Standalone Content Creation Agent'
        assert not any(any(x in route for x in ('publishing','approvals','social/','coordinate','research-jobs','trash','delete-permanently')) for route in schema['paths'])
        assert not hasattr(client.app.state,'research_workflow')
        tables=set(inspect(client.app.state.engine).get_table_names())
        assert tables=={'alembic_version','campaigns','research_runs','generation_jobs','assets','content_items','content_versions'}
        assert client.post('/api/v1/research-reports',json={'topic':'invalid'}).status_code==422
        with pytest.raises(ValidationError): GenerationRequest(topic='bad',report_id=uuid4(),concept_count=4)
        with pytest.raises(ValidationError): GenerationRequest(topic='bad',report_id=uuid4(),slide_count=6)
        broken=synthetic_report();broken['claims'][0]['evidence'][0]['source_id']='missing'
        with pytest.raises(ValidationError): ResearchReport.model_validate(broken)
        assert client.post('/api/v1/research-reports',json=broken).status_code==422

def test_live_input_campaign_context_restore_and_fresh_process(tmp_path):
    settings=Settings(_env_file=None,app_data_dir=tmp_path,content_api_key='',pollinations_api_key='')
    with TestClient(create_app(settings,start_worker=False)) as c:
        report=synthetic_report()
        assert c.post('/api/v1/research-reports',json=report).status_code==201
        assert c.post('/api/v1/research-reports',json=report).status_code==201
        changed=deepcopy(report);changed['summary']='Changed'
        assert c.post('/api/v1/research-reports',json=changed).status_code==409
        campaign=c.post('/api/v1/campaign-contexts',json={'name':'Synthetic context','objective':'Explain source-grounded ideas','audience':'Engineers','platforms':['instagram'],'approved_facts':['This is an offline test.']}).json()
        c.app.state.workflow.agent.text_service=DistinctText()
        payload={'topic':report['topic'],'report_id':report['id'],'campaign_id':campaign['id'],'slide_count':2,'artwork_mode':'application_gradient'}
        response=c.post('/api/v1/generation-jobs',json=payload,headers={'Idempotency-Key':str(uuid4())})
        assert response.status_code==202,response.text
        job=response.json()['id'];c.app.state.workflow.run(job)
        assert c.get('/api/v1/generation-jobs/'+job).json()['status']=='succeeded'
        item=c.get('/api/v1/content').json()['items'][0]
        assert item['request']['audience']=='Engineers'
        assert item['approval_status']=='unapproved' and item['publishing_status']=='not_published'
        revision=c.post('/api/v1/content/'+item['id']+'/revisions',json={'base_version_id':item['version_id'],'concept':item['concept'],'template_id':'bulletin-v1'}).json()['id']
        c.app.state.workflow.run(revision)
        current=c.get('/api/v1/content/'+item['id']).json()
        body={'base_version_id':current['version_id']};headers={'Idempotency-Key':str(uuid4())}
        restored=c.post(f"/api/v1/content/{item['id']}/versions/{item['version_id']}/restore",json=body,headers=headers)
        assert restored.status_code==200,restored.text
        assert c.post(f"/api/v1/content/{item['id']}/versions/{item['version_id']}/restore",json=body,headers=headers).json()==restored.json()
        final=c.get('/api/v1/content/'+item['id']).json()
        assert final['version_number']==3 and final['background']==item['background']
        assert final['approval_status']=='unapproved'
        expected={'item':final,'report':report}
    code="""import json,sys
from fastapi.testclient import TestClient
from backend.app.config import Settings
from backend.app.main import create_app
with TestClient(create_app(Settings(_env_file=None,app_data_dir=sys.argv[1]),start_worker=False)) as c:
 print(json.dumps({'item':c.get('/api/v1/content/'+sys.argv[2]).json(),'report':c.get('/api/v1/research-reports/'+sys.argv[3]).json()}))
"""
    result=subprocess.run([sys.executable,'-B','-c',code,str(tmp_path),item['id'],report['id']],cwd=ROOT,capture_output=True,text=True,check=True)
    assert json.loads(result.stdout)==expected

def test_worker_marks_interrupted_jobs_and_keeps_checkpoint(tmp_path):
    with TestClient(create_app(Settings(_env_file=None,app_data_dir=tmp_path),start_worker=False)) as c:
        report=synthetic_report();c.post('/api/v1/research-reports',json=report)
        job=c.post('/api/v1/generation-jobs',json={'topic':report['topic'],'report_id':report['id']},headers={'Idempotency-Key':str(uuid4())}).json()['id']
        with Session(c.app.state.engine) as db:
            row=db.get(GenerationJob,job);row.status='running';row.checkpoint={'text_parts':{'shared':[{'saved':'explicit fixture'}]}};db.commit()
        runner=JobRunner(c.app.state.workflow);runner.start();runner.close();runner.thread.join()
        with Session(c.app.state.engine) as db:
            row=db.get(GenerationJob,job)
            assert row.status=='interrupted' and row.checkpoint['text_parts']['shared'][0]['saved']=='explicit fixture'
''')
print('Frozen standalone migration and additional boundary/restart acceptance tests written.')
