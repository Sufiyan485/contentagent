from copy import deepcopy
from uuid import UUID, uuid4
from datetime import date, datetime, time, timezone
from typing import Literal

from fastapi import APIRouter, Header, HTTPException, Query, Request
from fastapi.responses import Response
from sqlalchemy import func, select, or_, exists
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .contracts import ContentTrashState, GeneratedBatch, GenerationRequest, JobView, JobPage, JobSummary, JobStatus, ResearchReport, RetryRequest, RevisionRequest, TemplateView, PlatformPreset
from .agents.revision import NaturalRevisionRequest
from .templates.platforms import PRESETS
from .templates import TEMPLATES
from .models import Campaign, ContentItem, ContentVersion, GenerationJob, ResearchRun, now_iso
from .services.providers import ProviderError
from .workflow import digest
from .contracts import Contract
from threading import BoundedSemaphore
from pydantic import Field

preview_slots=BoundedSemaphore(2)


class PosterPreviewRequest(RevisionRequest):
    platform: Literal['instagram','facebook','linkedin']
    slide_index: int = Field(ge=0,le=4)


class VersionRestoreRequest(Contract):
    base_version_id: UUID


class VersionRestoreResult(Contract):
    item_id: UUID
    version_id: UUID
    version_number: int
    restored_from_version_id: UUID

router = APIRouter(prefix='/api/v1')


@router.get('/platform-presets', response_model=list[PlatformPreset])
def platform_presets():
    return [{'platform': key, **value} for key, value in PRESETS.items()]


@router.get('/templates', response_model=list[TemplateView])
def templates():
    return [{'id': key, **value} for key, value in TEMPLATES.items()]


RETRYABLE = ('failed', 'partial', 'interrupted', 'cancelled')


def job_view(job, has_child=False):
    return JobView(id=job.id,topic=job.snapshot['request']['topic'],campaign_id=job.campaign_id,
        parent_job_id=job.parent_job_id,can_retry=job.status in RETRYABLE and not has_child and not job.checkpoint.get('permanently_deleted_content'),
        status=job.status,current_stage=job.current_stage,stages=job.stages,results=job.results,error=job.error,created_at=job.created_at)


@router.get('/generation-jobs', response_model=JobPage)
def job_history(request:Request, page:int=Query(1,ge=1), limit:int=Query(20,ge=1,le=100),
                status:JobStatus | None=None, campaign_id:UUID | None=None):
    with Session(request.app.state.engine) as db:
        query = select(GenerationJob)
        if status:
            query = query.where(GenerationJob.status == status)
        if campaign_id:
            if not db.get(Campaign, str(campaign_id)):
                raise HTTPException(404, 'Campaign not found.')
            query = query.where(GenerationJob.campaign_id == str(campaign_id))
        total = db.scalar(select(func.count()).select_from(query.subquery()))
        rows = db.scalars(query.order_by(GenerationJob.created_at.desc(),GenerationJob.id).offset((page-1)*limit).limit(limit)).all()
        parents = set(db.scalars(select(GenerationJob.parent_job_id).where(GenerationJob.parent_job_id.in_([row.id for row in rows]))))
        return JobPage(items=[JobSummary(id=row.id,topic=row.snapshot['request']['topic'],
            campaign_id=row.campaign_id,campaign_name=row.snapshot.get('campaign',{}).get('name'),
            parent_job_id=row.parent_job_id,status=row.status,current_stage=row.current_stage,
            created_at=row.created_at,can_retry=row.status in RETRYABLE and row.id not in parents and not row.checkpoint.get('permanently_deleted_content'))
            for row in rows], total=total,page=page,limit=limit)


def version_view(item, version, db):
    approval_status='unapproved'
    return {'id':item.id,'version_id':version.id,'version_number':version.version_number,'created_at':version.created_at,**version.snapshot,'approval_status':approval_status,'publishing_status':'not_published',**ContentTrashState(id=item.id,trashed_at=item.trashed_at).model_dump(mode='json')}


