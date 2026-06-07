"""Regression: yt-dlp extractors must resolve ffmpeg explicitly.

Bug: the sift-watcher LaunchAgent runs under launchd's minimal PATH (no
/opt/homebrew/bin), so yt-dlp's FFmpegExtractAudio postprocessor could not
find ffmpeg/ffprobe and every video capture failed at audio extraction.
The extractors now resolve ffmpeg's directory and pass ffmpeg_location.
"""
from pathlib import Path
from unittest.mock import patch

from sift.extractors.base import resolve_ffmpeg_location
from sift.extractors.tiktok import TikTokExtractor


def test_resolve_falls_back_to_homebrew_when_not_on_path():
    # PATH has no ffmpeg (the launchd condition), but it exists in /opt/homebrew/bin
    with patch("sift.extractors.base.shutil.which", return_value=None), \
         patch("sift.extractors.base.Path.is_file",
               lambda self: str(self) == "/opt/homebrew/bin/ffmpeg"):
        assert resolve_ffmpeg_location() == "/opt/homebrew/bin"


def test_resolve_returns_none_when_truly_missing():
    with patch("sift.extractors.base.shutil.which", return_value=None), \
         patch("sift.extractors.base.Path.is_file", lambda self: False):
        assert resolve_ffmpeg_location() is None


def test_extract_passes_ffmpeg_location_to_ytdlp(tmp_path: Path):
    e = TikTokExtractor()
    fake_info = {"title": "clip", "uploader": "@u", "id": "1234"}
    with patch("sift.extractors.ytdlp_base.YoutubeDL") as mock_ydl_cls, \
         patch("sift.extractors.ytdlp_base.resolve_ffmpeg_location",
               return_value="/opt/homebrew/bin"):
        mock_ydl_cls.return_value.__enter__.return_value.extract_info.return_value = fake_info
        (tmp_path / "1234.mp3").write_bytes(b"audio")
        e.extract("https://vm.tiktok.com/ZNR78fWEf", tmp_path)

    opts = mock_ydl_cls.call_args.args[0]
    assert opts.get("ffmpeg_location") == "/opt/homebrew/bin"


def test_extract_raises_clear_error_when_ffmpeg_missing(tmp_path: Path):
    e = TikTokExtractor()
    with patch("sift.extractors.ytdlp_base.resolve_ffmpeg_location", return_value=None):
        try:
            e.extract("https://vm.tiktok.com/ZNR78fWEf", tmp_path)
            raise AssertionError("should have raised RuntimeError")
        except RuntimeError as ex:
            assert "ffmpeg" in str(ex).lower()
