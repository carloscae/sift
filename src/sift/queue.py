import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, Field

from sift.classify import Item, classify_path, classify_url
from sift.config import Config


class QueueEntry(BaseModel):
    id: str
    source: str
    kind: str
    platform: str | None = None
    local_path: str | None = None
    enqueued_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())


class QueueState(BaseModel):
    pending: dict[str, QueueEntry] = Field(default_factory=dict)
    processed: dict[str, QueueEntry] = Field(default_factory=dict)
    failed: dict[str, QueueEntry] = Field(default_factory=dict)


class Queue:
    def __init__(self, config: Config):
        self.config = config
        self._state_file = config.state_path / "queue.json"
        self._state = self._load()

    def _load(self) -> QueueState:
        if self._state_file.exists():
            return QueueState(**json.loads(self._state_file.read_text()))
        return QueueState()

    def _save(self) -> None:
        self._state_file.parent.mkdir(parents=True, exist_ok=True)
        self._state_file.write_text(self._state.model_dump_json(indent=2))

    @staticmethod
    def _hash_source(source: str) -> str:
        return hashlib.sha256(source.encode()).hexdigest()[:12]

    def _enqueue_item(self, item_id: str, item: Item, *, save: bool) -> None:
        self._state.pending[item_id] = QueueEntry(
            id=item_id,
            source=item.source,
            kind=item.kind.value,
            platform=item.platform,
            local_path=str(item.local_path) if item.local_path else None,
        )
        if save:
            self._save()

    def enqueue_url(self, url: str) -> str:
        item = classify_url(url)
        item_id = self._hash_source(url)
        self._enqueue_item(item_id, item, save=True)
        return item_id

    def enqueue_file(self, path: Path) -> str:
        item = classify_path(path)
        item_id = self._hash_source(str(path))
        self._enqueue_item(item_id, item, save=True)
        return item_id

    def scan_raw(self) -> list[Item]:
        """Find files in raw/ not yet known to the queue."""
        if not self.config.raw_path.exists():
            return []
        seen_sources = {
            e.source for e in {**self._state.pending, **self._state.processed}.values()
        }
        new_items: list[Item] = []
        for path in self.config.raw_path.iterdir():
            if not path.is_file():
                continue
            item = classify_path(path)
            if item.source in seen_sources:
                continue
            item_id = self._hash_source(str(path))
            self._enqueue_item(item_id, item, save=False)
            new_items.append(item)
        if new_items:
            self._save()
        return new_items

    def pending_items(self) -> list[QueueEntry]:
        return list(self._state.pending.values())

    def mark_processed(self, item_id: str) -> None:
        if item_id in self._state.pending:
            self._state.processed[item_id] = self._state.pending.pop(item_id)
            self._save()

    def mark_failed(self, item_id: str) -> None:
        if item_id in self._state.pending:
            self._state.failed[item_id] = self._state.pending.pop(item_id)
            self._save()
