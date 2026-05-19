from pathlib import Path

from sift.config import Config
from sift.writer import CaptureData, write_capture


def test_writes_markdown_with_frontmatter(tmp_vault: Path):
    config = Config(vault=tmp_vault)
    data = CaptureData(
        item_id="abc123",
        source="https://tiktok.com/foo",
        platform="tiktok",
        subtype="video-url",
        title="Some title",
        summary="A short summary.",
        transcript_or_ocr="The full transcript text.",
        enriched_by="openrouter",
        cost_usd=0.0006,
        models={
            "stt": "groq/whisper-large-v3-turbo",
            "text": "google/gemini-2.5-flash-lite",
        },
    )

    out_path = write_capture(config, data)

    assert out_path.exists()
    content = out_path.read_text()
    assert "type: clipping" in content
    assert "subtype: video-url" in content
    assert "platform: tiktok" in content
    assert "source: https://tiktok.com/foo" in content
    assert "status: raw" in content
    assert "enrich-cost-usd: 0.0006" in content
    assert "# Some title" in content
    assert "A short summary." in content
    assert "The full transcript text." in content


def test_writes_stub_when_no_enrichment(tmp_vault: Path):
    config = Config(vault=tmp_vault)
    data = CaptureData(
        item_id="abc",
        source="https://x.com/foo",
        platform="x",
        subtype="url-article",
        title="Untitled",
    )

    out_path = write_capture(config, data)

    content = out_path.read_text()
    assert "status: pending-enrichment" in content
    assert "enrich-cost-usd" not in content
