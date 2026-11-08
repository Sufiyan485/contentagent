from pathlib import Path
import json, ast
D=Path(__file__).resolve().parent
S=Path(r'D:\Projects\AI_Social_Media')
def write(name,text):
 p=D/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(text,encoding='utf-8')
write('backend/app/main.py', '''"""Standalone content host. No research, approval or publishing workers."""
from contextlib import asynccontextmanager
from uuid import uuid4, UUID
from fastapi import FastAPI, Request, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.middleware.cors import CORSMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware
from sqlalchemy import select
from sqlalchemy.orm import Session
from .config import Settings
from .database import make_engine, migrate
from .contracts import ResearchReport, CampaignInput
from .models import ResearchRun, Campaign
from .workflow import ContentWorkflow, JobRunner
from .content_api import router
from .services.data_lock import DataDirectoryLock
from .services.local_security import is_local_client, forbidden_browser_request, protect_response

def create_app(settings=None, *, start_worker=True, include_demo_reports=False):
    settings=settings or Settings()
    @asynccontextmanager
    async def lifespan(app):
        with DataDirectoryLock(settings.data_dir):
            engine=make_engine(settings)
            migrate(engine)
            app.state.settings=settings
            app.state.engine=engine
            app.state.include_demo_reports=include_demo_reports
            app.state.workflow=ContentWorkflow(engine,settings)
            worker=JobRunner(app.state.workflow)
            try:
                if start_worker: worker.start()
                yield
            finally:
                if start_worker:
                    worker.close()
                    worker.thread.join()
                engine.dispose()
    app=FastAPI(title='Standalone Content Creation Agent',version='1.0.0',lifespan=lifespan)
    app.add_middleware(CORSMiddleware,allow_origins=settings.app_allowed_origins,allow_methods=['GET','POST','PATCH'],allow_headers=['Content-Type','Idempotency-Key'])
    app.add_middleware(TrustedHostMiddleware,allowed_hosts=['localhost','127.0.0.1','testserver'])
    def error(status,code,message,details=None):
        return JSONResponse(status_code=status,content={'error':{'code':code,'message':message,'details':details,'retryable':False}})
    @app.middleware('http')
    async def boundary(request:Request,call_next):
        request.state.request_id=str(uuid4())
        if not request.client or not is_local_client(request.client.host):
            return error(403,'local_access_required','Available only on this computer.')
        if forbidden_browser_request(request,settings.app_allowed_origins):
            return error(403,'origin_rejected','This origin is not allowed.')
        if request.method in {'POST','PATCH','PUT','DELETE'}:
            if request.headers.get('content-type','').split(';')[0]!='application/json':
                return error(415,'json_required','Use application/json.')
            chunks=[];size=0
            async for chunk in request.stream():
                size+=len(chunk)
                if size>128*1024: return error(413,'request_too_large','Request exceeds 128 KiB.')
                chunks.append(chunk)
            request._body=b''.join(chunks)
        try: response=await call_next(request)
        except Exception:
            return error(500,'internal_error','The request could not finish. Check local configuration.')
        return protect_response(request,response)
    @app.exception_handler(RequestValidationError)
    async def validation(request,exc):
        return error(422,'invalid_request','Check request fields.',[{'location':list(e['loc']),'type':e['type']} for e in exc.errors()])
    @app.get('/api/v1/health')
    def health(): return {'status':'ok','database':'ready','component':'content_only'}
    @app.post('/api/v1/research-reports',response_model=ResearchReport,status_code=201)
    def import_report(payload:ResearchReport):
        if payload.origin=='demo' and not include_demo_reports:
            raise HTTPException(409,'Demo reports are test fixtures only.')
        if payload.origin=='provided':
            raise HTTPException(409,'Submit a source-backed live report; supplied facts belong in approved_user_facts.')
        snapshot=payload.model_dump(mode='json')
        with Session(app.state.engine) as db:
            row=db.get(ResearchRun,str(payload.id))
            if row and row.snapshot!=snapshot: raise HTTPException(409,'Report ID already identifies a different immutable report.')
            if not row:
                db.add(ResearchRun(id=str(payload.id),origin=payload.origin,topic=payload.topic,snapshot=snapshot));db.commit()
        return payload
    @app.get('/api/v1/research-reports',response_model=list[ResearchReport])
    def reports():
        with Session(app.state.engine) as db:
            query=select(ResearchRun).order_by(ResearchRun.created_at,ResearchRun.id)
            if not include_demo_reports: query=query.where(ResearchRun.origin=='live')
            return [r.snapshot for r in db.scalars(query)]
    @app.post('/api/v1/campaign-contexts',status_code=201)
    def campaign_context(payload:CampaignInput):
        with Session(app.state.engine) as db:
            row=Campaign(name=payload.name,snapshot=payload.model_dump(mode='json'))
            db.add(row);db.commit();db.refresh(row)
            return {'id':row.id,**row.snapshot}
    app.include_router(router)
    return app

app=create_app()
''')
write('backend/tests/app_fixture.py','''"""Explicit test-only demo ingestion. Never imported by runtime startup."""
from contextlib import asynccontextmanager
from backend.app.main import create_app as application
from backend.app.config import ROOT
from backend.app.contracts import ResearchReport
from backend.app.models import ResearchRun
from sqlalchemy.orm import Session

def create_app(settings=None, *, start_worker=True):
    app=application(settings,start_worker=start_worker,include_demo_reports=True)
    original=app.router.lifespan_context
    @asynccontextmanager
    async def fixtures(app):
        async with original(app):
            with Session(app.state.engine) as db:
                for path in sorted((ROOT/'tests/fixtures/reports').glob('*.json')):
                    report=ResearchReport.model_validate_json(path.read_text(encoding='utf-8'))
                    if not db.get(ResearchRun,str(report.id)):
                        db.add(ResearchRun(id=str(report.id),origin='demo',topic=report.topic,snapshot=report.model_dump(mode='json')))
                db.commit()
            yield
    app.router.lifespan_context=fixtures
    return app
''')
# Adapt only excluded-app assertions and fixture locations, retaining content assertions.
p=D/'backend/tests/test_content.py';t=p.read_text();start=t.index('        path=f"/api/v1/content/');end=t.index('    with TestClient(create_app',start);t=t[:start]+t[end:];p.write_text(t,encoding='utf-8')
p=D/'backend/tests/test_natural_revision.py';t=p.read_text();start=t.index('        review=c.get(');end=t.index('        calls=[];',start);t=t[:start]+t[end:];start=t.index('        c.post(f"/api/v1/content/');end=t.index("\n\n\n@pytest.mark.parametrize",start);t=t[:start]+t[end:];t=t.replace('test_scope_assets_approval_retry_restart_and_purge','test_scope_assets_retry_and_restart');p.write_text(t,encoding='utf-8')
for p in (D/'backend/tests').glob('test_*.py'):
 t=p.read_text().replace("ROOT / 'demo_reports'","ROOT / 'tests/fixtures/reports'").replace("ROOT/'demo_reports'","ROOT/'tests/fixtures/reports'").replace("demo_reports/01-machine-learning.json","tests/fixtures/reports/01-machine-learning.json")
 p.write_text(t,encoding='utf-8')
