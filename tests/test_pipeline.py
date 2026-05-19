from pathlib import Path
from unittest.mock import patch

from sift.config import Config
from sift.extractors.base import ExtractFailure, ExtractResult
from sift.pipeline import process_pending
from sift.queue import Queue


def test_process_pending_creates_stub_for_url(tmp_vault: Path):
    config = Config(vault=tmp_vault)
    q = Queue(config)
    q.enqueue_url("https://example.com/article")

    fake_failure = ExtractFailure(
        url="https://example.com/article",
        platform="generic",
        error_class="unknown",
        error_detail="(no extraction in this test)",
    )
    with patch("sift.pipeline.dispatch_extract", return_value=fake_failure):
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

    fake_failure = ExtractFailure(
        url="https://example.com",
        platform="generic",
        error_class="unknown",
        error_detail="(no extraction in this test)",
    )
    with patch("sift.pipeline.dispatch_extract", return_value=fake_failure):
        process_pending(config)

    q2 = Queue(config)
    assert q2.pending_items() == []


def test_pipeline_calls_extractor_for_url(tmp_vault: Path):
    config = Config(vault=tmp_vault)
    q = Queue(config)
    q.enqueue_url("https://www.youtube.com/watch?v=abc")

    fake_result = ExtractResult(
        platform="youtube",
        media_type="audio",
        title="Test Video",
        metadata={"author": "ch"},
    )

    with patch("sift.pipeline.dispatch_extract", return_value=fake_result):
        process_pending(config)

    captures = list(config.captures_path.glob("*.md"))
    assert len(captures) == 1
    content = captures[0].read_text()
    assert "# Test Video" in content
    assert "platform: youtube" in content
