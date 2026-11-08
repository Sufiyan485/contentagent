"""Allowlisted application-owned poster layouts. Never load a caller-supplied path."""
from pathlib import Path
from typing import Literal

TemplateId = Literal['editorial-v1', 'spotlight-v1', 'bulletin-v1']

TEMPLATES = {
    'editorial-v1': {'name': 'Editorial', 'description': 'Left-aligned copy with room for artwork on the right.'},
    'spotlight-v1': {'name': 'Spotlight', 'description': 'Centered headline and copy inside a dark framed composition.'},
    'bulletin-v1': {'name': 'Bulletin', 'description': 'A bright information card with a brand-color accent.'},
}


def template_css(template_id: TemplateId) -> str:
    if template_id not in TEMPLATES:
        raise ValueError('Unknown poster template')
    return (Path(__file__).parent / f'{template_id}.css').read_text(encoding='utf-8')
