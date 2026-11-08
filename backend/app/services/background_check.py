"""Local OCR gate for image-model backgrounds, never for final poster text."""
from threading import Lock
from io import BytesIO

from PIL import Image, ImageDraw, ImageFont

from .providers import ProviderError


def evaluate_regions(detected, recognized):
    # Recognition catches readable letters even in weaker detection boxes;
    # strong unrecognized regions still block gibberish/fake-writing shapes.
    scores = [] if detected.scores is None else list(detected.scores)
    texts = [] if getattr(recognized, 'txts', None) is None else list(recognized.txts)
    recognized_scores = [] if recognized.scores is None else list(recognized.scores)
    readable = sum(1 for text, confidence in zip(texts, recognized_scores) if confidence >= .6 and any(c.isalnum() for c in text))
    strong = sum(1 for score in scores if score >= .8)
    count = max(readable, strong)
    return {'method': 'rapidocr-detection-recognition-v1', 'status': 'rejected' if count else 'no_text_detected',
            'regions': count, 'candidate_regions': len(scores), 'detection_threshold': .8, 'recognition_threshold': .6,
            'limitation': 'Automated detection can miss stylized writing or flag visual patterns; human review is still required.'}


class BackgroundTextCheck:
    def __init__(self):
        self._engine = None
        self._lock = Lock()

    def ready(self):
        with self._lock:
            if self._engine is None:
                try:
                    from rapidocr import RapidOCR
                    engine = RapidOCR()
                    probe = BytesIO()
                    image = Image.new('RGB', (512, 512), 'white')
                    ImageDraw.Draw(image).text((25,200),'OCR CHECK',fill='black',font=ImageFont.load_default(size=50))
                    image.save(probe, format='PNG')
                    engine(probe.getvalue(), use_cls=True, use_rec=True)
                    self._engine = engine
                except Exception:
                    raise ProviderError('Background text detection is unavailable. Install backend requirements in .venv and retry. Artwork was not requested.') from None

    def inspect(self, image_bytes):
        self.ready()
        try:
            with self._lock:
                detected = self._engine(image_bytes, use_cls=False, use_rec=False)
                recognized = self._engine(image_bytes, use_cls=True, use_rec=True) if detected.boxes is not None else detected
            return evaluate_regions(detected, recognized)
        except Exception:
            raise ProviderError('Background text detection failed. The image was not accepted; retry after checking the local OCR installation.') from None
