from copy import deepcopy

import pytest
from pydantic import ValidationError

from backend.app.agents.content import ContentCreationAgent
from backend.app.config import ROOT
from backend.app.contracts import Caption, GenerationRequest, ResearchReport
from backend.app.services.providers import ProviderError
from backend.tests.test_content import FixtureText


def test_legacy_caption_and_normalization():
    assert Caption(platform='instagram', text='Old caption #Existing').hashtags == []
    assert Caption(platform='linkedin', text='Caption', hashtags=[' Data ', '#Learning']).hashtags == ['#Data', '#Learning']


@pytest.mark.parametrize('tags', [['#Data', '#data'], ['#two words'], ['#'], ['#bad-tag'], ['#' + 'x'*51], ['#x'+str(i) for i in range(11)], 'not a list', [123]])
def test_invalid_hashtags(tags):
    with pytest.raises(ValidationError):
        Caption(platform='instagram', text='Caption', hashtags=tags)


def setup_agent(tags, text='Learning about data.'):
    report = ResearchReport.model_validate_json((ROOT / 'tests/fixtures/reports/01-machine-learning.json').read_text())
    request = GenerationRequest(topic=report.topic, report_id=report.id, slide_count=2)
    data = FixtureText().generate('', '', '')
    data['concepts'][0]['captions'][0].update(hashtags=tags, text=text)

    class Service:
        calls = 0
        def generate(self, prompt, provider, model):
            self.calls += 1
            return deepcopy(data)

    service = Service()
    return ContentCreationAgent(service), service, request, report


def test_wrong_generated_count_is_rejected_after_correction_attempt():
    agent, service, request, report = setup_agent(['#Data'])
    with pytest.raises(ProviderError):
        agent.generate(request, report, 'groq', 'test')
    assert service.calls == 2


def test_zero_tags_and_hashtags_not_in_caption():
    agent, _, request, report = setup_agent([])
    request.hashtag_count = 0
    assert agent.generate(request, report, 'groq', 'test').concepts[0].captions[0].hashtags == []
    agent, _, request, report = setup_agent(['#Data', '#Learning', '#AI'], text='Learn more #Data')
    with pytest.raises(ProviderError):
        agent.generate(request, report, 'groq', 'test')
