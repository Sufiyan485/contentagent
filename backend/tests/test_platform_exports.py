"""Fixture text and labeled gradients; real Chromium, database and HTTP boundary."""
from copy import deepcopy
import json
from io import BytesIO
from uuid import uuid4

import pytest
from PIL import Image
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from backend.app.config import ROOT, Settings
from backend.app.contracts import GenerationRequest
from backend.tests.app_fixture import create_app
from backend.app.models import GenerationJob
from backend.app.services.providers import ProviderError
from backend.app.templates import TEMPLATES
from backend.app.templates.platforms import PRESETS
from backend.tests.test_templates import rendering, concept


@pytest.mark.parametrize('template', TEMPLATES)
@pytest.mark.parametrize('platform', PRESETS)
def test_platform_layouts(rendering, template, platform):
    _, store, artwork, renderer = rendering
    request = GenerationRequest(topic='Platform fixture', report_id=uuid4(), template_id=template,
        background_theme='light', artwork_mode='application_gradient', slide_count=5)
    batch = concept(5)
    background = artwork.generate(request, batch, 1)
    outputs = renderer.render(request, batch, background, platform=platform)
    assert len(outputs) == 5
    for i, asset_id in enumerate(outputs):
        metadata = store.metadata(asset_id)
        assert metadata['platform'] == platform
        assert metadata['background_asset_id'] == background
        assert metadata['slide'] == i + 1
        with Image.open(BytesIO(store.read(asset_id))) as image:
            assert image.size == (PRESETS[platform]['width'], PRESETS[platform]['height'])
    folder = ROOT / 'data/verification/platforms'
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f'{platform}-{template}.png').write_bytes(store.read(outputs[0]))


@pytest.mark.parametrize('template', TEMPLATES)
@pytest.mark.parametrize('platform', PRESETS)
def test_long_readable_copy_across_platforms(rendering, template, platform):
    _, store, artwork, renderer = rendering
    theme = {'instagram': 'light', 'facebook': 'colorful', 'linkedin': 'dark'}[platform]
    request = GenerationRequest(topic='Long copy acceptance fixture', report_id=uuid4(),
        template_id=template, background_theme=theme, artwork_mode='application_gradient')
    batch = concept()
    batch.slides[0].headline = 'Build understanding through careful questions and reliable evidence'
    batch.slides[0].body = ('Start with a clear question and examine the evidence before sharing a conclusion. '
        'Compare what each source supports, explain the limits, and make the next step useful. '
        'A thoughtful explanation helps readers understand both the idea and the uncertainty. '
        'Keep learning, check assumptions, and revise your view when stronger evidence appears.')
    background = artwork.generate(request, batch, 1)
    result = renderer.render(request, batch, background, platform=platform)
    assert len(result) == 1  # Renderer rejects clipping/overlap before saving.
    folder = ROOT / 'data/verification/long-copy'
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f'{platform}-{template}.png').write_bytes(store.read(result[0]))


class PlatformText:
    calls = 0

    def generate(self, *args):
        self.calls += 1
        request = json.loads(args[0].split('\n',1)[1])['request']
        batch = concept(request['slide_count']).model_dump(mode='json')
        if len(request['platforms']) == 1:
            batch['background_design'] = request['platforms'][0] + ' distinct scene'
            batch['slides'][0]['headline'] = request['platforms'][0] + ' unique visual hook'
        for slide in batch['slides']:
            slide['claim_ids'] = ['c1']
        batch['captions'] = [{'platform': p, 'text': f'{p} fixture caption', 'claim_ids': ['c1'],
            'hashtags': ['#Learning', '#Data', '#Research']} for p in request['platforms']]
        return {'concepts': [batch]}


@pytest.mark.parametrize('platform', PRESETS)
def test_platform_overflow_is_rejected(rendering, platform):
    _, _, artwork, renderer = rendering
    request = GenerationRequest(topic='Overflow fixture', report_id=uuid4(), artwork_mode='application_gradient')
    batch = concept()
    batch.slides[0].body = '\n'.join(['Line'] * 100)
    background = artwork.generate(request, batch, 1)
    with pytest.raises(ProviderError, match='overflows'):
        renderer.render(request, batch, background, platform=platform)


