from pathlib import Path
from unittest.mock import patch

from sift.extractors.tiktok import TikTokExtractor


def test_can_handle_tiktok_hosts():
    e = TikTokExtractor()
    assert e.can_handle("tiktok.com")
    assert e.can_handle("www.tiktok.com")
    assert e.can_handle("vm.tiktok.com")
    assert e.can_handle("vt.tiktok.com")


def test_extract_returns_result(tmp_path: Path):
    e = TikTokExtractor()
    fake_info = {"title": "TikTok clip", "uploader": "@user", "id": "1234", "duration": 30}

    with patch("sift.extractors.ytdlp_base.YoutubeDL") as mock_ydl_cls:
        mock_ydl_cls.return_value.__enter__.return_value.extract_info.return_value = fake_info
        (tmp_path / "1234.mp3").write_bytes(b"audio")
        result = e.extract("https://www.tiktok.com/@user/video/1234", tmp_path)

    assert result.platform == "tiktok"
    assert result.media_type == "audio"
    assert result.metadata["author"] == "@user"


def test_extract_anti_scrape_raises(tmp_path: Path):
    e = TikTokExtractor()
    with patch("sift.extractors.ytdlp_base.YoutubeDL") as mock_ydl_cls:
        mock_ydl_cls.return_value.__enter__.return_value.extract_info.side_effect = (
            Exception("Unable to extract: anti-scrape protection")
        )
        try:
            e.extract("https://www.tiktok.com/@user/video/blocked", tmp_path)
            raise AssertionError("should have raised")
        except Exception as ex:
            assert "anti-scrape" in str(ex)
