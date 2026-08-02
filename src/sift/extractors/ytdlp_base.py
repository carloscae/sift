import re
from pathlib import Path

from yt_dlp import YoutubeDL

from sift.extractors.base import Extractor, ExtractResult, resolve_ffmpeg_location

CAPTION_MAX_CHARS = 1500

_HASHTAG_RE = re.compile(r"#\w+")


def _is_silent_video_error(exc: Exception) -> bool:
    """Narrow match for yt-dlp's postprocessing failure on audio-less clips.

    TikTok slideshows and muted clips have no audio stream, so ffprobe warns
    and yt-dlp's FFmpegExtractAudio postprocessor escalates it to a hard
    error ("ERROR: Postprocessing: WARNING: unable to obtain file audio
    codec with ffprobe"). Deliberately narrow: unrelated failures (e.g. an
    IP block) must still propagate and fail the extraction.
    """
    msg = str(exc).lower()
    return "postprocessing" in msg and "audio codec" in msg and "ffprobe" in msg


def _build_caption_text(info: dict) -> str | None:
    """Compact Uploader/Description/Hashtags block from yt-dlp metadata.

    Skips any part that is empty. Hashtags already visible inline in the
    description (common on TikTok) are not repeated from `info['tags']`.
    The whole block is capped at roughly CAPTION_MAX_CHARS by truncating
    the description, never the hashtags.
    """
    uploader = (info.get("uploader") or "").strip()
    description = (info.get("description") or "").strip()
    tags = info.get("tags") or []

    inline_hashtags = {m.group(0).lower() for m in _HASHTAG_RE.finditer(description)}
    extra_hashtags = []
    seen = set(inline_hashtags)
    for tag in tags:
        if not tag:
            continue
        hashtag = f"#{tag}"
        if hashtag.lower() in seen:
            continue
        seen.add(hashtag.lower())
        extra_hashtags.append(hashtag)

    uploader_line = f"Uploader: {uploader}" if uploader else ""
    hashtags_line = f"Hashtags: {' '.join(extra_hashtags)}" if extra_hashtags else ""

    description_line = ""
    if description:
        reserved = sum(len(line) + 1 for line in (uploader_line, hashtags_line) if line)
        budget = max(CAPTION_MAX_CHARS - reserved, 0)
        if len(description) > budget:
            description = description[:budget].rstrip() + "…" if budget > 1 else ""
        if description:
            description_line = f"Description: {description}"

    lines = [line for line in (uploader_line, description_line, hashtags_line) if line]
    return "\n".join(lines) if lines else None


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
            try:
                info = ydl.extract_info(url, download=True)
            except Exception as e:
                if not _is_silent_video_error(e):
                    raise
                info = ydl.extract_info(url, download=False)
                caption = _build_caption_text(info)
                return ExtractResult(
                    platform=self.platform,
                    media_type="text",
                    media_path=None,
                    text_content=caption,
                    caption_text=caption,
                    title=info.get("title")
                    or info.get("description")
                    or f"{self.platform.title()} {info.get('id')}",
                    metadata={
                        "author": info.get("uploader"),
                        "video_id": info.get("id"),
                        "source_url": url,
                        "degraded_reason": "silent-video-no-audio-stream",
                    },
                )
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
            title=info.get("title")
            or info.get("description", f"{self.platform.title()} {info.get('id')}"),
            caption_text=_build_caption_text(info),
            metadata={
                "author": info.get("uploader"),
                "video_id": info.get("id"),
                "source_url": url,
            },
        )
