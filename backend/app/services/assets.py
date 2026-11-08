from hashlib import sha256
from io import BytesIO
from uuid import uuid4

from PIL import Image
from sqlalchemy.orm import Session

from ..models import Asset
from .providers import ProviderError

Image.MAX_IMAGE_PIXELS = 25_000_000


class AssetStore:
    def __init__(self, engine, settings):
        self.engine = engine
        self.root = settings.data_dir / 'assets'
        self.root.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def normalize(data: bytes):
        if len(data) > 10 * 1024 * 1024:
            raise ProviderError('Image exceeds the 10 MiB limit.')
        try:
            with Image.open(BytesIO(data), formats=('PNG', 'JPEG', 'WEBP')) as img:
                if img.format not in ('PNG','JPEG','WEBP') or getattr(img, 'n_frames', 1) != 1:
                    raise ValueError('Unsupported image')
                width, height = img.size
                if width * height > 25_000_000 or min(width,height) < 512:
                    raise ValueError('Invalid dimensions')
                img.verify()
            with Image.open(BytesIO(data), formats=('PNG', 'JPEG', 'WEBP')) as img:
                converted = BytesIO()
                img.convert('RGB').save(converted, format='PNG')
                data = converted.getvalue()
        except Exception:
            raise ProviderError('Image is invalid, too small, animated, or exceeds dimension limits.') from None
        if len(data) > 10 * 1024 * 1024:
            raise ProviderError('Normalized image exceeds the 10 MiB limit.')
        return data, width, height

    def save(self, data: bytes, origin: str, metadata=None):
        data, width, height = self.normalize(data)
        asset_id = str(uuid4())
        key = f'{asset_id}.png'
        temporary = self.root / f'{asset_id}.tmp'
        temporary.write_bytes(data)
        temporary.replace(self.root / key)
        with Session(self.engine) as db:
            db.add(Asset(id=asset_id, storage_key=key, checksum=sha256(data).hexdigest(), origin=origin, width=width, height=height, metadata_json=metadata or {}))
            db.commit()
        return asset_id

    def read(self, asset_id):
        with Session(self.engine) as db:
            row = db.get(Asset, asset_id)
            if not row:
                raise ProviderError('Saved image is missing.')
            path = (self.root / row.storage_key).resolve()
            if path.parent != self.root.resolve() or not path.is_file():
                raise ProviderError('Saved image is unavailable.')
            data = path.read_bytes()
            if sha256(data).hexdigest() != row.checksum:
                raise ProviderError('Saved image integrity check failed.')
            return data

    def metadata(self, asset_id):
        with Session(self.engine) as db:
            row = db.get(Asset, asset_id)
            if not row:
                raise ProviderError('Saved image is missing.')
            return dict(row.metadata_json)
