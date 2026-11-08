import asyncio
import sys
from base64 import b64encode
from html import escape

from playwright.async_api import async_playwright, Error as PlaywrightError

from ..config import ROOT
from ..templates import template_css
from ..templates.themes import theme_css
from ..templates.platforms import PRESETS, platform_css
from .providers import ProviderError


class PosterRenderer:
    def __init__(self, assets):
        self.assets = assets

    def render(self, request, concept, background_id, platform=None, *, preview_index=None):
        # Windows Selector loops cannot launch Playwright subprocesses.
        # Choose a compatible loop locally without changing
        # the web server's policy or touching its running event loop.
        factory = asyncio.ProactorEventLoop if sys.platform == 'win32' else asyncio.new_event_loop
        try:
            with asyncio.Runner(loop_factory=factory) as runner:
                return runner.run(self._render(request, concept, background_id, platform, preview_index))
        except PlaywrightError:
            raise ProviderError('Chromium could not render the poster. Run .venv\\Scripts\\python.exe -m playwright install chromium, then retry incomplete stages. Saved text and artwork are preserved.') from None

    async def _render(self, request, concept, background_id, platform=None, preview_index=None):
        preset = PRESETS[platform] if platform else {'width': 1080, 'height': 1080, 'preset_id': 'shared-square-v1'}
        width, height = preset['width'], preset['height']
        background = b64encode(self.assets.read(background_id)).decode()
        font_path = ROOT / 'assets/fonts/inter-latin-600-normal.woff2'
        if not font_path.is_file():
            raise ProviderError('Poster font is missing. Restore assets/fonts/inter-latin-600-normal.woff2 before rendering.')
        font = b64encode(font_path.read_bytes()).decode()
        layout_css = template_css(request.template_id) + theme_css(request.background_theme, request.template_id) + platform_css(platform)
        rendered = []
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch()
            try:
                context = await browser.new_context(viewport={'width':width,'height':height}, device_scale_factor=1, java_script_enabled=False)
                await context.route('**/*', lambda route: route.abort())
                page = await context.new_page()
                for index, slide in enumerate(concept.slides):
                    if preview_index is not None and index != preview_index:
                        continue
                    label = {'educational':'LEARN SOMETHING NEW','promotional':'DISCOVER WHAT IS POSSIBLE','announcement':'AN UPDATE WORTH SHARING'}[slide.layout]
                    footer = f'<div class="footer">{index+1:02d} / {len(concept.slides):02d}</div>' if len(concept.slides) > 1 else ''
                    document = f'''<!doctype html><html><head><meta charset="utf-8"><style>
                    @font-face{{font-family:Poster;src:url(data:font/woff2;base64,{font})}}
                    *{{box-sizing:border-box}}body{{margin:0;font-family:Poster,sans-serif;color:white}}
                    .poster{{--brand-color:{request.brand_color};width:{width}px;height:{height}px;position:relative;background:#0f172a;overflow:hidden}}
                    img{{position:absolute;width:100%;height:100%;object-fit:cover}}
                    .shade{{position:absolute;inset:0;background:linear-gradient(90deg,rgba(5,12,28,.97) 0%,rgba(5,12,28,.94) 50%,rgba(5,12,28,.12) 76%,rgba(5,12,28,.05))}}
                    .content{{position:absolute;inset:78px;display:flex;flex-direction:column}}
                    .brand{{font-size:25px;letter-spacing:1px}}.label{{font-size:16px;letter-spacing:4px;color:#cbd5e1;margin-top:90px}}
                    .copy{{max-width:600px;flex:1;min-height:0;padding-top:28px}}h1{{font-size:66px;line-height:1.08;letter-spacing:-2px;margin:0 0 32px;overflow-wrap:anywhere}}
                    .body{{font-size:29px;line-height:1.5;color:#e2e8f0;white-space:pre-wrap;margin:0;overflow-wrap:anywhere}}
                    .cta{{font-size:20px;line-height:1.5;max-width:680px;margin:24px 0;overflow-wrap:anywhere}}
                    .footer{{display:flex;justify-content:flex-end;font-size:14px;letter-spacing:2px;color:#cbd5e1}}
                    .brand{{overflow-wrap:anywhere;flex-shrink:0}}.label,.cta,.footer{{flex-shrink:0}}
                    {layout_css}
                    </style></head><body><div class="poster"><img src="data:image/png;base64,{background}" alt=""><div class="shade"></div><div class="content">
                    <div class="brand">{escape(request.brand_name)}</div><div class="label">{label}</div><div class="copy"><h1>{escape(slide.headline)}</h1><p class="body">{escape(slide.body)}</p></div><p class="cta">{escape(slide.cta)}</p>{footer}</div></div></body></html>'''
                    await page.set_content(document, wait_until='load')
                    await page.evaluate('document.fonts.ready')
                    if not await page.evaluate("document.fonts.check('16px Poster') && [...document.images].every(i=>i.complete && i.naturalWidth>0)"):
                        raise ProviderError('Poster fonts or background did not load.')
                    for headline_size, body_size in [(66,29),(58,27),(50,25),(44,23)]:
                        await page.evaluate("([h,b])=>{document.querySelector('h1').style.fontSize=h+'px';document.querySelector('.body').style.fontSize=b+'px'}",[headline_size,body_size])
                        fits = await page.evaluate("""()=>{
                            const c=document.querySelector('.copy'), body=document.querySelector('.body');
                            const box=document.querySelector('.content').getBoundingClientRect();
                            const nodes=[...document.querySelectorAll('.brand,.label,h1,.body,.cta,.footer')];
                            return body.getBoundingClientRect().bottom<=c.getBoundingClientRect().bottom+1 &&
                                nodes.every(n=>{const r=n.getBoundingClientRect(); return r.left>=box.left-1 && r.right<=box.right+1 && r.top>=box.top-1 && r.bottom<=box.bottom+1 && n.scrollWidth<=n.clientWidth+1;}) &&
                                nodes.slice(1).every((n,i)=>n.getBoundingClientRect().top>=nodes[i].getBoundingClientRect().bottom-1);
                        }""")
                        if fits:
                            break
                    if not fits:
                        raise ProviderError(f'Slide {index+1} text overflows. Shorten the copy and retry.')
                    data = await page.screenshot(type='png')
                    if preview_index is not None:
                        return data
                    rendered.append(self.assets.save(data,'html_chromium',{'template':request.template_id,'background_theme':request.background_theme,'render_style_version':'platforms-v2','background_asset_id':background_id,'slide':index+1,'platform':platform,'preset_id':preset['preset_id'],'width':width,'height':height}))
                return rendered
            finally:
                await browser.close()
