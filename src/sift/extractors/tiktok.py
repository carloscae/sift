from pathlib import Path

from yt_dlp import YoutubeDL

from sift.extractors.base import Extractor, ExtractResult


class TikTokExtractor(Extractor):
    platform = "tiktok"

    _HOSTS = {"tiktok.com", "www.tiktok.com", "vm.tiktok.com", "vt.tiktok.com"}

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
            platform="tiktok",
            media_type="audio",
            media_path=media_path,
            title=info.get("title", f"TikTok clip {info.get('id')}"),
            metadata={
                "author": info.get("uploader"),
                "duration": info.get("duration"),
                "id": info.get("id"),
                "source_url": url,
            },
        )
