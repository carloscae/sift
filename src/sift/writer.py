from datetime import UTC, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from pydantic import BaseModel, Field
from slugify import slugify as _ext_slugify

from sift.config import Config
from sift.version import __version__


class CaptureData(BaseModel):
    item_id: str
    source: str
    platform: str | None = None
    subtype: str  # "video-url" | "voice-note" | "photo" | "url-article" | etc
    title: str = "Untitled"
    summary: str | None = None
    transcript_or_ocr: str | None = None
    tags: list[str] = Field(default_factory=list)
    enriched_by: str | None = None
    cost_usd: float | None = None
    models: dict[str, str] = Field(default_factory=dict)


def _slugify(title: str, max_len: int = 50) -> str:
    s = _ext_slugify(title, max_length=max_len, word_boundary=True, save_order=True)
    return s or "untitled"


def write_capture(config: Config, data: CaptureData) -> Path:
    config.captures_path.mkdir(parents=True, exist_ok=True)

    now = datetime.now(ZoneInfo(config.timezone))
    date = now.strftime("%Y-%m-%d")
    slug = _slugify(data.title)
    base_filename = f"{date}-{slug}-{data.item_id[:6]}.md"
    out_path = config.captures_path / base_filename
    if out_path.exists():
        for attempt in range(2, 11):
            candidate = config.captures_path / f"{date}-{slug}-{data.item_id[:6]}-{attempt}.md"
            if not candidate.exists():
                out_path = candidate
                break
        else:
            raise FileExistsError(
                f"Could not find a unique filename after 10 attempts for base '{base_filename}'"
            )

    status = "raw" if data.enriched_by else "pending-enrichment"
    tags = ["clipping", *data.tags]

    frontmatter_lines = [
        "---",
        "type: clipping",
        f"subtype: {data.subtype}",
        f"date: {date}",
        f"source: {data.source}",
    ]
    if data.platform:
        frontmatter_lines.append(f"platform: {data.platform}")
    frontmatter_lines.extend(
        [
            f"status: {status}",
            f"tags: [{', '.join(tags)}]",
        ]
    )
    frontmatter_lines.append("---")

    body_lines = [
        "",
        f"# {data.title}",
        "",
        f"**Source:** {data.source}",
        f"**Captured:** {now.strftime('%Y-%m-%d %H:%M %Z')}",
        "",
    ]
    if data.summary:
        body_lines.extend(["## Analysis", "", data.summary, ""])
    # Transcript only for audio/video — text captures are re-readable at the source URL
    if data.transcript_or_ocr and data.subtype in ("video-url", "voice-note", "video-file"):
        body_lines.extend(["## Transcript", "", data.transcript_or_ocr, ""])

    out_path.write_text("\n".join(frontmatter_lines + body_lines))
    return out_path