# Per-process environment/cache paths remain inside this project.
write('tools/run_tests.ps1', '''$ErrorActionPreference = 'Stop'
$taskRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $taskRoot
$env:PYTHONDONTWRITEBYTECODE='1'
$env:TEMP=Join-Path $taskRoot '.cache/tmp'
$env:TMP=$env:TEMP
$env:PLAYWRIGHT_BROWSERS_PATH=Join-Path $taskRoot '.cache/ms-playwright'
$env:LANGSMITH_TRACING='false'
$env:LANGCHAIN_TRACING_V2='false'
$env:XDG_CACHE_HOME=Join-Path $taskRoot '.cache'
New-Item -ItemType Directory -Force -Path $env:TEMP | Out-Null
& '.\\.venv\\Scripts\\python.exe' -B -m pytest backend/tests --basetemp='.cache/pytest-tmp' -o cache_dir='.cache/pytest' @args
exit $LASTEXITCODE
''')
write('backend/tests/conftest.py', '''"""Prevent any unmocked internet access or inherited credentials in tests."""
import os
from pathlib import Path
import socket
import pytest
ROOT=Path(__file__).resolve().parents[2]
for name in list(os.environ):
    if name.endswith(('_API_KEY','_API_SECRET','_TOKEN')) or name.startswith(('CONTENT_','POLLINATIONS_','LANGSMITH_','LANGCHAIN_','RESEARCH_','SEARCH_','APP_DATA_DIR')):
        os.environ.pop(name,None)
os.environ['LANGSMITH_TRACING']='false'
os.environ['LANGCHAIN_TRACING_V2']='false'
os.environ['PLAYWRIGHT_BROWSERS_PATH']=str(ROOT/'.cache/ms-playwright')
@pytest.fixture(autouse=True)
def offline_sockets(monkeypatch):
    original=socket.socket.connect
    def checked(sock,address):
        if isinstance(address,tuple) and address[0] not in ('127.0.0.1','localhost','::1'):
            raise AssertionError('Unmocked external network access prohibited during extraction tests')
        return original(sock,address)
    monkeypatch.setattr(socket.socket,'connect',checked)
''')
pins={}
for line in (S/'backend/requirements.txt').read_text().splitlines():
 if '==' in line:
  name,version=line.strip().split('==');pins[name.lower()]=line.strip()
names=['fastapi','uvicorn','pydantic','pydantic-settings','sqlalchemy','alembic','httpx','playwright','langgraph','langsmith','pillow','rapidocr','onnxruntime']
write('requirements.txt','\n'.join(pins[n] for n in names)+'\n')
write('requirements-dev.txt','-r requirements.txt\n'+pins['pytest']+'\n')
write('.env.example','''# Content LLM only. Set an eligible free-tier provider/model and your own key.
CONTENT_PROVIDER=groq
CONTENT_MODEL=openai/gpt-oss-120b
CONTENT_API_KEY=
# Optional live artwork; extraction tests never call this service.
POLLINATIONS_API_KEY=
POLLINATIONS_MODEL=
# Existing application exclusions are used unless explicitly overridden.
# POLLINATIONS_NEGATIVE_PROMPT=
ARTWORK_MAX_ATTEMPTS=2
# Must resolve inside this independent project (relative to project root).
APP_DATA_DIR=data
# Optional JSON list of allowed localhost browser origins:
# APP_ALLOWED_ORIGINS=["http://127.0.0.1:8000","http://localhost:8000"]
LANGSMITH_TRACING=false
LANGCHAIN_TRACING_V2=false
''')
write('.gitignore','.venv/\n.env\ndata/\n.cache/\n__pycache__/\n*.pyc\n')
print('Created standalone host, narrowed API, test bootstrap, offline guards and dependency inputs.')

