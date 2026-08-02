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
    assert "enrich-cost-usd" not in content
    assert "enriched-by" not in content
    assert "# Some title" in content
    assert "## Analysis" in content
    assert "A short summary." in content
    assert "## Transcript" in content
    assert "The full transcript text." in content


def test_writes_caption_section_and_degraded_summary_status(tmp_vault: Path):
    """Task 3/2: caption metadata gets its own section; a degraded summary
    is visibly flagged in frontmatter, and no Analysis section is written
    when there's no AI summary."""
    config = Config(vault=tmp_vault)
    data = CaptureData(
        item_id="abc456",
        source="https://tiktok.com/foo",
        platform="tiktok",
        subtype="video-url",
        title="Muted clip",
        summary=None,
        summary_status="degraded",
        transcript_or_ocr="The full transcript text.",
        caption_text="Uploader: someone\nDescription: about cats #cats",
    )

    out_path = write_capture(config, data)
    content = out_path.read_text()

    assert "summary_status: degraded" in content
    assert "## Analysis" not in content
    assert "## Caption" in content
    assert "about cats #cats" in content
    assert "## Transcript" in content
    assert "The full transcript text." in content


def test_caption_identical_to_transcript_is_not_duplicated(tmp_vault: Path):
    """Silent-video degrade sets transcript_or_ocr == caption_text verbatim —
    the note must not show the same text under two headers."""
    config = Config(vault=tmp_vault)
    same_text = "Uploader: someone\nDescription: silent clip"
    data = CaptureData(
        item_id="abc789",
        source="https://tiktok.com/silent",
        platform="tiktok",
        subtype="video-url",
        title="Silent clip",
        transcript_or_ocr=same_text,
        caption_text=same_text,
    )

    out_path = write_capture(config, data)
    content = out_path.read_text()

    assert "## Caption" in content
    assert "## Transcript" not in content
    assert content.count("silent clip") == 1


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


def test_slugify_cjk_title(tmp_vault: Path):
    """CJK titles get transliterated, not stripped to 'untitled'."""
    from sift.writer import _slugify
    s = _slugify("日本語のタイトル")
    assert s != "untitled"
    assert len(s) > 0
    # Should be slug-shaped (lowercase, dashes, no spaces)
    assert " " not in s


def test_slugify_emoji_only_falls_back_to_untitled():
    from sift.writer import _slugify
    assert _slugify("🎉🔥") == "untitled"


def test_slugify_preserves_german_umlauts_as_transliteration():
    from sift.writer import _slugify
    s = _slugify("Über München — Eine Reise")
    assert s != "untitled"
    # Common transliteration: ü → u, ö → o
    assert "u" in s and "m" in s
