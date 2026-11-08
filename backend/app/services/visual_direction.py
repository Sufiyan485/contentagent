"""Small topic-grounded art directions, not generated assets or factual evidence."""
import re


NODE_SCENE=re.compile(r'\bnodes?\b|neural mesh|glowing web|connected (?:dots|spheres)|wireframe brain|network of lights',re.I)
NETWORK_TOPIC=re.compile(r'neural networks?|network (?:topology|architecture|security)|computer networks?|graph (?:theory|databases?|neural)|knowledge graphs?',re.I)

# Only the selected short direction enters the LLM prompt, never this whole catalog.
DIRECTIONS=(
    (r'\bpython\b|\bprogramming\b|\bcoding\b|software development', (
        'interlocking unmarked modular pieces assembling a clean mechanical sequence',
        'a compact mechanism turning a small input into an orderly sequence of fitted parts',
        'stackable reusable components fitting precisely into a working structure')),
    (r'\bai agents?\b|agentic|autonomous agents?', (
        'an unmarked robotic gripper arranging physical task pieces along a clear route',
        'a small autonomous mechanism selecting a tool to complete a physical task',
        'cooperating mechanical arms passing an object through distinct workstations')),
    (r'data science|data analy|statistics', (
        'mixed physical pieces passing through a sorter into clearly organized groups',
        'a prism separating a mixed stream into distinct ordered bands',
        'a precision lens revealing an orderly pattern within mixed material')),
    (r'machine learning|\bml\b', (
        'a sorting mechanism directing differently shaped objects into matching groups',
        'a mechanical guide adjusting its path to fit a sequence of physical shapes',
        'a sculptural mold adapting to a collection of varied objects')),
    (r'cybersecurity|authentication|phishing|password', (
        'two distinct physical keys operating one layered protective lock',
        'a solid shield protecting a small valuable object from approaching fragments',
        'interlocking protective barriers enclosing a secure chamber')),
)


def nodes_relevant(request,report):
    explicit=request.background_subject or ''
    return bool(NODE_SCENE.search(explicit) or NETWORK_TOPIC.search(explicit+' '+request.topic+' '+report.topic))


def visual_direction(request,report,creative_context=None):
    if request.background_subject:
        return 'Use the user visual subject preference if relevant to the report; all surfaces unmarked.'
    if nodes_relevant(request,report):
        return 'Depict the specific network structure discussed in the report, not a decorative glowing cloud.'
    topic=request.topic+' '+report.topic
    offset={'instagram':0,'facebook':1,'linkedin':2}.get(request.platforms[0],0)
    offset+=(creative_context or {}).get('concept_number',1)-1
    for pattern,options in DIRECTIONS:
        if re.search(pattern,topic,re.I):
            return 'Interpret the concept through '+options[offset%len(options)]+'. No generic node web.'
    return 'Choose a recognizable physical subject or process from the concept itself. Do not default to a glowing node web.'
