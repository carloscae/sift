from pathlib import Path
from unittest.mock import patch

from sift.config import Config, EnricherConfig
from sift.enricher.base import Enricher, SummaryResult, TranscriptResult
from sift.extractors.base import ExtractFailure, ExtractResult
from sift.pipeline import ItemOutcome, ProcessResult, confirmation_for, process_pending
from sift.queue import Queue


def test_process_pending_marks_failed_for_url(tmp_vault: Path):
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

    # No stub written to captures — failures go to queue state only
    captures = list(config.captures_path.glob("*.md"))
    assert len(captures) == 0
    q2 = Queue(config)
    failed_sources = [e.source for e in q2.failed_items()]
    assert any("example.com" in s for s in failed_sources)


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


def test_process_pending_returns_failed_not_saved_when_extraction_fails(tmp_vault: Path):
    """A run where the only item fails must report it failed, not saved.

    Regression: process_pending used to return None, so the watcher counted
    every drained trigger file as 'processed' regardless of per-item outcome —
    hiding a multi-week capture outage.
    """
    config = Config(vault=tmp_vault)
    q = Queue(config)
    item_id = q.enqueue_url("https://example.com/article")

    fake_failure = ExtractFailure(
        url="https://example.com/article",
        platform="generic",
        error_class="unknown",
        error_detail="(no extraction in this test)",
    )
    with patch("sift.pipeline.dispatch_extract", return_value=fake_failure):
        result = process_pending(config)

    assert result.failed == [item_id]
    assert result.saved == []


def test_process_pending_reports_saved_with_title(tmp_vault: Path):
    """A saved item is reported in `saved` with its resolved capture title."""
    config = Config(vault=tmp_vault)
    q = Queue(config)
    item_id = q.enqueue_url("https://www.youtube.com/watch?v=abc")

    fake_result = ExtractResult(
        platform="youtube",
        media_type="audio",
        title="Test Video",
        metadata={"author": "ch"},
    )
    with patch("sift.pipeline.dispatch_extract", return_value=fake_result):
        result = process_pending(config)

    assert result.failed == []
    assert [(o.item_id, o.title) for o in result.saved] == [(item_id, "Test Video")]


def test_process_result_outcome_for():
    """outcome_for distinguishes saved / failed / absent — the watcher's ✓ vs ❌ gate."""
    result = ProcessResult(
        saved=[ItemOutcome(item_id="a", title="Title A")],
        failed=["b"],
    )
    assert result.outcome_for("a") == ("saved", "Title A")
    assert result.outcome_for("b") == ("failed", None)
    assert result.outcome_for("c") == ("absent", None)


def test_confirmation_for_failed_sends_nothing():
    """The exact regression: a failed item must not produce a success confirmation."""
    result = ProcessResult(failed=["b"])
    saved, message = confirmation_for("b", result, latest_title=lambda: "stale")
    assert saved is False
    assert message is None


def test_confirmation_for_saved_uses_real_title():
    result = ProcessResult(saved=[ItemOutcome(item_id="a", title="Real Title")])
    saved, message = confirmation_for("a", result, latest_title=lambda: "stale")
    assert saved is True
    assert message == "✓ Real Title"


def test_confirmation_for_absent_falls_back_to_latest():
    """A duplicate URL captured in a prior run counts as saved, with the latest title."""
    result = ProcessResult()
    saved, message = confirmation_for("c", result, latest_title=lambda: "✓ latest capture")
    assert saved is True
    assert message == "✓ latest capture"


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


class _FakeEnricher(Enricher):
    def transcribe(self, audio_path):
        return TranscriptResult(text="Full transcript text.", model="fake-stt", cost_usd=0.001)

    def caption(self, image_path):
        from sift.enricher.base import CaptionResult
        return CaptionResult(caption="img", model="fake-v", cost_usd=0.001)

    def summarise(self, text, context=None):
        return SummaryResult(
            title="Smart title",
            summary="A 2-3 sentence summary.",
            tags=["tag1"],
            model="fake-text",
            cost_usd=0.0001,
        )


def test_budget_exceeded_skips_enricher(tmp_vault: Path):
    """When monthly spend exceeds the configured budget, enricher must be None."""
    enricher_cfg = EnricherConfig(monthly_budget_usd=1.00)
    config = Config(vault=tmp_vault, enricher=enricher_cfg)

    q = Queue(config)
    q.enqueue_url("https://example.com/article")

    fake_failure = ExtractFailure(
        url="https://example.com/article",
        platform="generic",
        error_class="unknown",
        error_detail="(no extraction in this test)",
    )

    # Simulate spend already above budget (e.g. $1.50 spent, $1.00 limit)
    with patch("sift.pipeline._load_monthly_spend", return_value=1.50), \
         patch("sift.pipeline.build_enricher") as mock_build, \
         patch("sift.pipeline.dispatch_extract", return_value=fake_failure):
        process_pending(config)

    # build_enricher must never have been called — budget guard short-circuits it
    mock_build.assert_not_called()


def test_pipeline_enriches_audio_url(tmp_vault: Path):
    config = Config(vault=tmp_vault)
    q = Queue(config)
    q.enqueue_url("https://www.youtube.com/watch?v=abc")

    work_dir_for_item = tmp_vault / ".vault-ingest" / "work"
    work_dir_for_item.mkdir(parents=True, exist_ok=True)
    audio = tmp_vault / "fake-audio.mp3"
    audio.write_bytes(b"audio")

    fake_extract = ExtractResult(
        platform="youtube",
        media_type="audio",
        media_path=audio,
        title="Original Title",
    )
    fake_enricher = _FakeEnricher()

    with patch("sift.pipeline.dispatch_extract", return_value=fake_extract), \
         patch("sift.pipeline.build_enricher", return_value=fake_enricher):
        process_pending(config)

    captures = list(config.captures_path.glob("*.md"))
    assert len(captures) == 1
    content = captures[0].read_text()
    assert "# Smart title" in content
    assert "A 2-3 sentence summary." in content
    assert "Full transcript text." in content
    assert "status: raw" in content
    assert "enrich-cost-usd" not in content
