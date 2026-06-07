from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field


class OpenRouterConfig(BaseModel):
    api_key_env: str = "OPENROUTER_API_KEY"
    model_text: str = "google/gemini-2.5-flash-lite"
    model_vision: str = "google/gemini-2.5-flash"
    whisper_svc_url: str = "http://localhost:8742"


class ClaudeCliConfig(BaseModel):
    claude_bin: str = "claude"
    whisper_svc_url: str = "http://localhost:8742"


class EnricherConfig(BaseModel):
    backend: Literal["openrouter", "claude-cli", "local"] = "openrouter"
    openrouter: OpenRouterConfig = Field(default_factory=OpenRouterConfig)
    claude_cli: ClaudeCliConfig = Field(default_factory=ClaudeCliConfig)
    monthly_budget_usd: float | None = None
    user_context: str | None = None


class Config(BaseModel):
    vault: Path
    raw_dir: str = "raw"
    output_dir: str = "captures"
    state_dir: str = ".vault-ingest"
    timezone: str = "UTC"
    enricher: EnricherConfig = Field(default_factory=EnricherConfig)
    private_caption_keywords: list[str] = Field(
        default_factory=lambda: ["private", "internal", "confidential"]
    )

    @property
    def raw_path(self) -> Path:
        p = Path(self.raw_dir)
        return p if p.is_absolute() else self.vault / self.raw_dir

    @property
    def captures_path(self) -> Path:
        p = Path(self.output_dir)
        return p if p.is_absolute() else self.vault / self.output_dir

    @property
    def state_path(self) -> Path:
        p = Path(self.state_dir)
        return p if p.is_absolute() else self.vault / self.state_dir


def load_config(path: Path) -> Config:
    if not path.exists():
        raise FileNotFoundError(f"Config not found: {path}")
    with path.open() as f:
        raw = yaml.safe_load(f)
    return Config(**raw)
