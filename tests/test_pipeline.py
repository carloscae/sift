from pathlib import Path
from unittest.mock import patch

from sift.config import Config
from sift.enricher.base import Enricher, SummaryResult, TranscriptResult
from sift.extractors.base import ExtractFailure, ExtractResult
from sift.pipeline import process_pending
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
    state = q._load()
    assert any("example.com" in str(e.source) for e in state.failed.values())


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
    assert "enrich-cost-usd: 0.0011" in content
