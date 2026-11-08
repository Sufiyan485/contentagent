from io import BytesIO
from uuid import uuid4
import asyncio
import sys
from concurrent.futures import ThreadPoolExecutor

import pytest
from PIL import Image
from pydantic import ValidationError
from sqlalchemy.orm import Session

from backend.app.config import ROOT, Settings
from backend.app.contracts import GeneratedConcept, GenerationRequest
from backend.app.database import make_engine, migrate
from backend.app.models import Asset
from backend.app.services.assets import AssetStore
from backend.app.services.artwork import ArtworkService
from backend.app.services.providers import ProviderError
from backend.app.services.renderer import PosterRenderer
from backend.app.templates import TEMPLATES, template_css


@pytest.fixture
def rendering(tmp_path):
    settings = Settings(_env_file=None, app_data_dir=tmp_path)
    engine = make_engine(settings)
    migrate(engine)
    store = AssetStore(engine, settings)
    yield engine, store, ArtworkService(settings, store), PosterRenderer(store)
    engine.dispose()


def concept(count=1):
    return GeneratedConcept(title='Template verification fixture', background_design='Abstract shapes',
        captions=[{'platform': 'instagram', 'text': 'Test fixture caption.'}],
        slides=[{'headline': 'Turn curiosity into understanding', 'body': 'Start with a question. Explore the evidence. Share what you learn with a clear explanation and a useful next step.', 'cta': 'Explore the full report', 'layout': 'educational'} for _ in range(count)])


@pytest.mark.parametrize('template', TEMPLATES)
@pytest.mark.parametrize('slides', [1, 2, 5])
def test_template_rendering_and_carousel_background(rendering, template, slides):
    engine, store, artwork, renderer = rendering
    request = GenerationRequest(topic='Template fixture', report_id=uuid4(), template_id=template, slide_count=slides, artwork_mode='application_gradient')
    batch = concept(slides)
    background = artwork.generate(request, batch, 1)
    output = renderer.render(request, batch, background)
    assert len(output) == slides
    for asset_id in output:
        with Session(engine) as db:
            asset = db.get(Asset, asset_id)
            assert asset.metadata_json['template'] == template
            assert asset.metadata_json['background_asset_id'] == background
        with Image.open(BytesIO(store.read(asset_id))) as image:
            assert image.size == (1080, 1080)
    # Explicit fixture previews, separate from live content and the app database.
    if slides == 1:
        folder = ROOT / 'data' / 'verification' / 'templates'
        folder.mkdir(parents=True, exist_ok=True)
        (folder / f'{template}.png').write_bytes(store.read(output[0]))


@pytest.mark.parametrize('template', TEMPLATES)
def test_unfittable_copy_fails_instead_of_clipping(rendering, template):
    _, _, artwork, renderer = rendering
    request = GenerationRequest(topic='Overflow fixture', report_id=uuid4(), template_id=template, artwork_mode='application_gradient')
    batch = concept()
    batch.slides[0].body = '\n'.join(['Line'] * 100)
    background = artwork.generate(request, batch, 1)
    with pytest.raises(ProviderError, match='overflows'):
        renderer.render(request, batch, background)


def test_template_paths_are_allowlisted():
    with pytest.raises(ValidationError):
        GenerationRequest(topic='Test', report_id=uuid4(), template_id='../../.env')
    with pytest.raises(ValueError):
        template_css('../../.env')


@pytest.mark.parametrize('template', TEMPLATES)
@pytest.mark.parametrize('theme', ['light', 'colorful'])
def test_bright_themes_render_with_shared_background(rendering,template,theme):
    engine,store,artwork,renderer=rendering
    request=GenerationRequest(topic='Theme fixture',report_id=uuid4(),template_id=template,background_theme=theme,artwork_mode='application_gradient',slide_count=2)
    batch=concept(2)
    background=artwork.generate(request,batch,1)
    output=renderer.render(request,batch,background)
    assert len(output)==2
    for asset_id in output:
        assert store.metadata(asset_id)['background_asset_id']==background
        assert store.metadata(asset_id)['background_theme']==theme
    folder=ROOT/'data/verification/templates'
    folder.mkdir(parents=True,exist_ok=True)
    (folder/f'{template}-{theme}.png').write_bytes(store.read(output[0]))


@pytest.mark.skipif(sys.platform != 'win32', reason='Windows reload event-loop regression')
def test_renderer_under_windows_reload_policy(rendering):
    _, store, artwork, renderer = rendering
    request = GenerationRequest(topic='Reload regression', report_id=uuid4(), template_id='spotlight-v1', artwork_mode='application_gradient')
    batch = concept()
    background = artwork.generate(request, batch, 1)
    previous = asyncio.get_event_loop_policy()
    selector = asyncio.WindowsSelectorEventLoopPolicy()
    try:
        asyncio.set_event_loop_policy(selector)
        with ThreadPoolExecutor(max_workers=1) as worker:
            output = worker.submit(renderer.render, request, batch, background).result(timeout=45)
        assert asyncio.get_event_loop_policy() is selector
        assert store.read(output[0]).startswith(b'\x89PNG')
    finally:
        asyncio.set_event_loop_policy(previous)
