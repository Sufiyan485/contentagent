from copy import deepcopy
from hashlib import sha256
import json
import time
from threading import Event, Thread
from typing import TypedDict
from uuid import uuid4

from langgraph.graph import StateGraph, START, END
from langsmith import tracing_context
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from .agents.content import ContentCreationAgent
from .agents.revision import revise_text, reused_assets
from .contracts import GeneratedBatch, GenerationRequest, ResearchReport, PlatformExport
from .templates.platforms import PRESETS
from .models import ContentItem, ContentVersion, GenerationJob, now_iso
from .services.assets import AssetStore
from .services.artwork import ArtworkService
from .services.providers import ProviderError, ProviderDeferred, TextService
from .services.quality import check_concept
from .services.renderer import PosterRenderer

STAGES = ['validate','text_generation','artwork_generation','poster_rendering','quality_checks','persistence']


def digest(value):
    return sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()


class State(TypedDict):
    job_id: str


class ContentWorkflow:
    def __init__(self, engine, settings, text_service=None, artwork=None, renderer=None):
        self.engine, self.settings = engine, settings
        self.active_jobs = set()
        self.assets = AssetStore(engine, settings)
        self.agent = ContentCreationAgent(text_service or TextService(settings))
        if isinstance(self.agent.text_service,TextService): self.agent.text_service.defer_retries=True
        self.artwork = artwork or ArtworkService(settings,self.assets)
        self.renderer = renderer or PosterRenderer(self.assets)
        graph = StateGraph(State)
        for stage in STAGES:
            graph.add_node(stage,self.node(stage))
        graph.add_edge(START,STAGES[0])
        for previous, following in zip(STAGES,STAGES[1:]):
            graph.add_edge(previous,following)
        graph.add_edge(STAGES[-1],END)
        self.graph = graph.compile()

    def checkpoint(self, job_id, checkpoint):
        with Session(self.engine) as db:
            row = db.get(GenerationJob,job_id)
            if row.checkpoint.get('permanently_deleted_content'):
                raise ProviderError('Content was permanently deleted; this job cannot resume.')
            row.checkpoint = deepcopy(checkpoint)
            db.commit()

    def generate_batch(self, request, report, snapshot, checkpoint, job_id, group):
        if request.concept_count==1:
            batch=self.agent.generate(request,report,snapshot['provider'],snapshot['model'],campaign=snapshot.get('campaign'),correction=checkpoint.get('text_correction'))
            checkpoint.pop('text_correction',None)
            checkpoint['provider_retry_count']=0
            return batch.model_dump(mode='json')
        # Bound each completion, and persist each validated concept before the next call.
        parts=checkpoint.setdefault('text_parts',{}).setdefault(group,[])
        while len(parts)<request.concept_count:
            batch=self.agent.generate(request.model_copy(update={'concept_count':1}),report,snapshot['provider'],snapshot['model'],
                campaign=snapshot.get('campaign'),creative_context={'concept_number':len(parts)+1,'total':request.concept_count,
                    'avoid_repeating_titles':[p['title'] for p in parts]},correction=checkpoint.get('text_correction'))
            checkpoint.pop('text_correction',None)
            parts.append(batch.concepts[0].model_dump(mode='json'))
            checkpoint['provider_retry_count']=0
            self.checkpoint(job_id,checkpoint)
        return {'concepts':deepcopy(parts)}

    def node(self, stage):
        def run(state):
            with Session(self.engine) as db:
                job = db.get(GenerationJob,state['job_id'])
                if job.checkpoint.get('permanently_deleted_content'):
                    raise ProviderError('Content was permanently deleted; this job cannot resume.')
                if job.status == 'cancelled':
                    raise ProviderError('Generation cancelled. Completed work is preserved.')
                job.current_stage = stage
                job.stages = [*job.stages,{'stage':stage,'status':'running','at':now_iso()}]
                db.commit()
                snapshot, checkpoint = deepcopy(job.snapshot), deepcopy(job.checkpoint)
            # Snapshots written before platform exports keep their original layout.
            request = GenerationRequest.model_validate({'export_mode':'shared_square', **snapshot['request']})
            report = ResearchReport.model_validate(snapshot['report'])
            if stage == 'validate':
                if request.brand_profile_id:
                    raise ProviderError('Saved brand profiles are not implemented; use the inline brand options.')
                if snapshot.get('target_item_id'):
                    with Session(self.engine) as db:
                        item=db.get(ContentItem,snapshot['target_item_id'])
                        if not item or item.current_version_id != snapshot['base_version_id']:
                            raise ProviderError('A newer version exists. Reload and submit the edit again.')
            elif stage == 'text_generation':
                if 'batch' not in checkpoint:
                    if snapshot.get('natural_revision'):
                        concept=revise_text(self.agent.text_service,request,report,snapshot,correction=checkpoint.get('text_correction'))
                        checkpoint.pop('text_correction',None)
                        checkpoint['batch']=GeneratedBatch(concepts=[concept]).model_dump(mode='json')
                        checkpoint['concepts']={'0':reused_assets(request,snapshot['natural_revision']['base'],concept)}
                    elif request.creative_mode == 'distinct_platforms':
                        batches = checkpoint.setdefault('platform_batches', {})
                        directions = {'instagram':'Expressive illustration of the report subject with a clear focal object', 'facebook':'Approachable illustration of the report subject with warm balanced lighting; no unrelated everyday props', 'linkedin':'Precise illustration of the report subject with refined materials and professional lighting'}
                        for platform in request.platforms:
                            if platform not in batches:
                                specific = request.model_copy(update={'platforms':[platform], 'creative_mode':'shared', 'visual_style':request.visual_style + '. ' + directions[platform]})
                                batches[platform] = self.generate_batch(specific,report,snapshot,checkpoint,state['job_id'],platform)
                                self.checkpoint(state['job_id'],checkpoint)
                        combined = deepcopy(batches[request.platforms[0]])
                        for index, concept in enumerate(combined['concepts']):
                            concept['captions'] = [batches[p]['concepts'][index]['captions'][0] for p in request.platforms]
                            concept['warnings'] = list(dict.fromkeys(w for p in request.platforms for w in batches[p]['concepts'][index].get('warnings',[])))
                            concept['platform_variants'] = {p: {key:batches[p]['concepts'][index][key] for key in ('slides','background_design')} for p in request.platforms}
                        checkpoint['batch'] = GeneratedBatch.model_validate(combined).model_dump(mode='json')
                    else:
                        checkpoint['batch'] = self.generate_batch(request,report,snapshot,checkpoint,state['job_id'],'shared')
                    self.checkpoint(state['job_id'],checkpoint)
            elif stage in ('artwork_generation','poster_rendering','quality_checks'):
                batch = GeneratedBatch.model_validate(checkpoint['batch'])
                checkpoint.setdefault('concepts',{})
                for index, concept in enumerate(batch.concepts):
                    result = checkpoint['concepts'].setdefault(str(index),{})
                    try:
                        if request.creative_mode == 'distinct_platforms':
                            self.platform_stage(stage, request, concept, result, report, snapshot, index, state['job_id'], checkpoint)
                        elif stage == 'artwork_generation' and not result.get('background'):
                            result['background'] = self.artwork.generate(request,concept,int(digest({'job':snapshot['seed_id'],'index':index})[:7],16))
                            result.pop('artwork_error',None)
                        elif stage == 'poster_rendering' and result.get('background'):
                            if request.export_mode == 'per_platform':
                                exports = result.setdefault('platform_exports', {})
                                errors = result.setdefault('platform_errors', {})
                                for platform in request.platforms:
                                    if platform in exports:
                                        continue
                                    try:
                                        renders = self.renderer.render(request, concept, result['background'], platform=platform)
                                        exports[platform] = PlatformExport(platform=platform, **PRESETS[platform],
                                            template_id=request.template_id, background_asset_id=result['background'], renders=renders).model_dump(mode='json')
                                        errors.pop(platform, None)
                                    except ProviderError as error:
                                        errors[platform] = str(error)
                                    # Persist each complete platform before attempting the next one.
                                    self.checkpoint(state['job_id'], checkpoint)
                                result['renders'] = [asset for platform in request.platforms for asset in exports.get(platform, {}).get('renders', [])]
                                if errors:
                                    result['render_error'] = 'Some platform exports are incomplete. Retry to finish them.'
                                else:
                                    result.pop('render_error', None)
                            elif not result.get('renders'):
                                result['renders'] = self.renderer.render(request,concept,result['background'])
                                result.pop('render_error',None)
                        elif stage == 'quality_checks':
                            result['quality'] = check_concept(concept,result.get('background'),result.get('renders',[]),report,
                                platforms=request.platforms if request.export_mode == 'per_platform' else None,
                                exports=result.get('platform_exports', {}))
                        if stage == 'artwork_generation' and result.get('background'):
                            result['background_check'] = self.assets.metadata(result['background']).get('text_check',{'status':'not_checked','method':'legacy_asset'})
                    except ProviderError as error:
                        result['artwork_error' if stage == 'artwork_generation' else 'render_error'] = str(error)
                    self.checkpoint(state['job_id'],checkpoint)
            elif stage == 'persistence':
                self.persist(state['job_id'],snapshot,checkpoint)
            with Session(self.engine) as db:
                job = db.get(GenerationJob,state['job_id'])
                events = deepcopy(job.stages)
                events[-1]['status'] = 'completed'
                if stage in ('artwork_generation','poster_rendering'):
                    field = 'artwork_error' if stage == 'artwork_generation' else 'render_error'
                    if any(result.get(field) for result in checkpoint.get('concepts',{}).values()):
                        events[-1]['status'] = 'partial'
                job.stages = events
                db.commit()
            return state
        return run

    def platform_stage(self, stage, request, concept, result, report, snapshot, index, job_id, checkpoint):
        backgrounds = result.setdefault('platform_backgrounds', {})
        exports = result.setdefault('platform_exports', {})
        artwork_errors = result.setdefault('platform_artwork_errors', {})
        render_errors = result.setdefault('platform_errors', {})
        if set(concept.platform_variants) != set(request.platforms):
            raise ProviderError('Platform creative variants are missing. Create a new request.')
        for platform in request.platforms:
            variant = concept.platform_variants[platform]
            specific = concept.model_copy(update={'slides':variant.slides, 'background_design':variant.background_design, 'platform_variants':{}})
            try:
                if stage == 'artwork_generation' and platform not in backgrounds:
                    seed = int(digest({'job':snapshot['seed_id'],'index':index,'platform':platform})[:7],16)
                    backgrounds[platform] = self.artwork.generate(request,specific,seed)
                    artwork_errors.pop(platform,None)
                if stage == 'artwork_generation' and platform in backgrounds:
                    result.setdefault('platform_background_checks', {})[platform] = self.assets.metadata(backgrounds[platform]).get('text_check', {'status':'not_checked'})
                if stage == 'poster_rendering' and platform in backgrounds and platform not in exports:
                    renders = self.renderer.render(request,specific,backgrounds[platform],platform=platform)
                    exports[platform] = PlatformExport(platform=platform,**PRESETS[platform],template_id=request.template_id,background_asset_id=backgrounds[platform],renders=renders).model_dump(mode='json')
                    render_errors.pop(platform,None)
            except ProviderError as error:
                (artwork_errors if stage == 'artwork_generation' else render_errors)[platform] = str(error)
            self.checkpoint(job_id,checkpoint)
        for errors, field in ((artwork_errors,'artwork_error'),(render_errors,'render_error')):
            if errors:
                result[field] = 'Some platform stages are incomplete. ' + ' '.join(errors.values())
            else:
                result.pop(field,None)
        result['renders'] = [asset for p in request.platforms for asset in exports.get(p,{}).get('renders',[])]
        if stage == 'quality_checks':
            result['quality'] = check_concept(concept,backgrounds,result['renders'],report,platforms=request.platforms,exports=exports)

    def persist(self, job_id, snapshot, checkpoint):
        results = []
        with Session(self.engine) as db:
            db.connection().exec_driver_sql('BEGIN IMMEDIATE')
            job = db.get(GenerationJob,job_id)
            for index, concept in enumerate(checkpoint['batch']['concepts']):
                item = db.get(ContentItem,snapshot['target_item_id']) if snapshot.get('target_item_id') else db.scalar(select(ContentItem).where(ContentItem.family_id==job.family_id,ContentItem.concept_index==index))
                if item and item.deleted_at:
                    raise ProviderError('Content was permanently deleted; this job cannot resume.')
                if not item:
                    item = ContentItem(family_id=job.family_id,concept_index=index)
                    db.add(item); db.flush()
                existing = db.scalar(select(ContentVersion).where(ContentVersion.item_id==item.id,ContentVersion.job_id==job.id))
                if existing:
                    results.append({'item_id':item.id,'version_id':existing.id}); continue
                previous = db.get(ContentVersion,item.current_version_id) if item.current_version_id else None
                saved = {'concept':concept,**checkpoint['concepts'].get(str(index),{}),'request':snapshot['request'],'report_id':snapshot['report']['id'],'provider':snapshot['provider'],'model':snapshot['model'],'parent_version_id':item.current_version_id,'template_version':snapshot['request'].get('template_id','editorial-v1'),'prompt_version':snapshot.get('prompt_version','content-v1'),'artwork_mode':snapshot['request']['artwork_mode']}
                if job.campaign_id:
                    saved['campaign_id'] = job.campaign_id
                    saved['campaign_brief'] = snapshot.get('campaign')
                version = ContentVersion(item_id=item.id,job_id=job.id,version_number=previous.version_number+1 if previous else 1,snapshot=saved,payload_digest=digest(saved))
                db.add(version); db.flush()
                item.current_version_id=version.id
                results.append({'item_id':item.id,'version_id':version.id})
            job.results = results
            db.commit()

    def run(self, job_id):
        self.active_jobs.add(job_id)
        try:
            with Session(self.engine) as db:
                job = db.get(GenerationJob,job_id)
                if job.status != 'queued':
                    return
                if job.checkpoint.get('provider_resume_at',0)>time.time(): return
                job.checkpoint={k:v for k,v in job.checkpoint.items() if k!='provider_resume_at'}
                job.status='running'; db.commit()
            # Never send content or prompts to optional tracing services.
            with tracing_context(enabled=False):
                self.graph.invoke({'job_id':job_id})
            with Session(self.engine) as db:
                job=db.get(GenerationJob,job_id)
                if job.status != 'cancelled':
                    job.status='partial' if any(c.get('quality',{}).get('status')=='fail' for c in job.checkpoint.get('concepts',{}).values()) else 'succeeded'
                    job.error=None
                db.commit()
        except ProviderDeferred as error:
            with Session(self.engine) as db:
                job=db.get(GenerationJob,job_id)
                if job.status=='cancelled': return
                checkpoint=deepcopy(job.checkpoint)
                attempts=checkpoint.get('provider_retry_count',0)+int(error.throttled)
                checkpoint['provider_retry_count']=attempts
                if getattr(error,'correction',None): checkpoint['text_correction']=error.correction
                if attempts>5:
                    job.status='failed'
                    job.error='Provider remained unavailable after five scheduled retries. Completed text is preserved; retry later.'
                    job.stages=[*job.stages,{'stage':job.current_stage,'status':'failed','at':now_iso()}]
                else:
                    until=time.time()+error.seconds
                    checkpoint['provider_resume_at']=until
                    job.status='queued'
                    job.error=None
                    job.stages=[*job.stages,{'stage':job.current_stage,'status':'waiting','at':now_iso(),'message':str(error),'retry_at':until}]
                job.checkpoint=checkpoint
                db.commit()
        except Exception as error:
            with Session(self.engine) as db:
                job=db.get(GenerationJob,job_id)
                if job.status != 'cancelled':
                    job.status='partial' if job.checkpoint.get('batch') else 'failed'
                job.error=str(error) if isinstance(error,ProviderError) else 'This stage could not finish. Completed work is preserved; retry or check local installation.'
                events=deepcopy(job.stages)
                if events:
                    events[-1]['status']='failed'
                job.stages=events
                db.commit()
        finally:
            self.active_jobs.discard(job_id)


class JobRunner:
    def __init__(self, workflow):
        self.workflow=workflow
        self.stop=Event()
        self.thread=Thread(target=self.loop,name='content-worker',daemon=True)

    def start(self):
        with Session(self.workflow.engine) as db:
            db.execute(update(GenerationJob).where(GenerationJob.status=='running').values(status='interrupted',error='Application restarted. Retry to resume completed stages.'))
            db.commit()
        self.thread.start()

    def loop(self):
        while not self.stop.is_set():
            with Session(self.workflow.engine) as db:
                job_id=db.scalar(select(GenerationJob.id).where(GenerationJob.status=='queued',
                    (GenerationJob.checkpoint['provider_resume_at'].as_float().is_(None)) |
                    (GenerationJob.checkpoint['provider_resume_at'].as_float()<=time.time())
                ).order_by(GenerationJob.created_at).limit(1))
            if job_id:
                self.workflow.run(job_id)
            else:
                self.stop.wait(.3)

    def close(self):
        self.stop.set()
        self.thread.join(timeout=5)
