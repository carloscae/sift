from pathlib import Path

from sift.config import Config
from sift.pipeline import process_pending
from sift.queue import Queue


def test_process_pending_creates_stub_for_url(tmp_vault: Path):
    config = Config(vault=tmp_vault)
    q = Queue(config)
    q.enqueue_url("https://example.com/article")

    process_pending(config)

    captures = list(config.captures_path.glob("*.md"))
    assert len(captures) == 1
    content = captures[0].read_text()
    assert "https://example.com/article" in content
    assert "status: pending-enrichment" in content


def test_process_pending_marks_item_processed(tmp_vault: Path):
    config = Config(vault=tmp_vault)
    q = Queue(config)
    q.enqueue_url("https://example.com")

    process_pending(config)

    q2 = Queue(config)
    assert q2.pending_items() == []
