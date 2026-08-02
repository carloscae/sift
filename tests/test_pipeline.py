from pathlib import Path
from unittest.mock import patch

from sift.config import Config, EnricherConfig
from sift.enricher.base import Enricher, SummaryResult, TranscriptResult
from sift.extractors.base import ExtractFailure, ExtractResult
from sift.pipeline import ItemOutcome, ProcessResult, confirmation_for, process_pending
from sift.queue import Queue


def test_process_pending_retries_before_terminal_failure(tmp_vault: Path):
    """A single failed run must retry (item stays pending), not die at attempt 1."""
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
    assert q2.failed_items() == []
    pending_sources = [e.source for e in q2.pending_items()]
    assert any("example.com" in s for s in pending_sources)


def test_process_pending_marks_terminal_failed_after_max_attempts(tmp_vault: Path):
    """After MAX_ATTEMPTS failed runs, the item leaves pending_items() and
    lands in failed_items() — the state the watcher's dead-letter path reads."""
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
        for _ in range(Queue.MAX_ATTEMPTS):
            process_pending(config)

    q2 = Queue(config)
    assert q2.pending_items() == []
    assert any("example.com" in e.source for e in q2.failed_items())


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
    saved, message = confirmation_for("b", result, "failed", latest_title=lambda: "stale")
    assert saved is False
    assert message is None


def test_confirmation_for_saved_uses_real_title():
    result = ProcessResult(saved=[ItemOutcome(item_id="a", title="Real Title")])
    saved, message = confirmation_for("a", result, "processed", latest_title=lambda: "stale")
    assert saved is True
    assert message == "✓ Real Title"


def test_confirmation_for_absent_and_processed_falls_back_to_latest():
    """A duplicate URL captured in a prior run (status now 'processed') counts
    as saved, with the latest title — this run didn't touch it at all."""
    result = ProcessResult()
    saved, message = confirmation_for(
        "c", result, "processed", latest_title=lambda: "✓ latest capture"
    )
    assert saved is True
    assert message == "✓ latest capture"


def test_confirmation_for_absent_and_pending_is_not_saved():
    """Regression: enqueue_url hashes to an id already 'failed' in the DB, so
    the item never appears in pending_items() and 'absent' used to be
    misread as success. A genuinely pending/failed item must not confirm."""
    result = ProcessResult()
    saved, message = confirmation_for(
        "c", result, "pending", latest_title=lambda: "✓ latest capture"
    )
    assert saved is False
    assert message is None


def test_confirmation_for_absent_and_failed_is_not_saved():
    result = ProcessResult()
    saved, message = confirmation_for(
        "c", result, "failed", latest_title=lambda: "✓ latest capture"
    )
    assert saved is False
    assert message is None


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


class _FakeEnricherSummariseFails(Enricher):
    def transcribe(self, audio_path):
        return TranscriptResult(text="Full transcript text.", model="fake-stt", cost_usd=0.001)

    def caption(self, image_path):
        from sift.enricher.base import CaptionResult
        return CaptionResult(caption="img", model="fake-v", cost_usd=0.001)

    def summarise(self, text, context=None):
        raise RuntimeError("claude CLI exited 1: (simulated)")


def test_summarise_failure_raises_on_non_final_attempt(tmp_vault: Path):
    """Before the retry budget is exhausted, a summarise() failure must still
    raise so the item is genuinely retried, not prematurely degraded."""
    config = Config(vault=tmp_vault)
    q = Queue(config)
    q.enqueue_url("https://www.youtube.com/watch?v=abc")

    audio = tmp_vault / "fake-audio.mp3"
    audio.write_bytes(b"audio")
    fake_extract = ExtractResult(
        platform="youtube", media_type="audio", media_path=audio, title="Original Title",
    )

    with patch("sift.pipeline.dispatch_extract", return_value=fake_extract), \
         patch("sift.pipeline.build_enricher", return_value=_FakeEnricherSummariseFails()):
        result = process_pending(config)

    assert result.saved == []
    assert result.failed  # this attempt failed and will be retried
    assert list(config.captures_path.glob("*.md")) == []
    q2 = Queue(config)
    assert q2.pending_items() != []  # retried, not lost, not dead


