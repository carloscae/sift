from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from sift.extractors.twitter import TwitterExtractor
from yt_dlp.utils import DownloadError


def test_can_handle_twitter_hosts():
    e = TwitterExtractor()
    assert e.can_handle("twitter.com")
    assert e.can_handle("www.twitter.com")
    assert e.can_handle("x.com")
    assert e.can_handle("www.x.com")
    assert e.can_handle("t.co")


def test_extract_video_tweet(tmp_path: Path):
    e = TwitterExtractor()
    fake_info = {
        "title": "A video tweet",
        "uploader": "@tweeter",
        "id": "1234567890",
        "description": "desc",
    }
    with patch("sift.extractors.twitter.YoutubeDL") as mock_ydl_cls:
        mock_ydl_cls.return_value.__enter__.return_value.extract_info.return_value = fake_info
        (tmp_path / "1234567890.mp3").write_bytes(b"audio")
        result = e.extract("https://x.com/user/status/1234567890", tmp_path)

    assert result.platform == "twitter"
    assert result.media_type == "audio"
    assert result.metadata["tweet_id"] == "1234567890"


def test_extract_text_tweet_fallback(tmp_path: Path):
    e = TwitterExtractor()
    fake_fx_response = {
        "tweet": {
            "text": "Just a text tweet",
            "author": {"name": "Alice", "screen_name": "alice"},
        }
    }
    with patch("sift.extractors.twitter.YoutubeDL") as mock_ydl_cls:
        mock_ydl_cls.return_value.__enter__.return_value.extract_info.side_effect = DownloadError("no video")
        with patch("sift.extractors.twitter.httpx.get") as mock_get:
            mock_resp = MagicMock()
            mock_resp.json.return_value = fake_fx_response
            mock_get.return_value = mock_resp
            result = e.extract("https://x.com/alice/status/9999", tmp_path)

    assert result.platform == "twitter"
    assert result.media_type == "text"
    assert result.text_content == "Just a text tweet"
    assert result.metadata["screen_name"] == "alice"


def test_tco_resolves_before_extraction(tmp_path: Path):
    e = TwitterExtractor()
    fake_fx_response = {
        "tweet": {
            "text": "Resolved tweet",
            "author": {"name": "Bob", "screen_name": "bob"},
        }
    }
    with patch("sift.extractors.twitter.httpx.head") as mock_head:
        mock_head.return_value.url = "https://x.com/bob/status/111"
        with patch("sift.extractors.twitter.YoutubeDL") as mock_ydl_cls:
            mock_ydl_cls.return_value.__enter__.return_value.extract_info.side_effect = DownloadError("no video")
            with patch("sift.extractors.twitter.httpx.get") as mock_get:
                mock_resp = MagicMock()
                mock_resp.json.return_value = fake_fx_response
                mock_get.return_value = mock_resp
                result = e.extract("https://t.co/abc123", tmp_path)

    assert result.media_type == "text"
    assert result.metadata["tweet_id"] == "111"