@router.get('/research-reports/{report_id}',response_model=ResearchReport)
def get_report(report_id: UUID, request: Request):
    with Session(request.app.state.engine) as db:
        row=db.get(ResearchRun,str(report_id))
        if not row:
            raise HTTPException(404,'Research report not found.')
        return row.snapshot


@router.post('/generation-jobs',response_model=JobView,status_code=202)
def create_job(payload: GenerationRequest, request: Request, idempotency_key: str = Header(min_length=1,max_length=128)):
    settings=request.app.state.settings
    fingerprint=digest(payload.model_dump(mode='json'))
    with Session(request.app.state.engine) as db:
        existing=db.scalar(select(GenerationJob).where(GenerationJob.idempotency_key==idempotency_key))
        if existing:
            if existing.request_hash != fingerprint:
                raise HTTPException(409,'This idempotency key belongs to another request.')
            return job_view(existing)
        report=db.get(ResearchRun,str(payload.report_id))
        if not report:
            raise HTTPException(404,'Choose an available research report.')
        if report.origin=='provided':
            raise HTTPException(409,'Use Guided Create and reconfirm supplied facts for a new announcement.')
        if report.origin=='demo' and not request.app.state.include_demo_reports:
            raise HTTPException(409,'Demo reports are retired. Create a new report in Research.')
        if payload.campaign_id and not db.get(Campaign,str(payload.campaign_id)):
            raise HTTPException(404,'Campaign not found.')
        if db.scalar(select(func.count()).select_from(GenerationJob).where(GenerationJob.status.in_(['queued','running']))) >= 10:
            raise HTTPException(429,'The local generation queue is full. Wait for current jobs to finish.')
        family_id=str(uuid4())
        snapshot={'request':payload.model_dump(mode='json'),'report':report.snapshot,'provider':settings.content_provider,'model':settings.content_model,'seed_id':family_id,'prompt_version':'content-v10-topic-visuals'}
        if payload.campaign_id:
            campaign=db.get(Campaign,str(payload.campaign_id))
            snapshot['campaign']=campaign.snapshot
            # Apply campaign defaults only to fields omitted by the caller.
            for key in ('audience','platforms'):
                if key not in payload.model_fields_set and campaign.snapshot.get(key):
                    snapshot['request'][key]=campaign.snapshot[key]
            snapshot['request']['approved_user_facts']=list(dict.fromkeys([*campaign.snapshot.get('approved_facts',[]),*payload.approved_user_facts]))
        job=GenerationJob(report_id=str(payload.report_id),campaign_id=str(payload.campaign_id) if payload.campaign_id else None,family_id=family_id,idempotency_key=idempotency_key,request_hash=fingerprint,snapshot=snapshot)
        db.add(job)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            existing=db.scalar(select(GenerationJob).where(GenerationJob.idempotency_key==idempotency_key))
            if not existing or existing.request_hash != fingerprint:
                raise HTTPException(409,'Concurrent request conflict.') from None
            return job_view(existing)
        db.refresh(job)
        has_child = db.scalar(select(GenerationJob.id).where(GenerationJob.parent_job_id == job.id).limit(1))
        return job_view(job, has_child=bool(has_child))


@router.get('/generation-jobs/{job_id}',response_model=JobView)
def get_job(job_id:UUID,request:Request):
    with Session(request.app.state.engine) as db:
        job=db.get(GenerationJob,str(job_id))
        if not job:
            raise HTTPException(404,'Job not found.')
        has_child = db.scalar(select(GenerationJob.id).where(GenerationJob.parent_job_id == job.id).limit(1))
        return job_view(job, has_child=bool(has_child))


