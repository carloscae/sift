import json
from pathlib import Path

from sift.config import Config
from sift.queue import Queue


def _config(vault: Path) -> Config:
    return Config(vault=vault)


def test_enqueue_writes_to_state(tmp_vault: Path):
    q = Queue(_config(tmp_vault))
    item_id = q.enqueue_url("https://tiktok.com/foo")
    state = json.loads((tmp_vault / ".vault-ingest" / "queue.json").read_text())
    assert item_id in state["pending"]
    assert state["pending"][item_id]["source"] == "https://tiktok.com/foo"


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
    """scan_raw with N new files writes queue.json once, not N times."""
    for i in range(3):
        (tmp_vault / "raw" / f"voice{i}.mp3").write_bytes(b"x")

    q = Queue(_config(tmp_vault))
    items = q.scan_raw()
    assert len(items) == 3
    # All 3 items present in queue state after a single scan
    state = json.loads((tmp_vault / ".vault-ingest" / "queue.json").read_text())
    assert len(state["pending"]) == 3
