from enum import StrEnum
from pathlib import Path
from urllib.parse import urlparse

from pydantic import BaseModel


class ItemKind(StrEnum):
    URL = "url"
    AUDIO = "audio"
    VIDEO = "video"
    IMAGE = "image"
    DOCUMENT = "document"
    TEXT = "text"


AUDIO_EXTS = {".mp3", ".m4a", ".wav", ".ogg", ".oga", ".flac", ".aac"}
VIDEO_EXTS = {".mp4", ".mov", ".webm", ".mkv", ".avi"}
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".heic", ".gif"}
DOCUMENT_EXTS = {".pdf", ".docx", ".txt", ".md"}

_PLATFORM_HOSTS = {
    "tiktok": ["tiktok.com", "vm.tiktok.com", "vt.tiktok.com"],
    "youtube": ["youtube.com", "youtu.be", "m.youtube.com"],
    "instagram": ["instagram.com"],
    "x": ["twitter.com", "x.com"],
    "reddit": ["reddit.com", "redd.it"],
    "bluesky": ["bsky.app", "bsky.social"],
}


class Item(BaseModel):
    kind: ItemKind
    source: str  # URL string or local file path string
    platform: str | None = None  # for URL items
    local_path: Path | None = None  # for file items


def _hostname_to_platform(host: str) -> str:
    host = host.lower().lstrip(".")
    for platform, hosts in _PLATFORM_HOSTS.items():
        if any(host == h or host.endswith("." + h) for h in hosts):
            return platform
    return "generic"


def classify_url(url: str) -> Item:
    parsed = urlparse(url)
    return Item(
        kind=ItemKind.URL,
        source=url,
        platform=_hostname_to_platform(parsed.netloc),
    )


def classify_path(path: Path) -> Item:
    suffix = path.suffix.lower()

    if suffix == ".url":
        url = path.read_text().strip()
        return classify_url(url)
    if suffix == ".txt":
        text = path.read_text().strip()
        first_line = text.splitlines()[0] if text else ""
        if first_line.startswith(("http://", "https://")):
            return classify_url(first_line)

    if suffix in AUDIO_EXTS:
        kind = ItemKind.AUDIO
    elif suffix in VIDEO_EXTS:
        kind = ItemKind.VIDEO
    elif suffix in IMAGE_EXTS:
        kind = ItemKind.IMAGE
    elif suffix in DOCUMENT_EXTS:
        kind = ItemKind.DOCUMENT
    else:
        kind = ItemKind.TEXT

    return Item(kind=kind, source=str(path), local_path=path)
