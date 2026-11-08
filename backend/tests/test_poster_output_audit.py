"""Exported pixels and geometry, independent of the workspace preview UI."""
from io import BytesIO
from uuid import uuid4

import pytest
from PIL import Image, ImageChops
from playwright.async_api import Page

from backend.app.config import ROOT
from backend.app.contracts import GenerationRequest
from backend.app.templates import TEMPLATES
from backend.app.templates.platforms import PRESETS
from backend.tests.test_templates import rendering, concept


@pytest.mark.parametrize('template',TEMPLATES)
@pytest.mark.parametrize('platform',PRESETS)
@pytest.mark.parametrize('theme',['dark','light','colorful'])
def test_every_slide_keeps_header_and_fits_export(rendering,monkeypatch,template,platform,theme):
    _,store,artwork,renderer=rendering
    request=GenerationRequest(topic='Poster output audit fixture',report_id=uuid4(),
        template_id=template,background_theme=theme,artwork_mode='application_gradient',slide_count=3)
    batch=concept(3)
    batch.slides[1].headline='Heat Pump Fundamentals'
    batch.slides[1].body=('An electric air-source heat pump moves heat between outdoor and indoor air '
        'to heat and cool a home. It moves heat rather than generating it. '
        'Performance depends on the equipment, the building and outdoor conditions. '
        'Compare reliable evidence and ask an installer about your specific needs.')
    batch.slides[2].headline='Cold-Climate Performance'
    batch.slides[2].body='\n'.join(['Check the equipment specifications.',
        'Compare performance at low outdoor temperatures.',
        'Ask about backup heating for the coldest days.'])
    background=artwork.generate(request,batch,1)
    screenshot=Page.screenshot
    headers=[]

    async def checked_capture(page,*args,**kwargs):
        metrics=await page.evaluate('''()=>{
            const nodes=[...document.querySelectorAll('.brand,.label,h1,.body,.cta,.footer')];
            return {scroll:[scrollX,scrollY],width:innerWidth,height:innerHeight,
                nodes:nodes.map(n=>{const r=n.getBoundingClientRect(),s=getComputedStyle(n);
                    return {text:n.textContent,x:r.x,y:r.y,right:r.right,bottom:r.bottom,
                        width:r.width,height:r.height,font:parseFloat(s.fontSize),
                        display:s.display,visibility:s.visibility,opacity:s.opacity};})};
        }''')
        assert metrics['scroll']==[0,0],metrics
        for node in metrics['nodes']:
            assert node['display']!='none' and node['visibility']=='visible' and float(node['opacity'])>0
            assert 0<=node['x']<node['right']<=metrics['width']
            assert 0<=node['y']<node['bottom']<=metrics['height']
        brand,label,headline,body,*_=metrics['nodes']
        assert brand['text']=='Content Studio' and label['text']=='LEARN SOMETHING NEW'
        assert brand['font']>=25 and headline['font']>=44 and body['font']>=23
        data=await screenshot(page,*args,**kwargs)
        with Image.open(BytesIO(data)) as img:
            assert img.size==(PRESETS[platform]['width'],PRESETS[platform]['height'])
            # Same background and header must produce identical exported header
            # pixels even after a previous slide has used a different text fit.
            header=img.crop((0,0,img.width,int(label['bottom'])+1)).copy()
            if headers: assert ImageChops.difference(headers[0],header).getbbox() is None
            headers.append(header)
        return data

    monkeypatch.setattr(Page,'screenshot',checked_capture)
    outputs=renderer.render(request,batch,background,platform=platform)
    assert len(headers)==len(outputs)==3
    folder=ROOT/'data/verification/poster-output-audit'
    folder.mkdir(parents=True,exist_ok=True)
    for index,asset_id in enumerate(outputs):
        assert store.metadata(asset_id)['background_asset_id']==background
        (folder/f'{platform}-{template}-{theme}-{index+1}.png').write_bytes(store.read(asset_id))
    preview=renderer.render(request,batch,background,platform=platform,preview_index=1)
    with Image.open(BytesIO(preview)) as draft,Image.open(BytesIO(store.read(outputs[1]))) as saved:
        assert draft.size==saved.size
        assert ImageChops.difference(draft.convert('RGB'),saved.convert('RGB')).getbbox() is None,'Preview pixels differ from saved export'
