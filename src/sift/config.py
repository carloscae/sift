from pathlib import Path

import yaml
from pydantic import BaseModel, Field


class OpenRouterConfig(BaseModel):
    api_key_env: str = "OPENROUTER_API_KEY"
    model_stt: str = "groq/whisper-large-v3-turbo"
    model_text: str = "google/gemini-2.5-flash-lite"
    model_vision: str = "google/gemini-2.5-flash"


class EnricherConfig(BaseModel):
    backend: str = "openrouter"
    openrouter: OpenRouterConfig = Field(default_factory=OpenRouterConfig)
    monthly_budget_usd: float | None = None


class Config(BaseModel):
    vault: Path
    raw_dir: str = "raw"
    output_dir: str = "captures"
    state_dir: str = ".vault-ingest"
    raw_ttl_days: int = 7
    enricher: EnricherConfig = Field(default_factory=EnricherConfig)
    private_caption_keywords: list[str] = Field(
        default_factory=lambda: ["private", "internal", "confidential"]
    )

    @property
    def raw_path(self) -> Path:
        return self.vault / self.raw_dir

    @property
    def captures_path(self) -> Path:
        return self.vault / self.output_dir

    @property
    def state_path(self) -> Path:
        return self.vault / self.state_dir


def load_config(path: Path) -> Config:
    if not path.exists():
        raise FileNotFoundError(f"Config not found: {path}")
    with path.open() as f:
        raw = yaml.safe_load(f)
    return Config(**raw)
