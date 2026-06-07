from pathlib import Path

from yt_dlp import YoutubeDL

from sift.extractors.base import Extractor, ExtractResult, resolve_ffmpeg_location


class YtDlpAudioExtractor(Extractor):
    """Base for extractors that use yt-dlp to download audio."""

    # Subclasses must define:
    platform: str           # e.g. "youtube"
    _HOSTS: set[str]        # e.g. {"youtube.com", "www.youtube.com", ...}

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
            "socket_timeout": 20,
        }
        ffmpeg_dir = resolve_ffmpeg_location()
        if ffmpeg_dir is None:
            raise RuntimeError(
                "ffmpeg/ffprobe not found on PATH or in /opt/homebrew/bin, "
                "/usr/local/bin. Install ffmpeg (brew install ffmpeg)."
            )
        opts["ffmpeg_location"] = ffmpeg_dir
        with YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
        media_path = next(work_dir.glob(f"{info['id']}.mp3"), None)
        if media_path is None:
            raise RuntimeError(
                f"yt-dlp reported success but expected mp3 not found in {work_dir} "
                f"(id={info.get('id')}). ffmpeg post-processing may have failed."
            )
        return ExtractResult(
            platform=self.platform,
            media_type="audio",
            media_path=media_path,
            title=info.get("title") or info.get("description", f"{self.platform.title()} {info.get('id')}"),
            metadata={
                "author": info.get("uploader"),
                "video_id": info.get("id"),
                "source_url": url,
            },
        )
