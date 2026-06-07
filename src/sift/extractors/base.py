import shutil
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

MediaType = Literal["audio", "video", "image", "text", "mixed"]


class ExtractResult(BaseModel):
    platform: str
    media_type: MediaType
    media_path: Path | None = None
    text_content: str | None = None
    title: str = "Untitled"
    metadata: dict = Field(default_factory=dict)
    cost_usd: float = 0.0


class ExtractFailure(BaseModel):
    url: str
    platform: str
    error_class: Literal[
        "anti-scrape", "auth-wall", "rate-limited", "site-changed", "network", "unknown"
    ]
    error_detail: str
    suggested_t2: str | None = None


class Extractor(ABC):
    platform: str

    @abstractmethod
    def can_handle(self, hostname: str) -> bool:
        """Return True if this extractor handles the given hostname."""

    @abstractmethod
    def extract(self, url: str, work_dir: Path) -> ExtractResult:
        """Run the extraction; raise on failure (caller wraps in ExtractFailure)."""


_REGISTRY: list[Extractor] = []


def register_extractor(extractor: Extractor) -> None:
    _REGISTRY.append(extractor)


def get_extractor(hostname: str) -> Extractor | None:
    for ex in _REGISTRY:
        if ex.can_handle(hostname):
            return ex
    return None


def all_extractors() -> list[Extractor]:
    return list(_REGISTRY)


def clear_registry() -> None:
    """Drop all registered extractors. For test isolation."""
    _REGISTRY.clear()


def resolve_ffmpeg_location() -> str | None:
    """Directory containing ffmpeg/ffprobe, or None if not found.

    yt-dlp's FFmpegExtractAudio postprocessor locates ffmpeg via PATH. Under
    launchd and other minimal-PATH supervisors, /opt/homebrew/bin is absent
    from PATH, so resolve it explicitly and pass ffmpeg_location to yt-dlp.
    """
    found = shutil.which("ffmpeg")
    if found:
        return str(Path(found).parent)
    for candidate in ("/opt/homebrew/bin", "/usr/local/bin"):
        if (Path(candidate) / "ffmpeg").is_file():
            return candidate
    return None