@router.post('/generation-jobs/{job_id}/retry',response_model=JobView,status_code=202)
def retry_job(job_id:UUID,payload:RetryRequest,request:Request):
    with Session(request.app.state.engine) as db:
        # Serialize local SQLite retries so concurrent clicks cannot fork a job.
        db.connection().exec_driver_sql('BEGIN IMMEDIATE')
        previous=db.get(GenerationJob,str(job_id))
        if not previous:
            raise HTTPException(404,'Job not found.')
        if previous.checkpoint.get('permanently_deleted_content'):
            raise HTTPException(409,'This generation contains permanently deleted content and cannot be retried.')
        trash=select(ContentItem.id).where(ContentItem.family_id==previous.family_id, ContentItem.trashed_at.is_not(None),ContentItem.deleted_at.is_(None))
        if previous.snapshot.get('target_item_id'):
            trash=trash.where(ContentItem.id==previous.snapshot['target_item_id'])
        if db.scalar(trash.limit(1)):
            raise HTTPException(409,'Restore trashed content in this job before retrying.')
        if previous.status not in RETRYABLE:
            raise HTTPException(409,'Only incomplete jobs can be retried.')
        if db.scalar(select(GenerationJob.id).where(GenerationJob.parent_job_id==previous.id).limit(1)):
            raise HTTPException(409,'This job has a newer attempt or revision. Open the latest job in generation history.')
        if db.scalar(select(GenerationJob.id).where(GenerationJob.family_id==previous.family_id,GenerationJob.status.in_(['queued','running']))):
            raise HTTPException(409,'A retry for this content is already active.')
        snapshot,checkpoint=deepcopy(previous.snapshot),deepcopy(previous.checkpoint)
        checkpoint.pop('provider_retry_count',None)
        checkpoint.pop('provider_resume_at',None)
        if db.scalar(select(func.count()).select_from(GenerationJob).where(GenerationJob.status.in_(['queued','running']))) >= 10:
            raise HTTPException(429,'The local generation queue is full. Wait for current jobs to finish.')
        if snapshot.get('target_item_id'):
            item = db.get(ContentItem, snapshot['target_item_id'])
            current = db.get(ContentVersion, item.current_version_id) if item else None
            if current and current.job_id == previous.id:
                snapshot['base_version_id'] = current.id
        if any('Background rejected:' in value.get('artwork_error','') for value in checkpoint.get('concepts',{}).values()):
            # New candidates on an explicit retry after OCR rejection; keep
            # completed concepts and their exact background assets intact.
            snapshot['seed_id'] = str(uuid4())
        if payload.artwork_mode and payload.artwork_mode != snapshot['request']['artwork_mode']:
            snapshot['request']['artwork_mode']=payload.artwork_mode
            checkpoint.pop('concepts',None)
        job=GenerationJob(report_id=previous.report_id,campaign_id=previous.campaign_id,family_id=previous.family_id,parent_job_id=previous.id,idempotency_key=str(uuid4()),request_hash=digest(snapshot['request']),snapshot=snapshot,checkpoint=checkpoint)
        db.add(job);db.commit();db.refresh(job)
        return job_view(job)


@router.post('/generation-jobs/{job_id}/cancel',response_model=JobView)
def cancel_job(job_id:UUID,request:Request):
    with Session(request.app.state.engine) as db:
        job=db.get(GenerationJob,str(job_id))
        if not job:
            raise HTTPException(404,'Job not found.')
        if job.status not in ('queued','running'):
            raise HTTPException(409,'Job is no longer active.')
        job.status='cancelled';db.commit()
        return job_view(job)


