"""Explicit test text fixture; real local artwork, Chromium and persistence."""
from copy import deepcopy
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.app.config import Settings
from backend.tests.app_fixture import create_app
from backend.app.models import Asset, GenerationJob
from backend.app.services.providers import ProviderError


class FixtureText:
    calls = 0

    def generate(self, prompt, provider, model):
        self.calls += 1
        slide = {'headline': 'Learn from data', 'body': 'Machine learning uses data to train models.', 'cta': 'Explore the report', 'layout': 'educational', 'claim_ids': ['c1']}
        return {'concepts': [{'title': 'Test-only carousel', 'captions': [{'platform': 'instagram', 'text': 'Learn about machine learning.', 'claim_ids': ['c1'], 'hashtags': ['#MachineLearning', '#Learning', '#Data']}], 'slides': [slide, deepcopy(slide)], 'background_design': 'Abstract blue shapes', 'warnings': []}]}


def test_carousel_retry_revision_and_restart(tmp_path):
    settings = Settings(_env_file=None, app_data_dir=tmp_path, content_api_key='', pollinations_api_key='')
    app = create_app(settings, start_worker=False)
    fixture = FixtureText()
    with TestClient(app) as client:
        reports = client.get('/api/v1/research-reports').json()
        assert len(reports) == 5 and all(r['origin'] == 'demo' for r in reports)
        report = next(r for r in reports if r['id'].endswith('001'))
        # Use the fixture's actual source ID, not an invented reference.
        assert report['claims'][0]['id'] == 'c1'
        payload = {'topic': report['topic'], 'report_id': report['id'], 'slide_count': 2}
        headers = {'Idempotency-Key': str(uuid4())}
        created = client.post('/api/v1/generation-jobs', json=payload, headers=headers)
        assert created.status_code == 202
        job = created.json()['id']
        assert client.post('/api/v1/generation-jobs', json=payload, headers=headers).json()['id'] == job
        assert client.post('/api/v1/generation-jobs', json={**payload, 'topic': 'Changed'}, headers=headers).status_code == 409
        app.state.workflow.agent.text_service = fixture
        app.state.workflow.run(job)
        assert client.get(f'/api/v1/generation-jobs/{job}').json()['status'] == 'partial'
        old = client.get('/api/v1/content').json()['items'][0]
        assert old['artwork_error'] and not old.get('renders')
        retry = client.post(f'/api/v1/generation-jobs/{job}/retry', json={'artwork_mode': 'application_gradient'}).json()['id']
        app.state.workflow.run(retry)
        assert client.get(f'/api/v1/generation-jobs/{retry}').json()['status'] == 'succeeded'
        assert fixture.calls == 1
        saved = client.get(f"/api/v1/content/{old['id']}").json()
        assert len(saved['renders']) == 2 and saved['version_number'] == 2
        with Session(app.state.engine) as db:
            for asset_id in saved['renders']:
                assert db.get(Asset, asset_id).metadata_json['background_asset_id'] == saved['background']
        original = deepcopy(saved)
        concept = deepcopy(saved['concept'])
        concept['slides'][0]['headline'] = 'An edited headline'
        concept['captions'][0]['hashtags'] = ['#EditedTag']
        edit = {'base_version_id': saved['version_id'], 'concept': concept, 'template_id': 'bulletin-v1'}
        revision = client.post(f"/api/v1/content/{saved['id']}/revisions", json=edit).json()['id']
        app.state.workflow.run(revision)
        assert client.get(f'/api/v1/generation-jobs/{revision}').json()['status'] == 'succeeded'
        assert client.post(f"/api/v1/content/{saved['id']}/revisions", json=edit).status_code == 409
        history = client.get(f"/api/v1/content/{saved['id']}/versions").json()
        assert history[1] == original and history[2] == old
        assert history[0]['background'] == original['background']
        assert history[0]['template_version'] == 'bulletin-v1'
        assert history[0]['concept']['captions'][0]['hashtags'] == ['#EditedTag']
        assert history[1]['concept']['captions'][0]['hashtags'] == ['#MachineLearning', '#Learning', '#Data']
        assert history[0]['request']['template_id'] == 'bulletin-v1'
        assert history[1]['template_version'] == 'editorial-v1'
        assert fixture.calls == 1
        with app.state.engine.begin() as connection:
            with pytest.raises(IntegrityError):
                connection.execute(text('UPDATE content_versions SET version_number=99'))
        image_id = history[0]['renders'][0]
        image = client.get(f'/api/v1/assets/{image_id}').content
        assert image.startswith(b'\x89PNG')
    with TestClient(create_app(settings, start_worker=False)) as client:
        assert client.get(f"/api/v1/content/{saved['id']}/versions").json() == history
        assert client.get(f'/api/v1/assets/{image_id}').content == image
        assert len(client.get('/api/v1/research-reports').json()) == 5


def test_failed_live_provider_does_not_become_fixture(tmp_path):
    settings = Settings(_env_file=None, app_data_dir=tmp_path, content_api_key='')
    app = create_app(settings, start_worker=False)
    with TestClient(app) as client:
        report = client.get('/api/v1/research-reports').json()[0]
        job = client.post('/api/v1/generation-jobs', json={'topic': report['topic'], 'report_id': report['id']}, headers={'Idempotency-Key': str(uuid4())}).json()['id']
        app.state.workflow.run(job)
        result = client.get(f'/api/v1/generation-jobs/{job}').json()
        assert result['status'] == 'failed' and 'CONTENT_API_KEY' in result['error']
        assert client.get('/api/v1/content').json()['total'] == 0
