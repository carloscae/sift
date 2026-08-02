import sqlite3
from pathlib import Path

from sift.config import Config
from sift.queue import Queue


def _config(vault: Path) -> Config:
    return Config(vault=vault)


def _db_rows(tmp_vault: Path) -> list[tuple]:
    """Return (id, source, status) for all rows in the queue DB."""
    db_path = tmp_vault / ".vault-ingest" / "queue.db"
    with sqlite3.connect(db_path) as conn:
        return conn.execute("SELECT id, source, status FROM items").fetchall()


def _attempts(tmp_vault: Path, item_id: str) -> int:
    db_path = tmp_vault / ".vault-ingest" / "queue.db"
    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            "SELECT attempts FROM items WHERE id = ?", (item_id,)
        ).fetchone()
    return row[0]


# ---------------------------------------------------------------------------
# Original tests — rewritten to query SQLite instead of JSON
# ---------------------------------------------------------------------------

def test_enqueue_writes_to_state(tmp_vault: Path):
    q = Queue(_config(tmp_vault))
    item_id = q.enqueue_url("https://tiktok.com/foo")
    rows = _db_rows(tmp_vault)
    assert len(rows) == 1
    row_id, source, status = rows[0]
    assert row_id == item_id
    assert source == "https://tiktok.com/foo"
    assert status == "pending"


def test_scan_raw_picks_up_new_files(tmp_vault: Path):
    (tmp_vault / "raw" / "voice.mp3").write_bytes(b"x")
    q = Queue(_config(tmp_vault))
    items = q.scan_raw()
    assert len(items) == 1
    assert items[0].source.endswith("voice.mp3")


def test_scan_raw_skips_already_processed(tmp_vault: Path):
    voice = tmp_vault / "raw" / "voice.mp3"
    voice.write_bytes(b"x")
    q = Queue(_config(tmp_vault))
    item_id = q.enqueue_file(voice)
    q.mark_processed(item_id)
    items = q.scan_raw()
    assert items == []


def test_pending_items_returns_unprocessed(tmp_vault: Path):
    q = Queue(_config(tmp_vault))
    q.enqueue_url("https://x.com/foo")
    q.enqueue_url("https://x.com/bar")
    items = q.pending_items()
    assert len(items) == 2


def test_scan_raw_batches_writes(tmp_vault: Path):
    """scan_raw with N new files enqueues all of them."""
    for i in range(3):
        (tmp_vault / "raw" / f"voice{i}.mp3").write_bytes(b"x")

    q = Queue(_config(tmp_vault))
    items = q.scan_raw()
    assert len(items) == 3

    rows = _db_rows(tmp_vault)
    pending = [r for r in rows if r[2] == "pending"]
    assert len(pending) == 3


# ---------------------------------------------------------------------------
# New tests
# ---------------------------------------------------------------------------

def test_enqueue_url_dedup(tmp_vault: Path):
    """Re-enqueuing the same URL (even with tracking params) yields one pending row."""
    q = Queue(_config(tmp_vault))
    id1 = q.enqueue_url("https://youtube.com/watch?v=abc&utm_source=share")
    id2 = q.enqueue_url("https://youtube.com/watch?v=abc&utm_medium=social")
    # Normalized form is the same → same id → INSERT OR IGNORE → 1 row
    assert id1 == id2
    rows = _db_rows(tmp_vault)
    assert len(rows) == 1
    assert rows[0][2] == "pending"


def test_mark_failed_retries_below_max_attempts(tmp_vault: Path):
    """Below MAX_ATTEMPTS, mark_failed resets status to 'pending' so the item
    is picked up again by pending_items() instead of dying on attempt 1."""
    q = Queue(_config(tmp_vault))
    item_id = q.enqueue_url("https://tiktok.com/retry-test")

    q.mark_failed(item_id)
    rows = _db_rows(tmp_vault)
    assert rows[0][2] == "pending"
    assert _attempts(tmp_vault, item_id) == 1

    q.mark_failed(item_id)
    rows = _db_rows(tmp_vault)
    assert rows[0][2] == "pending"
    assert _attempts(tmp_vault, item_id) == 2


