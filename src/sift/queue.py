import contextlib
import hashlib
import sqlite3
import urllib.parse
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, Field

from sift.classify import Item, classify_path, classify_url
from sift.config import Config


# Tracking-only query params stripped during URL normalization.
_STRIP_PARAMS: frozenset[str] = frozenset(
    [
        # Generic UTM
        "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
        # Twitter / X
        "s", "t",
        # YouTube
        "si",
    ]
)


def _normalize_url(url: str) -> str:
    """Return a canonical form of *url* for deduplication purposes.

    Rules applied (in order):
    1. Strip tracking-only query parameters.
    2. Resolve ``youtu.be/<id>`` → ``youtube.com/watch?v=<id>``.
    3. Normalise ``x.com`` ↔ ``twitter.com`` (always stored as ``twitter.com``).
    """
    parsed = urllib.parse.urlparse(url)
    host = parsed.netloc.lower()

    # --- youtu.be → youtube.com ---
    if host in ("youtu.be", "www.youtu.be"):
        video_id = parsed.path.lstrip("/")
        parsed = parsed._replace(
            scheme="https",
            netloc="youtube.com",
            path="/watch",
            query=urllib.parse.urlencode({"v": video_id}),
            fragment="",
        )
        # Rebuild host so the param-stripping step below works cleanly.
        host = "youtube.com"

    # --- x.com → twitter.com ---
    if host in ("x.com", "www.x.com"):
        parsed = parsed._replace(netloc="twitter.com")
    elif host == "www.twitter.com":
        parsed = parsed._replace(netloc="twitter.com")

    # --- strip tracking params ---
    qs = urllib.parse.parse_qs(parsed.query, keep_blank_values=True)
    filtered = {k: v for k, v in qs.items() if k not in _STRIP_PARAMS}
    parsed = parsed._replace(query=urllib.parse.urlencode(filtered, doseq=True))

    return urllib.parse.urlunparse(parsed)


class QueueEntry(BaseModel):
    id: str
    source: str
    kind: str
    platform: str | None = None
    local_path: str | None = None
    enqueued_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())


_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS items (
    id          TEXT PRIMARY KEY,
    source      TEXT NOT NULL,
    kind        TEXT NOT NULL,
    platform    TEXT,
    local_path  TEXT,
    status      TEXT NOT NULL DEFAULT 'pending',
    enqueued_at TEXT NOT NULL,
    processed_at TEXT
);
"""


class Queue:
    def __init__(self, config: Config):
        self.config = config
        self._db_path = config.state_path / "queue.db"
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()
        self._prune_old()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @contextlib.contextmanager
    def _connect(self):
        conn = sqlite3.connect(
            self._db_path,
            check_same_thread=False,
        )
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(_CREATE_TABLE)

    def _prune_old(self) -> None:
        """Delete processed/failed rows older than 30 days."""
        with self._connect() as conn:
            conn.execute(
                "DELETE FROM items "
                "WHERE status IN ('processed', 'failed') "
                "AND processed_at < datetime('now', '-30 days')"
            )

    @staticmethod
    def _hash_source(source: str) -> str:
        return hashlib.sha256(source.encode()).hexdigest()[:12]

    def _insert_item(self, item_id: str, item: Item) -> None:
        """Insert a new pending row; silently ignore if the id already exists."""
        now = datetime.now(UTC).isoformat()
        with self._connect() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO items "
                "(id, source, kind, platform, local_path, status, enqueued_at) "
                "VALUES (?, ?, ?, ?, ?, 'pending', ?)",
                (
                    item_id,
                    item.source,
                    item.kind.value,
                    item.platform,
                    str(item.local_path) if item.local_path else None,
                    now,
                ),
            )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def enqueue_url(self, url: str) -> str:
        item = classify_url(url)
        item_id = self._hash_source(_normalize_url(url))
        self._insert_item(item_id, item)
        return item_id

    def enqueue_file(self, path: Path) -> str:
        item = classify_path(path)
        item_id = self._hash_source(str(path))
        self._insert_item(item_id, item)
        return item_id

    def scan_raw(self) -> list[Item]:
        """Find files in raw/ not yet known to the queue, enqueue them, return new Items."""
        if not self.config.raw_path.exists():
            return []

        with self._connect() as conn:
            rows = conn.execute(
                "SELECT source FROM items WHERE status IN ('pending', 'processed')"
            ).fetchall()
        seen_sources = {row["source"] for row in rows}

        new_items: list[Item] = []
        for path in self.config.raw_path.iterdir():
            if not path.is_file() or path.name.startswith("."):
                continue
            item = classify_path(path)
            if item.source in seen_sources:
                continue
            item_id = self._hash_source(str(path))
            self._insert_item(item_id, item)
            new_items.append(item)

        return new_items

    def pending_items(self) -> list[QueueEntry]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT id, source, kind, platform, local_path, enqueued_at "
                "FROM items WHERE status = 'pending'"
            ).fetchall()
        return [
            QueueEntry(
                id=row["id"],
                source=row["source"],
                kind=row["kind"],
                platform=row["platform"],
                local_path=row["local_path"],
                enqueued_at=row["enqueued_at"],
            )
            for row in rows
        ]

    def mark_processed(self, item_id: str) -> None:
        now = datetime.now(UTC).isoformat()
        with self._connect() as conn:
            conn.execute(
                "UPDATE items SET status = 'processed', processed_at = ? WHERE id = ?",
                (now, item_id),
            )

    def mark_failed(self, item_id: str) -> None:
        now = datetime.now(UTC).isoformat()
        with self._connect() as conn:
            conn.execute(
                "UPDATE items SET status = 'failed', processed_at = ? WHERE id = ?",
                (now, item_id),
            )

    def failed_items(self) -> list[QueueEntry]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT id, source, kind, platform, local_path, enqueued_at "
                "FROM items WHERE status = 'failed'"
            ).fetchall()
        return [
            QueueEntry(
                id=row["id"],
                source=row["source"],
                kind=row["kind"],
                platform=row["platform"],
                local_path=row["local_path"],
                enqueued_at=row["enqueued_at"],
            )
            for row in rows
        ]
