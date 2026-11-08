from io import BytesIO
from urllib.parse import quote

import httpx
from PIL import Image

from .providers import ProviderError, request_with_retries
from .background_check import BackgroundTextCheck


PALETTES = {
    'light': 'bright ivory, soft pastel accents, airy daylight, pale unmarked surfaces',
    'dark': 'deep charcoal, rich accent colors, low-key cinematic lighting',
    'colorful': 'vivid complementary hues, lively saturated accents, bright balanced lighting',
}


def background_prompt(request, concept, negative_prompt):
    # Subject information comes through the LLM's visual scene, not a quoted
    # topic/headline which an image model might attempt to typeset.
    prompt = (f'Scene: {concept.background_design}. '
            f'Style: {request.visual_style}. Palette: {PALETTES[request.background_theme]}. '
            f'Subtle {request.brand_color} accent. '
            'Square illustration with a large, recognizable subject centered in the right half, fully inside the frame. '
            'Quiet open space on the left for separately rendered text. '
            'Follow the scene subject; no unrelated props. Unmarked surfaces, no typography. '
            'Exclude: ' + negative_prompt)
    # Application transport budgets, not a claim about a universal provider limit.
    # Preserve configured exclusions in full; never silently drop safety instructions.
    if len(prompt)>2000 or len(quote(prompt,safe=''))>6000:
        raise ProviderError('Artwork brief exceeds the application prompt budget. Shorten the visual style, scene or configured exclusions before retrying.')
    return prompt



class ArtworkService:
    def __init__(self, settings, assets, transport=None, text_check=None):
        self.settings, self.assets, self.transport = settings, assets, transport
        self.text_check = text_check or BackgroundTextCheck()

    def generate(self, request, concept, seed):
        if request.artwork_mode == 'application_gradient':
            color = tuple(int(request.brand_color[i:i+2],16) for i in (1,3,5))
            image = Image.new('RGB',(1080,1080))
            pixels = image.load()
            for y in range(1080):
                for x in range(1080):
                    t = (x+y)/2160
                    if request.creative_mode == 'distinct_platforms':
                        t = (t + (seed % 997)/997)/2
                    if request.background_theme == 'light':
                        pixels[x,y] = tuple(int(255*(.92-.15*t)+v*(.08+.15*t)) for v in color)
                    elif request.background_theme == 'colorful':
                        pixels[x,y] = tuple(int(v*(1-t)+(255-v)*t) for v in color)
                    else:
                        pixels[x,y] = tuple(int(v*(.25+.55*t)) for v in color)
            stream = BytesIO()
            image.save(stream,format='PNG')
            return self.assets.save(stream.getvalue(),'application_gradient',{'brand_color':request.brand_color,'theme':request.background_theme,'text_check':{'status':'not_applicable','method':'application_drawn_gradient'}})
        key = self.settings.pollinations_api_key.get_secret_value()
        model = self.settings.pollinations_model
        if not key or not model:
            raise ProviderError('Configure POLLINATIONS_API_KEY and POLLINATIONS_MODEL, or explicitly retry with an application gradient.')
        self.text_check.ready()  # Fail before consuming credits if local OCR cannot load.
        prompt = background_prompt(request, concept, self.settings.pollinations_negative_prompt)
        url = 'https://gen.pollinations.ai/image/' + quote(prompt, safe='')
        with httpx.Client(timeout=120, transport=self.transport) as client:
            for attempt in range(self.settings.artwork_max_attempts):
                attempt_seed = (seed + attempt) % 2147483647
                response = request_with_retries(client,'GET',url, max_attempts=1, headers={'Authorization':f'Bearer {key}'}, params={'model':model,'width':1080,'height':1080,'seed':attempt_seed})
                data, _, _ = self.assets.normalize(response.content)
                check = self.text_check.inspect(data)
                asset_id = self.assets.save(data,'pollinations',{'model':model,'seed':attempt_seed,'theme':request.background_theme,'positive_prompt':prompt,'negative_prompt':self.settings.pollinations_negative_prompt,'negative_strategy':'prompt_exclusions','text_check':check,'attempt':attempt+1})
                if check['status'] == 'no_text_detected':
                    return asset_id
            raise ProviderError(f'Background rejected: possible lettering detected in {self.settings.artwork_max_attempts} attempts. Text is preserved. Retry artwork or explicitly choose a gradient.')
