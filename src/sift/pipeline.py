import shutil
from pathlib import Path

import structlog

import sift.extractors  # noqa: F401 — side-effect: register built-ins
from sift.classify import ItemKind
from sift.config import Config
from sift.enricher.base import Enricher
from sift.enricher.registry import build_enricher
from sift.extractors.base import ExtractFailure, ExtractResult
from sift.extractors.dispatch import dispatch_extract
from sift.queue import Queue, QueueEntry
from sift.writer import CaptureData, write_capture

logger = structlog.get_logger()


def process_pending(config: Config) -> None:
    queue = Queue(config)
    queue.scan_raw()

    enricher: Enricher | None = None
    try:
        enricher = build_enricher(config)
    except RuntimeError as e:
        logger.warning("enricher-unavailable", error=str(e))

    for entry in queue.pending_items():
        try:
            _process_one(config, entry, enricher)
            queue.mark_processed(entry.id)
            logger.info("processed", item_id=entry.id, source=entry.source)
        except Exception as e:
            logger.error("processing-failed", item_id=entry.id, error=str(e))
            queue.mark_failed(entry.id)


def _process_one(config: Config, entry: QueueEntry, enricher: Enricher | None) -> None:
    work_dir = config.state_path / "work" / entry.id
    work_dir.mkdir(parents=True, exist_ok=True)

    try:
        if entry.kind == ItemKind.URL.value:
            result = dispatch_extract(entry.source, work_dir)
            if isinstance(result, ExtractFailure):
                _write_failure_stub(config, entry, result)
                return
            _enrich_and_write(config, entry, result, enricher)
        else:
            _enrich_file_and_write(config, entry, enricher)
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)


def _enrich_and_write(
    config: Config, entry: QueueEntry, result: ExtractResult, enricher: Enricher | None,
) -> None:
    raw_file_path: Path | None = None
    if result.media_path:
        dest = config.raw_path / f"{entry.id}-{result.media_path.name}"
        dest.parent.mkdir(parents=True, exist_ok=True)
        result.media_path.replace(dest)
        raw_file_path = dest

    # Store path relative to vault when possible, otherwise absolute
    raw_file_rel: str | None = None
    if raw_file_path is not None:
        try:
            raw_file_rel = str(raw_file_path.relative_to(config.vault))
        except ValueError:
            raw_file_rel = str(raw_file_path)

    transcript_text = result.text_content
    cost_usd = result.cost_usd
    models: dict[str, str] = {}
    enriched_by: str | None = None
    title = result.title
    summary: str | None = None
    tags: list[str] = []

    if enricher is not None:
        if result.media_type == "audio" and raw_file_path is not None:
            audio_path = raw_file_path
            t = enricher.transcribe(audio_path)
            transcript_text = t.text
            cost_usd += t.cost_usd
            models["stt"] = t.model
            enriched_by = "openrouter"

        summary_text = transcript_text or result.title
        if summary_text:
            s = enricher.summarise(
                summary_text,
                context={"source": entry.source, "platform": result.platform},
            )
            cost_usd += s.cost_usd
            models["text"] = s.model
            enriched_by = "openrouter"
            title = s.title
            summary = s.summary
            tags = s.tags

    data = CaptureData(
        item_id=entry.id,
        source=entry.source,
        platform=result.platform,
        subtype=_subtype_from_media(result.media_type, result.platform),
        title=title,
        summary=summary,
        transcript_or_ocr=transcript_text,
        tags=tags,
        enriched_by=enriched_by,
        cost_usd=cost_usd if enriched_by else None,
        models=models,
        raw_file=raw_file_rel,
    )
    write_capture(config, data)


def _enrich_file_and_write(
    config: Config, entry: QueueEntry, enricher: Enricher | None,
) -> None:
    if not entry.local_path:
        return

    path = Path(entry.local_path)
    cost_usd = 0.0
    models: dict[str, str] = {}
    enriched_by: str | None = None
    transcript_or_ocr = None
    summary = None
    title = path.name
    tags: list[str] = []

    if enricher is not None:
        if entry.kind == ItemKind.AUDIO.value:
            t = enricher.transcribe(path)
            transcript_or_ocr = t.text
            cost_usd += t.cost_usd
            models["stt"] = t.model
            enriched_by = "openrouter"

            s = enricher.summarise(t.text, context={"source": str(path)})
            cost_usd += s.cost_usd
            models["text"] = s.model
            title = s.title
            summary = s.summary
            tags = s.tags

        elif entry.kind == ItemKind.IMAGE.value:
            c = enricher.caption(path)
            transcript_or_ocr = c.ocr_text or c.caption
            cost_usd += c.cost_usd
            models["vision"] = c.model
            enriched_by = "openrouter"
            tags = c.tags
            title = c.caption[:60] if c.caption else path.name
            summary = c.caption

    subtype = {
        ItemKind.AUDIO.value: "voice-note",
        ItemKind.IMAGE.value: "photo",
        ItemKind.VIDEO.value: "video-file",
        ItemKind.DOCUMENT.value: "document",
    }.get(entry.kind, "text-note")

    data = CaptureData(
        item_id=entry.id,
        source=entry.source,
        subtype=subtype,
        title=title,
        summary=summary,
        transcript_or_ocr=transcript_or_ocr,
        tags=tags,
        enriched_by=enriched_by,
        cost_usd=cost_usd if enriched_by else None,
        models=models,
        raw_file=entry.local_path,
    )
    write_capture(config, data)


def _write_failure_stub(
    config: Config, entry: QueueEntry, failure: ExtractFailure,
) -> None:
    data = CaptureData(
        item_id=entry.id,
        source=entry.source,
        platform=failure.platform,
        subtype="url-failed",
        title=f"[Extraction failed] {entry.source}",
        summary=(
            f"**{failure.error_class}**: {failure.error_detail}"
            f"\n\n{failure.suggested_t2 or ''}"
        ),
    )
    write_capture(config, data)


def _subtype_from_media(media_type: str, platform: str) -> str:
    if media_type == "audio":
        return "video-url"
    if media_type == "text":
        return "url-article"
    if media_type == "image":
        return "photo"
    return "video-url"
