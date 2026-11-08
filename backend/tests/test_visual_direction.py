from uuid import uuid4
from types import SimpleNamespace
import json
import pytest
from fastapi.testclient import TestClient
from backend.app.config import Settings
from backend.app.contracts import GenerationRequest, ResearchReport
from backend.app.agents.content import ContentCreationAgent
from backend.app.services.visual_direction import visual_direction, nodes_relevant
from backend.app.services.artwork import background_prompt
from backend.app.services.providers import ProviderError
from backend.tests.app_fixture import create_app
from backend.tests.test_distinct_creatives import DistinctText
from backend.tests.test_artwork import concept


def request(topic,**kwargs):
    return GenerationRequest(topic=topic,report_id=uuid4(),**kwargs)


def test_topics_platforms_and_concepts_get_short_distinct_directions():
    topics=['Python basics','AI agents','Data science','Machine learning','Cybersecurity']
    directions=[visual_direction(request(t),SimpleNamespace(topic=t)) for t in topics]
    assert len(set(directions))==5
    assert all(len(d)<230 for d in directions)
    assert 'modular pieces' in directions[0] and 'robotic gripper' in directions[1]
    assert 'sorter' in directions[2]
    report=SimpleNamespace(topic='Python basics')
    variants=[visual_direction(request(report.topic,platforms=[p]),report) for p in ('instagram','facebook','linkedin')]
    assert len(set(variants))==3
    assert visual_direction(request(report.topic),report,{'concept_number':2})!=variants[0]


def test_network_exception_and_user_preference():
    for topic in ('Python basics','Data science','AI agents','Machine learning'):
        assert not nodes_relevant(request(topic),SimpleNamespace(topic=topic))
    assert nodes_relevant(request('Neural networks'),SimpleNamespace(topic='Neural networks'))
    custom=request('Python basics',background_subject='Interlocking gears')
    assert 'user visual subject' in visual_direction(custom,SimpleNamespace(topic=custom.topic))
    assert nodes_relevant(request('Python basics',background_subject='A network of connected nodes'),SimpleNamespace(topic='Python basics'))


def test_generic_nodes_corrected_before_any_artwork(tmp_path):
    app=create_app(Settings(_env_file=None,app_data_dir=tmp_path),start_worker=False)
    with TestClient(app) as client:
        report=ResearchReport.model_validate(client.get('/api/v1/research-reports').json()[0]).model_copy(update={'topic':'Python basics'})
    class Nodes(DistinctText):
        correct=True
        def generate(self,prompt,*args):
            result=super().generate(prompt,*args)
            result['concepts'][0]['background_design']='Interlocking unmarked modules' if self.correct and 'Previous response failed validation' in prompt else 'A glowing web of connected nodes'
            assert 'modular pieces' in json.JSONDecoder().raw_decode(prompt.split('\n',1)[1])[0]['visual_direction']
            return result
    service=Nodes()
    batch=ContentCreationAgent(service).generate(request('Python basics'),report,'groq','fixture')
    assert service.calls==2 and batch.concepts[0].background_design=='Interlocking unmarked modules'
    service=Nodes();service.correct=False
    with pytest.raises(ProviderError,match='validation'):
        ContentCreationAgent(service).generate(request('Python basics'),report,'groq','fixture')


def test_art_prompt_bounded_with_complete_no_text_exclusions():
    settings=Settings(_env_file=None)
    prompt=background_prompt(request('Python basics'),concept(),settings.pollinations_negative_prompt)
    assert settings.pollinations_negative_prompt in prompt
    for excluded in ('letters','numbers','logos','watermarks','fake writing'):
        assert excluded in prompt
    assert len(prompt)<1200 and 'fully inside the frame' in prompt
    with pytest.raises(ProviderError,match='prompt budget'):
        background_prompt(request('Python basics',visual_style='x'*5000),concept(),settings.pollinations_negative_prompt)
    with pytest.raises(ProviderError,match='prompt budget'):
        background_prompt(request('Python basics'),concept(),'letters, '*1000)