@router.get('/content')
def library(request:Request,page:int=Query(1,ge=1),limit:int=Query(20,ge=1,le=100),campaign_id:UUID | None=None,trashed:bool=False,
            q:str=Query('',max_length=200),platform:Literal['instagram','facebook','linkedin'] | None=None,
            approval:Literal['approved','unapproved','rejected'] | None=None,
            sort:Literal['newest','oldest','title']='newest',date_from:date | None=None,date_to:date | None=None):
    if date_from and date_to and date_from>date_to: raise HTTPException(422,'Start date must be on or before end date.')
    with Session(request.app.state.engine) as db:
        query=select(ContentItem,ContentVersion).join(ContentVersion,ContentVersion.id==ContentItem.current_version_id)
        query=query.where(ContentItem.deleted_at.is_(None))
        query=query.where(ContentItem.trashed_at.is_not(None) if trashed else ContentItem.trashed_at.is_(None))
        if campaign_id:
            if not db.get(Campaign, str(campaign_id)):
                raise HTTPException(404, 'Campaign not found.')
            query=query.join(GenerationJob,GenerationJob.id==ContentVersion.job_id).where(GenerationJob.campaign_id==str(campaign_id))
        if q.strip():
            pattern='%'+q.strip().replace('\\','\\\\').replace('%','\\%').replace('_','\\_')+'%'
            captions=func.json_each(ContentVersion.snapshot,'$.concept.captions').table_valued('value').alias('search_captions')
            query=query.where(or_(ContentVersion.snapshot['concept']['title'].as_string().ilike(pattern,escape='\\'),
                exists(select(1).select_from(captions).where(func.json_extract(captions.c.value,'$.text').ilike(pattern,escape='\\')))))
        if platform:
            platforms=func.json_each(ContentVersion.snapshot,'$.request.platforms').table_valued('value').alias('search_platforms')
            query=query.where(exists(select(1).select_from(platforms).where(platforms.c.value==platform)))
        if date_from: query=query.where(ContentVersion.created_at>=datetime.combine(date_from,time.min,timezone.utc).isoformat())
        if date_to: query=query.where(ContentVersion.created_at<=datetime.combine(date_to,time.max,timezone.utc).isoformat())
        ordering=[ContentVersion.created_at.desc(),ContentItem.id]
        if sort=='oldest': ordering=[ContentVersion.created_at.asc(),ContentItem.id]
        elif sort=='title': ordering=[func.lower(ContentVersion.snapshot['concept']['title'].as_string()),ContentItem.id]
        query=query.order_by(*ordering)
        if approval:
            # Approval is an authoritative projection, not the immutable snapshot's historical value.
            matches=[view for item,version in db.execute(query) if (view:=version_view(item,version,db))['approval_status']==approval]
            return {'items':matches[(page-1)*limit:page*limit],'total':len(matches),'page':page,'limit':limit}
        total=db.scalar(select(func.count()).select_from(query.order_by(None).subquery()))
        rows=db.execute(query.offset((page-1)*limit).limit(limit)).all()
        return {'items':[version_view(item,version,db) for item,version in rows],'total':total,'page':page,'limit':limit}










@router.get('/content/{item_id}')
def get_content(item_id:UUID,request:Request):
    with Session(request.app.state.engine) as db:
        item=db.get(ContentItem,str(item_id))
        if not item or item.deleted_at:
            raise HTTPException(404,'Content not found.')
        return version_view(item,db.get(ContentVersion,item.current_version_id),db)


@router.get('/content/{item_id}/versions')
def versions(item_id:UUID,request:Request):
    with Session(request.app.state.engine) as db:
        item=db.get(ContentItem,str(item_id))
        if not item or item.deleted_at:
            raise HTTPException(404,'Content not found.')
        return [version_view(item,v,db) for v in db.scalars(select(ContentVersion).where(ContentVersion.item_id==item.id).order_by(ContentVersion.version_number.desc()))]


