from pathlib import Path
from unittest.mock import MagicMock, patch

from sift.extractors.youtube import YouTubeExtractor


def test_can_handle_youtube_hosts():
    e = YouTubeExtractor()
    assert e.can_handle("youtube.com")
    assert e.can_handle("www.youtube.com")
    assert e.can_handle("m.youtube.com")
    assert e.can_handle("youtu.be")


def test_can_handle_rejects_others():
    e = YouTubeExtractor()
    assert not e.can_handle("tiktok.com")


def test_extract_calls_ytdlp_and_returns_result(tmp_path: Path):
    e = YouTubeExtractor()
    fake_info = {
        "title": "Test Video",
        "uploader": "test-channel",
        "duration": 42,
        "upload_date": "20260519",
        "id": "abc123",
    }

    with patch("sift.extractors.youtube.YoutubeDL") as mock_ydl_cls:
        mock_ydl = MagicMock()
        mock_ydl_cls.return_value.__enter__.return_value = mock_ydl
        mock_ydl.extract_info.return_value = fake_info
        (tmp_path / "abc123.mp3").write_bytes(b"audio")

        result = e.extract("https://youtu.be/abc123", tmp_path)

    assert result.platform == "youtube"
    assert result.media_type == "audio"
    assert result.title == "Test Video"
    assert result.metadata["author"] == "test-channel"
    assert result.metadata["duration"] == 42
    assert result.media_path is not None
