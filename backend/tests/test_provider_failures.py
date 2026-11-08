"""HTTP failure fixtures; no live provider calls or paid fallbacks."""
import httpx
import pytest

from backend.app.config import Settings
from backend.app.services.providers import ProviderError, TextService


@pytest.mark.parametrize('status,attempts', [(401,1), (403,1), (402,1), (429,3), (500,3)])
def test_provider_failures_are_bounded_and_sanitized(monkeypatch, status, attempts):
    monkeypatch.setattr('backend.app.services.providers.time.sleep', lambda _: None)
    calls = []
    def respond(request):
        calls.append(request)
        return httpx.Response(status, text='private upstream response SECRET')
    service = TextService(Settings(_env_file=None, content_api_key='fixture-secret', content_model='fixture-model'), httpx.MockTransport(respond))
    with pytest.raises(ProviderError) as error:
        service.generate('Fixture', 'groq', 'fixture-model')
    assert len(calls) == attempts
    assert 'SECRET' not in str(error.value) and 'fixture-secret' not in str(error.value)
    assert {str(call.url.host) for call in calls} == {'api.groq.com'}


def test_provider_timeout_is_bounded(monkeypatch):
    monkeypatch.setattr('backend.app.services.providers.time.sleep', lambda _: None)
    calls = []
    def respond(request):
        calls.append(request)
        raise httpx.ReadTimeout('SECRET', request=request)
    service = TextService(Settings(_env_file=None, content_api_key='fixture-secret', content_model='fixture-model'), httpx.MockTransport(respond))
    with pytest.raises(ProviderError, match='timed out'):
        service.generate('Fixture', 'groq', 'fixture-model')
    assert len(calls) == 3