@router.post('/content/{item_id}/versions/{version_id}/restore',response_model=VersionRestoreResult)
def restore_version(item_id:UUID,version_id:UUID,payload:VersionRestoreRequest,request:Request,
                    idempotency_key:str=Header(min_length=1,max_length=128)):
    """Copy an immutable saved version without regenerating any output."""
    fingerprint=digest({'restore_item':str(item_id),'source':str(version_id),**payload.model_dump(mode='json')})
    with Session(request.app.state.engine) as db:
        db.connection().exec_driver_sql('BEGIN IMMEDIATE')
        item=db.get(ContentItem,str(item_id))
        if not item or item.deleted_at: raise HTTPException(404,'Content not found.')
        if item.trashed_at: raise HTTPException(409,'Restore this content from Trash first.')
        existing=db.scalar(select(GenerationJob).where(GenerationJob.idempotency_key==idempotency_key))
        if existing:
            if existing.request_hash!=fingerprint: raise HTTPException(409,'This idempotency key belongs to another request.')
            version=db.scalar(select(ContentVersion).where(ContentVersion.job_id==existing.id,ContentVersion.item_id==item.id))
            if not version: raise HTTPException(409,'The restored version is unavailable.')
            return VersionRestoreResult(item_id=item.id,version_id=version.id,version_number=version.version_number,restored_from_version_id=version_id)
        if item.current_version_id!=str(payload.base_version_id):
            raise HTTPException(409,'Content changed. Reload version history before restoring.')
        source=db.get(ContentVersion,str(version_id))
        if not source or source.item_id!=item.id: raise HTTPException(404,'Version not found.')
        if source.id==item.current_version_id: raise HTTPException(409,'This version is already current.')
        if db.scalar(select(GenerationJob.id).where(GenerationJob.family_id==item.family_id,
            or_(GenerationJob.status.in_(['queued','running']),GenerationJob.id.in_(list(request.app.state.workflow.active_jobs)))).limit(1)):
            raise HTTPException(409,'Wait for active generation or editing to finish.')
        if digest(source.snapshot)!=source.payload_digest: raise HTTPException(409,'Saved content integrity check failed.')
        saved=deepcopy(source.snapshot)
        backgrounds=[saved.get('background'),*saved.get('platform_backgrounds',{}).values()]
        try:
            for asset_id in set(b for b in backgrounds if b): request.app.state.workflow.assets.read(asset_id)
        except (ProviderError,OSError):
            raise HTTPException(409,'A saved background is missing or failed its integrity check.') from None
        current=db.get(ContentVersion,item.current_version_id)
        previous=db.get(GenerationJob,source.job_id)
        snapshot=deepcopy(previous.snapshot)
        snapshot.pop('natural_revision',None)
        snapshot.update(request=deepcopy(saved['request']),target_item_id=item.id,base_version_id=current.id,
                        restored_from_version_id=source.id)
        saved['restored_from_version_id']=source.id
        saved['restored_from_version_number']=source.version_number
        saved['parent_version_id']=current.id
        job=GenerationJob(report_id=previous.report_id,campaign_id=previous.campaign_id,family_id=item.family_id,
            parent_job_id=current.job_id,idempotency_key=idempotency_key,request_hash=fingerprint,snapshot=snapshot,
            status='succeeded',current_stage='persistence',stages=[])
        db.add(job);db.flush()
        version=ContentVersion(item_id=item.id,job_id=job.id,version_number=current.version_number+1,
            snapshot=saved,payload_digest=digest(saved))
        db.add(version);db.flush()
        item.current_version_id=version.id
        # Verify saved render integrity locally; no approval/publishing subsystem is included.
        try:
            for asset_id in saved.get('renders', []): request.app.state.workflow.assets.read(asset_id)
        except (ProviderError, OSError):
            raise HTTPException(409, 'A saved render is missing or failed its integrity check.') from None
        job.results=[{'item_id':item.id,'version_id':version.id,'version_number':version.version_number,'restored_from_version_number':source.version_number}]
        db.commit()
        return VersionRestoreResult(item_id=item.id,version_id=version.id,version_number=version.version_number,restored_from_version_id=source.id)


@router.post('/content/{item_id}/preview',response_class=Response,
             responses={200:{'content':{'image/png':{}}}})