def test_mark_failed_terminates_at_max_attempts(tmp_vault: Path):
    """At MAX_ATTEMPTS, status becomes terminal 'failed' and further failures
    keep it there (the dead-letter path in the watcher can now be reached)."""
    q = Queue(_config(tmp_vault))
    item_id = q.enqueue_url("https://tiktok.com/retry-test")

    q.mark_failed(item_id)  # attempt 1 → pending
    q.mark_failed(item_id)  # attempt 2 → pending
    q.mark_failed(item_id)  # attempt 3 → terminal
    rows = _db_rows(tmp_vault)
    assert rows[0][2] == "failed"
    assert _attempts(tmp_vault, item_id) == Queue.MAX_ATTEMPTS

    q.mark_failed(item_id)  # stays terminal, doesn't keep incrementing forever
    rows = _db_rows(tmp_vault)
    assert rows[0][2] == "failed"


def test_enqueue_url_resets_terminal_failed_row(tmp_vault: Path):
    """Resending a link by hand must actually retry it, not silently no-op."""
    q = Queue(_config(tmp_vault))
    url = "https://tiktok.com/resend-test"
    item_id = q.enqueue_url(url)
    q.mark_failed(item_id)
    q.mark_failed(item_id)
    q.mark_failed(item_id)
    rows = _db_rows(tmp_vault)
    assert rows[0][2] == "failed"

    same_id = q.enqueue_url(url)
    assert same_id == item_id
    rows = _db_rows(tmp_vault)
    assert rows[0][2] == "pending"
    assert _attempts(tmp_vault, item_id) == 0
    assert [e.id for e in q.pending_items()] == [item_id]


def test_migration_adds_attempts_column_idempotently(tmp_vault: Path):
    """Opening a pre-migration DB (no attempts column) must not raise, and
    reopening the migrated DB a second time must not raise either."""
    db_path = tmp_vault / ".vault-ingest" / "queue.db"
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "CREATE TABLE items ("
            "id TEXT PRIMARY KEY, source TEXT NOT NULL, kind TEXT NOT NULL, "
            "platform TEXT, local_path TEXT, status TEXT NOT NULL DEFAULT 'pending', "
            "enqueued_at TEXT NOT NULL, processed_at TEXT"
            ")"
        )
        conn.execute(
            "INSERT INTO items (id, source, kind, status, enqueued_at) "
            "VALUES ('pre01', 'https://example.com/pre', 'article', 'failed', "
            "'2026-01-01T00:00:00+00:00')"
        )
        conn.commit()

    q1 = Queue(_config(tmp_vault))  # first open: migration runs
    q2 = Queue(_config(tmp_vault))  # second open: migration is a no-op

    with sqlite3.connect(db_path) as conn:
        cols = {row[1] for row in conn.execute("PRAGMA table_info(items)")}
    assert "attempts" in cols

    rows = q2.failed_items()
    assert any(e.id == "pre01" for e in rows)
    del q1


def test_pruning_removes_old_processed_entries(tmp_vault: Path):
    """Rows with processed_at older than 30 days are deleted on Queue.__init__."""
    db_path = tmp_vault / ".vault-ingest" / "queue.db"

    # Manually insert a stale processed row
    old_ts = "2020-01-01T00:00:00+00:00"
    with sqlite3.connect(db_path) as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute(
            "CREATE TABLE IF NOT EXISTS items ("
            "id TEXT PRIMARY KEY, source TEXT NOT NULL, kind TEXT NOT NULL, "
            "platform TEXT, local_path TEXT, status TEXT NOT NULL DEFAULT 'pending', "
            "enqueued_at TEXT NOT NULL, processed_at TEXT"
            ")"
        )
        conn.execute(
            "INSERT INTO items (id, source, kind, status, enqueued_at, processed_at) "
            "VALUES ('stale01', 'https://example.com/old', 'article', 'processed', ?, ?)",
            (old_ts, old_ts),
        )
        conn.commit()

    # Constructing Queue runs _prune_old(); the stale row must be gone.
    Queue(_config(tmp_vault))
    rows = _db_rows(tmp_vault)
    assert not any(r[0] == "stale01" for r in rows)
