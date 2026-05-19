from abc import ABC, abstractmethod
from pathlib import Path

from pydantic import BaseModel, Field


class TranscriptResult(BaseModel):
    text: str
    model: str
    cost_usd: float = 0.0
    duration_sec: float | None = None


class CaptionResult(BaseModel):
    caption: str
    ocr_text: str = ""
    model: str
    cost_usd: float = 0.0
    tags: list[str] = Field(default_factory=list)


class OCRResult(BaseModel):
    text: str
    model: str
    cost_usd: float = 0.0


class SummaryResult(BaseModel):
    title: str
    summary: str
    tags: list[str] = Field(default_factory=list)
    model: str
    cost_usd: float = 0.0


class Enricher(ABC):
    """Pluggable backend for STT / vision / summarisation."""

    @abstractmethod
    def transcribe(self, audio_path: Path) -> TranscriptResult: ...

    @abstractmethod
    def caption(self, image_path: Path) -> CaptionResult: ...

    @abstractmethod
    def summarise(self, text: str, context: dict | None = None) -> SummaryResult: ...