def preview_poster(item_id:UUID,payload:PosterPreviewRequest,request:Request):
    with Session(request.app.state.engine) as db:
        item=db.get(ContentItem,str(item_id))
        if not item or item.deleted_at: raise HTTPException(404,'Content not found.')
        if item.trashed_at: raise HTTPException(409,'Restore this content from Trash first.')
        if item.current_version_id!=str(payload.base_version_id):
            raise HTTPException(409,'Content changed. Reopen the editor before previewing.')
        saved=db.get(ContentVersion,item.current_version_id).snapshot
        generation=GenerationRequest.model_validate(saved['request'])
        if payload.platform not in generation.platforms: raise HTTPException(422,'Platform is not part of this content.')
        if payload.template_id: generation.template_id=payload.template_id
        concept=payload.concept.model_copy(deep=True)
        distinct=generation.creative_mode=='distinct_platforms'
        if distinct:
            variant=concept.platform_variants.get(payload.platform)
            if not variant: raise HTTPException(422,'Platform copy is missing.')
            concept.slides=variant.slides
        if payload.slide_index>=len(concept.slides): raise HTTPException(422,'Slide is not part of this content.')
        background=saved.get('platform_backgrounds',{}).get(payload.platform) if distinct else saved.get('background')
        if not background: raise HTTPException(409,'Saved background is unavailable. Finish artwork generation first.')
        platform=payload.platform if generation.export_mode=='per_platform' else None
    if not preview_slots.acquire(blocking=False):
        raise HTTPException(429,'Preview renderer is busy. Retry in a moment.')
    try:
        data=request.app.state.workflow.renderer.render(generation,concept,background,platform=platform,preview_index=payload.slide_index)
        return Response(content=data,media_type='image/png',headers={'Cache-Control':'no-store'})
    except ProviderError as exc:
        raise HTTPException(422,str(exc)) from None
    finally:
        preview_slots.release()


@router.post('/content/{item_id}/revisions',response_model=JobView,status_code=202)
def revise(item_id:UUID,payload:RevisionRequest,request:Request):
    with Session(request.app.state.engine) as db:
        db.connection().exec_driver_sql('BEGIN IMMEDIATE')
        item=db.get(ContentItem,str(item_id))
        if not item or item.deleted_at:
            raise HTTPException(404,'Content not found.')
        if item.trashed_at:
            raise HTTPException(409,'Restore this content before editing it.')
        if item.current_version_id != str(payload.base_version_id):
            raise HTTPException(409,'A newer version exists. Reload before editing.')
        version=db.get(ContentVersion,item.current_version_id)
        previous=db.get(GenerationJob,version.job_id)
        if db.scalar(select(GenerationJob.id).where(GenerationJob.family_id==previous.family_id,GenerationJob.status.in_(['queued','running']))):
            raise HTTPException(409,'An update for this content is already active. Wait for it to finish.')
        snapshot=deepcopy(previous.snapshot)
        snapshot.pop('natural_revision',None)
        expected_platforms = snapshot['request']['platforms']
        actual_platforms = [caption.platform for caption in payload.concept.captions]
        if len(actual_platforms) != len(set(actual_platforms)) or set(actual_platforms) != set(expected_platforms):
            raise HTTPException(422, 'Provide exactly one caption for every selected platform.')
        snapshot['request']['concept_count']=1
        snapshot['request']['slide_count']=len(payload.concept.slides)
        snapshot['target_item_id']=item.id
        snapshot['base_version_id']=version.id
        if payload.template_id is not None:
            snapshot['request']['template_id'] = payload.template_id
        if snapshot['request'].get('creative_mode') == 'distinct_platforms':
            if set(payload.concept.platform_variants) != set(expected_platforms) or any(len(v.slides) != len(payload.concept.slides) for v in payload.concept.platform_variants.values()):
                raise HTTPException(422, 'Keep one creative variant per platform with matching slide counts.')
        checkpoint={'batch':GeneratedBatch(concepts=[payload.concept]).model_dump(mode='json'),'concepts':{'0':{'background':version.snapshot.get('background')}}}
        checkpoint['concepts']['0']['platform_backgrounds'] = deepcopy(version.snapshot.get('platform_backgrounds', {}))
        job=GenerationJob(report_id=previous.report_id,campaign_id=previous.campaign_id,family_id=previous.family_id,parent_job_id=previous.id,idempotency_key=str(uuid4()),request_hash=digest(snapshot),snapshot=snapshot,checkpoint=checkpoint)
        db.add(job);db.commit();db.refresh(job)
        return job_view(job)


