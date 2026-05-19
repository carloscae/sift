from datetime import UTC, datetime
from pathlib import Path

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
    raw_file: str | None = None  # path relative to vault


def _slugify(title: str, max_len: int = 50) -> str:
    s = _ext_slugify(title, max_length=max_len, word_boundary=True, save_order=True)
    return s or "untitled"


def write_capture(config: Config, data: CaptureData) -> Path:
    config.captures_path.mkdir(parents=True, exist_ok=True)

    now = datetime.now(UTC)
    date = now.strftime("%Y-%m-%d")
    slug = _slugify(data.title)
    filename = f"{date}-{slug}-{data.item_id[:6]}.md"
    out_path = config.captures_path / filename

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
            f"ingested-via: sift@{__version__}",
            f"status: {status}",
            f"tags: [{', '.join(tags)}]",
        ]
    )
    if data.raw_file:
        frontmatter_lines.append(f"raw-file: {data.raw_file}")
    if data.enriched_by:
        frontmatter_lines.extend(
            [
                f"enriched-by: {data.enriched_by}",
                f"enriched-at: {now.isoformat()}",
            ]
        )
        for kind, model in data.models.items():
            frontmatter_lines.append(f"enrich-model-{kind}: {model}")
        if data.cost_usd is not None:
            frontmatter_lines.append(f"enrich-cost-usd: {data.cost_usd:.4f}")
    frontmatter_lines.append("---")

    body_lines = [
        "",
        f"# {data.title}",
        "",
        f"**Source:** {data.source}",
        f"**Captured:** {now.strftime('%Y-%m-%d %H:%M UTC')}",
        "",
    ]
    if data.summary:
        body_lines.extend(["## Summary", "", data.summary, ""])
    if data.transcript_or_ocr:
        body_lines.extend(["## Transcript / OCR / Caption", "", data.transcript_or_ocr, ""])

    out_path.write_text("\n".join(frontmatter_lines + body_lines))
    return out_path
