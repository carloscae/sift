from pathlib import Path

from yt_dlp import YoutubeDL

from sift.extractors.base import Extractor, ExtractResult


class YouTubeExtractor(Extractor):
    platform = "youtube"

    _HOSTS = {"youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be"}

    def can_handle(self, hostname: str) -> bool:
        return hostname.lower() in self._HOSTS

    def extract(self, url: str, work_dir: Path) -> ExtractResult:
        opts = {
            "format": "bestaudio/best",
            "outtmpl": str(work_dir / "%(id)s.%(ext)s"),
            "postprocessors": [{
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "128",
            }],
            "quiet": True,
            "no_warnings": True,
        }
        with YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)

        media_path = next(work_dir.glob(f"{info['id']}.mp3"), None)

        return ExtractResult(
            platform="youtube",
            media_type="audio",
            media_path=media_path,
            title=info.get("title", "Untitled"),
            metadata={
                "author": info.get("uploader"),
                "duration": info.get("duration"),
                "upload_date": info.get("upload_date"),
                "id": info.get("id"),
            },
        )