@router.post('/content/{item_id}/natural-revisions',response_model=JobView,status_code=202)
def natural_revision(item_id:UUID,payload:NaturalRevisionRequest,request:Request,idempotency_key:str=Header(min_length=1,max_length=128)):
    fingerprint=digest({'item_id':str(item_id),**payload.model_dump(mode='json')})
    with Session(request.app.state.engine) as db:
        db.connection().exec_driver_sql('BEGIN IMMEDIATE')
        existing=db.scalar(select(GenerationJob).where(GenerationJob.idempotency_key==idempotency_key))
        if existing:
            if existing.request_hash!=fingerprint: raise HTTPException(409,'This idempotency key belongs to another request.')
            return job_view(existing)
        item=db.get(ContentItem,str(item_id))
        if not item or item.deleted_at: raise HTTPException(404,'Content not found.')
        if item.trashed_at: raise HTTPException(409,'Restore this content before editing it.')
        if item.current_version_id!=str(payload.base_version_id): raise HTTPException(409,'A newer version exists. Reload before editing.')
        if db.scalar(select(GenerationJob.id).where(GenerationJob.family_id==item.family_id,GenerationJob.status.in_(['queued','running'])).limit(1)):
            raise HTTPException(409,'Wait for active generation or editing to finish.')
        if db.scalar(select(func.count()).select_from(GenerationJob).where(GenerationJob.status.in_(['queued','running'])))>=10:
            raise HTTPException(429,'The local generation queue is full.')
        version=db.get(ContentVersion,item.current_version_id);base=version.snapshot
        selected=base['request']['platforms'];distinct=base['request'].get('creative_mode')=='distinct_platforms'
        if not set(payload.platforms).issubset(selected): raise HTTPException(422,'Select platforms present in this content.')
        if payload.slide_number and payload.slide_number>len(base['concept']['slides']): raise HTTPException(422,'This slide does not exist.')
        if payload.scope!='captions' and not distinct and set(payload.platforms)!=set(selected):
            raise HTTPException(422,'Shared poster text applies to all platforms. Select all platforms or edit captions only.')
        if (distinct and any(not base.get('platform_backgrounds',{}).get(p) for p in selected)) or (not distinct and not base.get('background')):
            raise HTTPException(409,'Finish background generation before requesting a text revision.')
        previous=db.get(GenerationJob,version.job_id);snapshot=deepcopy(previous.snapshot)
        snapshot['request']=deepcopy(base['request']);snapshot['request']['concept_count']=1
        snapshot['request']['slide_count']=len(base['concept']['slides'])
        snapshot.update(target_item_id=item.id,base_version_id=version.id,provider=request.app.state.settings.content_provider,
            model=request.app.state.settings.content_model,prompt_version='content-revision-v1',
            natural_revision={'request':payload.model_dump(mode='json'),'base':deepcopy(base)})
        job=GenerationJob(report_id=previous.report_id,campaign_id=previous.campaign_id,family_id=previous.family_id,parent_job_id=previous.id,
            idempotency_key=idempotency_key,request_hash=fingerprint,snapshot=snapshot)
        db.add(job);db.commit();db.refresh(job)
        return job_view(job)


@router.get('/assets/{asset_id}')
def asset(asset_id:UUID,request:Request,download:bool=False):
    try:
        data=request.app.state.workflow.assets.read(str(asset_id))
    except ProviderError:
        raise HTTPException(404,'Asset unavailable or integrity check failed.') from None
    headers={'Cache-Control':'private, max-age=31536000, immutable'}
    if download:
        metadata = request.app.state.workflow.assets.metadata(str(asset_id))
        platform = metadata.get('platform')
        # Only application-owned names enter response headers.
        prefix = platform if platform in PRESETS else 'poster'
        headers['Content-Disposition']=f'attachment; filename="{prefix}-{asset_id}.png"'
    return Response(content=data,media_type='image/png',headers=headers)