def test_summarise_failure_degrades_to_partial_capture_on_final_attempt(tmp_vault: Path):
    """On the retry-exhausting attempt, losing the transcript to a summarise()
    failure is worse than shipping a capture with no AI summary. Write the
    transcript + extractor title, flag it as partial, and mark processed
    instead of dead-lettering a note that holds real content."""
    config = Config(vault=tmp_vault)
    q = Queue(config)
    item_id = q.enqueue_url("https://www.youtube.com/watch?v=abc")
    q.mark_failed(item_id)  # attempts 0 -> 1, still pending
    q.mark_failed(item_id)  # attempts 1 -> 2, still pending — next run is final

    audio = tmp_vault / "fake-audio.mp3"
    audio.write_bytes(b"audio")
    fake_extract = ExtractResult(
        platform="youtube", media_type="audio", media_path=audio, title="Original Title",
    )

    with patch("sift.pipeline.dispatch_extract", return_value=fake_extract), \
         patch("sift.pipeline.build_enricher", return_value=_FakeEnricherSummariseFails()):
        result = process_pending(config)

    assert result.failed == []
    assert [o.item_id for o in result.saved] == [item_id]

    captures = list(config.captures_path.glob("*.md"))
    assert len(captures) == 1
    content = captures[0].read_text()
    assert "# Original Title" in content
    assert "Full transcript text." in content
    assert "## Analysis" not in content
    assert "summary_status: degraded" in content

    q2 = Queue(config)
    assert q2.pending_items() == []
    assert q2.failed_items() == []


class _RecordingEnricher(Enricher):
    def __init__(self):
        self.received_text: str | None = None

    def transcribe(self, audio_path):
        return TranscriptResult(text="Full transcript text.", model="fake-stt", cost_usd=0.0)

    def caption(self, image_path):
        from sift.enricher.base import CaptionResult
        return CaptionResult(caption="img", model="fake-v", cost_usd=0.0)

    def summarise(self, text, context=None):
        self.received_text = text
        return SummaryResult(
            title="Smart title", summary="Summary.", tags=["t"], model="fake-text", cost_usd=0.0
        )


def test_caption_and_transcript_both_fed_to_summarise_labelled_and_ordered(tmp_vault: Path):
    """Caption metadata (uploader/description/hashtags) carries topic signal
    a thin transcript alone doesn't. Both must reach summarise(), clearly
    labelled, with the caption block first — the enricher's 8000-char
    truncation is a head-cut, so caption-first means a long transcript loses
    its tail, never the caption."""
    config = Config(vault=tmp_vault)
    q = Queue(config)
    q.enqueue_url("https://www.tiktok.com/@u/video/1")

    audio = tmp_vault / "fake-audio.mp3"
    audio.write_bytes(b"audio")
    fake_extract = ExtractResult(
        platform="tiktok",
        media_type="audio",
        media_path=audio,
        title="Original Title",
        caption_text="Uploader: someone\nDescription: about cats #cats",
    )
    enricher = _RecordingEnricher()

    with patch("sift.pipeline.dispatch_extract", return_value=fake_extract), \
         patch("sift.pipeline.build_enricher", return_value=enricher):
        process_pending(config)

    assert enricher.received_text is not None
    assert "[Post metadata]" in enricher.received_text
    assert "Uploader: someone" in enricher.received_text
    assert "[Transcript]" in enricher.received_text
    assert "Full transcript text." in enricher.received_text
    assert enricher.received_text.index("[Post metadata]") < enricher.received_text.index(
        "[Transcript]"
    )

    captures = list(config.captures_path.glob("*.md"))
    content = captures[0].read_text()
    assert "## Caption" in content
    assert "about cats #cats" in content


def test_caption_only_when_transcript_absent(tmp_vault: Path):
    """Silent-video degrade path (ac2dd77): media_type='text', no separate
    transcript — the extractor's caption is the only signal available."""
    config = Config(vault=tmp_vault)
    q = Queue(config)
    q.enqueue_url("https://www.tiktok.com/@u/video/2")

    fake_extract = ExtractResult(
        platform="tiktok",
        media_type="text",
        title="Muted clip",
        text_content="Uploader: someone\nDescription: silent clip",
        caption_text="Uploader: someone\nDescription: silent clip",
        metadata={"degraded_reason": "silent-video-no-audio-stream"},
    )
    enricher = _RecordingEnricher()

    with patch("sift.pipeline.dispatch_extract", return_value=fake_extract), \
         patch("sift.pipeline.build_enricher", return_value=enricher):
        process_pending(config)

    assert enricher.received_text is not None
    assert "[Post metadata]" in enricher.received_text
    # The degrade path sets text_content == caption_text verbatim (ac2dd77) —
    # must not duplicate identical content into a second [Transcript] block.
    assert enricher.received_text.count("silent clip") == 1

    captures = list(config.captures_path.glob("*.md"))
    content = captures[0].read_text()
    # A muted TikTok clip is not an article: must not be misclassified.
    assert "subtype: video-url" in content
    assert "subtype: url-article" not in content