def test_platform_retry_revision_restart_and_legacy(tmp_path):
    settings = Settings(_env_file=None, app_data_dir=tmp_path, content_api_key='', pollinations_api_key='')
    app = create_app(settings, start_worker=False)
    fixture = PlatformText()
    with TestClient(app) as client:
        app.state.workflow.agent.text_service = fixture
        report = next(r for r in client.get('/api/v1/research-reports').json() if r['id'].endswith('001'))
        payload = {'topic': report['topic'], 'report_id': report['id'], 'slide_count': 2,
            'platforms': list(PRESETS), 'artwork_mode': 'application_gradient'}
        job = client.post('/api/v1/generation-jobs', json=payload, headers={'Idempotency-Key': str(uuid4())}).json()['id']
        renderer = app.state.workflow.renderer
        original_render = renderer.render
        calls = []

        def fail_facebook(request, batch, background, platform=None):
            calls.append(platform)
            if platform == 'facebook':
                raise ProviderError('Fixture platform failure')
            return original_render(request, batch, background, platform=platform)

        renderer.render = fail_facebook
        app.state.workflow.run(job)
        assert client.get(f'/api/v1/generation-jobs/{job}').json()['status'] == 'partial'
        partial = client.get('/api/v1/content').json()['items'][0]
        assert set(partial['platform_exports']) == {'instagram', 'linkedin'}
        assert partial['platform_errors'] == {'facebook': 'Fixture platform failure'}
        assert partial['quality']['status'] == 'fail'
        renderer.render = original_render
        retry = client.post(f'/api/v1/generation-jobs/{job}/retry', json={}).json()['id']
        app.state.workflow.run(retry)
        assert client.get(f'/api/v1/generation-jobs/{retry}').json()['status'] == 'succeeded'
        saved = client.get(f"/api/v1/content/{partial['id']}").json()
        assert len(saved['renders']) == 6 and not saved['platform_errors']
        for p in ('instagram', 'linkedin'):
            assert saved['platform_exports'][p] == partial['platform_exports'][p]
        assert fixture.calls == 1
        for p, export in saved['platform_exports'].items():
            assert export['background_asset_id'] == saved['background']
            response = client.get(f"/api/v1/assets/{export['renders'][0]}?download=true")
            assert f'filename="{p}-' in response.headers['content-disposition']
        invalid = deepcopy(saved['concept'])
        invalid['captions'].pop()
        assert client.post(f"/api/v1/content/{saved['id']}/revisions", json={'base_version_id': saved['version_id'], 'concept': invalid}).status_code == 422
        edited = deepcopy(saved['concept'])
        edited['slides'][0]['headline'] = 'Updated across all platforms'
        revision = client.post(f"/api/v1/content/{saved['id']}/revisions", json={'base_version_id': saved['version_id'], 'concept': edited, 'template_id': 'bulletin-v1'}).json()['id']
        app.state.workflow.run(revision)
        history = client.get(f"/api/v1/content/{saved['id']}/versions").json()
        assert history[1] == saved and history[2] == partial
        latest = history[0]
        assert latest['background'] == saved['background']
        assert latest['quality']['approval_status'] == 'unapproved'
        assert latest['quality']['publishing_status'] == 'not_published'
        assert set(latest['platform_exports']) == set(PRESETS)
        assert latest['quality']['status'] != 'fail'
        assert not set(latest['renders']) & set(saved['renders'])
        assert fixture.calls == 1
        image_id = latest['renders'][0]
        image_bytes = client.get(f'/api/v1/assets/{image_id}').content
        # Reconstruct a pre-feature queued snapshot (no export_mode field).
        legacy_job = client.post('/api/v1/generation-jobs', json=payload, headers={'Idempotency-Key': str(uuid4())}).json()['id']
        with Session(app.state.engine) as db:
            row = db.get(GenerationJob, legacy_job)
            snapshot = deepcopy(row.snapshot)
            snapshot['request'].pop('export_mode')
            row.snapshot = snapshot
            db.commit()
        app.state.workflow.run(legacy_job)
        legacy = next(i for i in client.get('/api/v1/content').json()['items'] if i['id'] != saved['id'])
        assert len(legacy['renders']) == 2 and 'platform_exports' not in legacy
        with Image.open(BytesIO(client.get(f"/api/v1/assets/{legacy['renders'][0]}").content)) as image:
            assert image.size == (1080, 1080)
    with TestClient(create_app(settings, start_worker=False)) as client:
        assert client.get(f"/api/v1/content/{saved['id']}/versions").json() == history
        assert client.get(f'/api/v1/assets/{image_id}').content == image_bytes
