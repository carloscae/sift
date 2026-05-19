import structlog

from sift.classify import ItemKind
from sift.config import Config
from sift.queue import Queue, QueueEntry
from sift.writer import CaptureData, write_capture

logger = structlog.get_logger()


def process_pending(config: Config) -> None:
    """Process every pending item in the queue.

    Phase 1: writes a stub capture per item. No extraction, no enrichment.
    """
    queue = Queue(config)
    queue.scan_raw()  # pick up new files dropped in raw/

    for entry in queue.pending_items():
        try:
            _process_one(config, entry)
            queue.mark_processed(entry.id)
            logger.info("processed", item_id=entry.id, source=entry.source)
        except Exception as e:
            logger.error("processing-failed", item_id=entry.id, error=str(e))
            queue.mark_failed(entry.id)


def _process_one(config: Config, entry: QueueEntry) -> None:
    subtype = _entry_subtype(entry)
    data = CaptureData(
        item_id=entry.id,
        source=entry.source,
        platform=entry.platform,
        subtype=subtype,
        title=_default_title(entry),
    )
    write_capture(config, data)


def _entry_subtype(entry: QueueEntry) -> str:
    if entry.kind == ItemKind.URL.value:
        return "url-article" if entry.platform == "generic" else "video-url"
    return {
        ItemKind.AUDIO.value: "voice-note",
        ItemKind.IMAGE.value: "photo",
        ItemKind.VIDEO.value: "video-file",
        ItemKind.DOCUMENT.value: "document",
        ItemKind.TEXT.value: "text-note",
    }.get(entry.kind, "text-note")


def _default_title(entry: QueueEntry) -> str:
    if entry.kind == ItemKind.URL.value:
        return f"{entry.platform or 'link'} clipping"
    return entry.source.rsplit("/", 1)[-1] if entry.local_path else "Untitled"
