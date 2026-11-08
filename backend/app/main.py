"""Standalone content host. No research, approval or publishing workers."""
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
