from pathlib import Path
from unittest.mock import patch

from yt_dlp.utils import DownloadError

from sift.extractors.tiktok import TikTokExtractor
from sift.extractors.ytdlp_base import _build_caption_text


def test_build_caption_text_basic():
    info = {
        "uploader": "@someone",
        "description": "A trip to the mountains",
        "tags": ["travel", "mountains"],
    }
    caption = _build_caption_text(info)
    assert caption == (
        "Uploader: @someone\n"
        "Description: A trip to the mountains\n"
        "Hashtags: #travel #mountains"
    )


def test_build_caption_text_skips_empty_parts():
    info = {"uploader": "@someone", "description": "", "tags": []}
    assert _build_caption_text(info) == "Uploader: @someone"


def test_build_caption_text_returns_none_when_nothing_available():
    info = {"uploader": "", "description": "", "tags": []}
    assert _build_caption_text(info) is None


def test_build_caption_text_dedupes_hashtags_already_in_description():
    info = {
        "uploader": "@someone",
        "description": "Check this out #travel #mountains",
        "tags": ["travel", "mountains", "vacation"],
    }
    caption = _build_caption_text(info)
    # only the tag not already visible inline is added
    assert "Hashtags: #vacation" in caption
    assert caption.count("#travel") == 1
    assert caption.count("#mountains") == 1


def test_build_caption_text_truncates_description_not_hashtags():
    info = {
        "uploader": "@someone",
        "description": "x" * 3000,
        "tags": ["travel", "mountains"],
    }
    caption = _build_caption_text(info)
    assert len(caption) <= 1550  # ~1500 char cap plus line labels/ellipsis
    assert "Hashtags: #travel #mountains" in caption


def test_extract_degrades_on_silent_video_ffprobe_error(tmp_path: Path):
    e = TikTokExtractor()
    metadata_only = {
        "id": "999",
        "uploader": "@muted",
        "description": "A silent slideshow #quiet",
        "tags": ["quiet"],
        "title": "A silent slideshow",
    }

    with patch("sift.extractors.ytdlp_base.YoutubeDL") as mock_ydl_cls:
        mock_ydl = mock_ydl_cls.return_value.__enter__.return_value
        mock_ydl.extract_info.side_effect = [
            DownloadError(
                "ERROR: Postprocessing: WARNING: unable to obtain file audio codec with ffprobe"
            ),
            metadata_only,
        ]
        result = e.extract("https://www.tiktok.com/@muted/video/999", tmp_path)

    assert result.media_type == "text"
    assert result.media_path is None
    assert result.text_content is not None
    assert "A silent slideshow" in result.text_content
    assert result.caption_text == result.text_content
    assert mock_ydl.extract_info.call_count == 2


def test_extract_still_raises_on_unrelated_download_error(tmp_path: Path):
    e = TikTokExtractor()
    with patch("sift.extractors.ytdlp_base.YoutubeDL") as mock_ydl_cls:
        mock_ydl_cls.return_value.__enter__.return_value.extract_info.side_effect = DownloadError(
            "ERROR: [TikTok] Your IP address is blocked from accessing this post"
        )
        try:
            e.extract("https://www.tiktok.com/@user/video/blocked", tmp_path)
            raise AssertionError("should have raised")
        except DownloadError as ex:
            assert "IP address is blocked" in str(ex)
