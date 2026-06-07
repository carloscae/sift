import json
import os
import shutil
from datetime import UTC, datetime
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

_RESULT_FILE = Path(os.environ.get("SIFT_RESULT_FILE", "")) if os.environ.get("SIFT_RESULT_FILE") else None
_BUDGET_FILE = Path.home() / ".sift" / "budget.json"


def _load_monthly_spend() -> float:
    """Return total enrichment spend for the current calendar month."""
    key = datetime.now(UTC).strftime("%Y-%m")
    try:
        data = json.loads(_BUDGET_FILE.read_text())
        return data.get(key, 0.0)
    except (FileNotFoundError, json.JSONDecodeError):
        return 0.0


def _record_spend(amount: float) -> None:
    """Add amount to this month's running total."""
    key = datetime.now(UTC).strftime("%Y-%m")
    try:
        data = json.loads(_BUDGET_FILE.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        data = {}
    data[key] = round(data.get(key, 0.0) + amount, 6)
    _BUDGET_FILE.parent.mkdir(parents=True, exist_ok=True)
    _BUDGET_FILE.write_text(json.dumps(data, indent=2))


def _write_result(title: str) -> None:
    if _RESULT_FILE:
        _RESULT_FILE.parent.mkdir(parents=True, exist_ok=True)
        _RESULT_FILE.write_text(json.dumps({"title": title, "success": True}))


def process_pending(config: Config) -> None:
    queue = Queue(config)
    queue.scan_raw()

    enricher: Enricher | None = None
    if config.enricher.monthly_budget_usd is not None:
        spent = _load_monthly_spend()
        if spent >= config.enricher.monthly_budget_usd:
            logger.warning(
                "monthly-budget-exceeded",
                spent=spent,
                budget=config.enricher.monthly_budget_usd,
            )
        else:
            try:
                enricher = build_enricher(config)
            except RuntimeError as e:
                logger.warning("enricher-unavailable", error=str(e))
    else:
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
                raise RuntimeError(
                    f"extraction-failed [{result.error_class}]: {result.error_detail}"
                )
            _enrich_and_write(config, entry, result, enricher)
        else:
            _enrich_file_and_write(config, entry, enricher)
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)


def _enrich_and_write(
    config: Config, entry: QueueEntry, result: ExtractResult, enricher: Enricher | None,
) -> None:
    # Finding 15 fix: track audio location separately so audio_path always
    # points to wherever the file actually is (work_dir if move failed, dest
    # if move succeeded).  If replace() raises (e.g. disk full), we log, set
    # audio_path to the original work_dir location, and re-raise — the
    # finally block below and _process_one's rmtree then handle cleanup
    # correctly.
    audio_path: Path | None = None
    if result.media_path:
        dest = config.raw_path / f"{entry.id}-{result.media_path.name}"
        dest.parent.mkdir(parents=True, exist_ok=True)
        audio_path = result.media_path  # point at source before attempting move
        try:
            result.media_path.replace(dest)
            audio_path = dest  # update only after successful move
        except OSError as exc:
            logger.error(
                "audio-move-failed",
                src=str(result.media_path),
                dest=str(dest),
                error=str(exc),
            )
            raise

    transcript_text = result.text_content
    cost_usd = result.cost_usd
    models: dict[str, str] = {}
    enriched_by: str | None = None
    title = result.title
    summary: str | None = None
    tags: list[str] = []

    # Finding 10 fix: only delete audio in the finally block if transcription
    # was actually attempted.  When the enricher is unavailable, leave the
    # audio file in place so the item can be retried later.
    transcription_attempted = False
    try:
        if enricher is not None:
            if result.media_type == "audio" and audio_path is not None:
                transcription_attempted = True
                t = enricher.transcribe(audio_path)
                transcript_text = t.text
                cost_usd += t.cost_usd
                models["stt"] = t.model
                enriched_by = config.enricher.backend

            summary_text = transcript_text or result.title
            if summary_text:
                s = enricher.summarise(
                    summary_text,
                    context={"source": entry.source, "platform": result.platform},
                )
                cost_usd += s.cost_usd
                models["text"] = s.model
                enriched_by = config.enricher.backend
                title = s.title
                summary = s.summary
                tags = s.tags
    finally:
        # Only clean up the audio file when we actually tried to transcribe it.
        # If enricher was None, leave the file so retrying enrichment is possible.
        if transcription_attempted and audio_path and audio_path.exists():
            audio_path.unlink()

    data = CaptureData(
        item_id=entry.id,
        source=entry.source,
        platform=result.platform,
        subtype=_subtype_from_media(result.media_type),
        title=title,
        summary=summary,
        transcript_or_ocr=transcript_text,
        tags=tags,
        enriched_by=enriched_by,
        cost_usd=cost_usd if enriched_by else None,
        models=models,
    )
    write_capture(config, data)
    if cost_usd > 0:
        _record_spend(cost_usd)
    _write_result(data.title or data.source)


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
            enriched_by = config.enricher.backend

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
            enriched_by = config.enricher.backend
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
    )
    write_capture(config, data)
    if cost_usd > 0:
        _record_spend(cost_usd)
    path.unlink(missing_ok=True)
    _write_result(data.title or data.source)



def _subtype_from_media(media_type: str) -> str:
    if media_type == "audio":
        return "video-url"
    if media_type == "text":
        return "url-article"
    if media_type == "image":
        return "photo"
    return "video-url"
