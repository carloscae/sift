import shutil
from pathlib import Path

import structlog

import sift.extractors  # noqa: F401  — registers built-in extractors
from sift.classify import ItemKind
from sift.config import Config
from sift.extractors.base import ExtractFailure, ExtractResult
from sift.extractors.dispatch import dispatch_extract
from sift.queue import Queue, QueueEntry
from sift.writer import CaptureData, write_capture

logger = structlog.get_logger()


def process_pending(config: Config) -> None:
    """Process every pending item in the queue."""
    queue = Queue(config)
    queue.scan_raw()

    for entry in queue.pending_items():
        try:
            _process_one(config, entry)
            queue.mark_processed(entry.id)
            logger.info("processed", item_id=entry.id, source=entry.source)
        except Exception as e:
            logger.error("processing-failed", item_id=entry.id, error=str(e))
            queue.mark_failed(entry.id)


def _process_one(config: Config, entry: QueueEntry) -> None:
    work_dir = config.state_path / "work" / entry.id
    work_dir.mkdir(parents=True, exist_ok=True)

    try:
        extract_result: ExtractResult | ExtractFailure | None = None

        if entry.kind == ItemKind.URL.value:
            extract_result = dispatch_extract(entry.source, work_dir)

        if isinstance(extract_result, ExtractFailure):
            _write_failure_stub(config, entry, extract_result)
            return

        if extract_result is not None:
            _write_from_extract(config, entry, extract_result, work_dir)
        else:
            _write_file_stub(config, entry)
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)


def _write_from_extract(
    config: Config, entry: QueueEntry, result: ExtractResult, work_dir: Path
) -> None:
    raw_file = None
    if result.media_path:
        dest = config.raw_path / f"{entry.id}-{result.media_path.name}"
        dest.parent.mkdir(parents=True, exist_ok=True)
        result.media_path.replace(dest)
        raw_file = str(dest.relative_to(config.vault))

    data = CaptureData(
        item_id=entry.id,
        source=entry.source,
        platform=result.platform,
        subtype=_subtype_from_media(result.media_type, result.platform),
        title=result.title,
        transcript_or_ocr=result.text_content,
        raw_file=raw_file,
    )
    write_capture(config, data)


def _write_failure_stub(
    config: Config, entry: QueueEntry, failure: ExtractFailure
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


def _write_file_stub(config: Config, entry: QueueEntry) -> None:
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
        title=Path(entry.source).name,
        raw_file=entry.local_path,
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
