from pathlib import Path
from typing import Literal

from pydantic import SecretStr, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[2]
Provider = Literal['gemini', 'groq', 'openrouter', 'openai']


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / '.env', extra='ignore')
    app_data_dir: Path = ROOT / 'data'
    content_provider: Provider = 'groq'
    content_model: str = 'openai/gpt-oss-120b'
    content_api_key: SecretStr = SecretStr('')
    pollinations_api_key: SecretStr = SecretStr('')
    pollinations_model: str = ''
    artwork_max_attempts: int = Field(default=2, ge=1, le=3)
    pollinations_negative_prompt: str = 'text, typography, letters, words, numbers, captions, subtitles, logos, watermarks, signatures, fake writing, gibberish, random characters, text-like patterns, UI elements, labels, signs containing text, poster text, finished poster designs, typography overlays'
    app_allowed_origins: list[str] = ['http://127.0.0.1:8001', 'http://localhost:8001']

    @property
    def data_dir(self) -> Path:
        path = self.app_data_dir
        resolved = (path if path.is_absolute() else ROOT / path).resolve()
        if not resolved.is_relative_to(ROOT.resolve()) or resolved == ROOT.resolve():
            raise ValueError('APP_DATA_DIR must be a subdirectory inside this standalone project.')
        return resolved

    @property
    def database_path(self) -> Path:
        return self.data_dir / 'app.sqlite3'
