"""Explicit test-only demo ingestion. Never imported by runtime startup."""
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
