import re
from pathlib import Path
from urllib.parse import urlparse

import httpx
from yt_dlp import YoutubeDL
from yt_dlp.utils import DownloadError

from sift.extractors.base import Extractor, ExtractResult, resolve_ffmpeg_location

try:
    from playwright.sync_api import sync_playwright as _sync_playwright
    _PLAYWRIGHT_AVAILABLE = True
except ImportError:
    _sync_playwright = None
    _PLAYWRIGHT_AVAILABLE = False

_HOSTS = {"twitter.com", "www.twitter.com", "x.com", "www.x.com", "t.co"}
_TWEET_ID_RE = re.compile(r"/status/(\d+)")
_FXTWITTER_API = "https://api.fxtwitter.com/status/{tweet_id}"
_ARTICLE_RE = re.compile(r"x\.com/i/article/")


def _extract_tweet_id(url: str) -> str | None:
    m = _TWEET_ID_RE.search(url)
    return m.group(1) if m else None


def _fetch_via_fxtwitter(url: str) -> tuple[ExtractResult, bool]:
    """Returns (result, has_video). has_video=True means yt-dlp should be tried."""
    tweet_id = _extract_tweet_id(url)
    if not tweet_id:
        raise ValueError(f"Cannot extract tweet ID from URL: {url}")
    api_url = _FXTWITTER_API.format(tweet_id=tweet_id)
    headers = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}
    resp = httpx.get(api_url, timeout=15, follow_redirects=True, headers=headers)
    resp.raise_for_status()
    data = resp.json().get("tweet", {})
    text = data.get("text", "")
    author = data.get("author", {})
    author_name = author.get("name", "")
    screen_name = author.get("screen_name", "")
    has_video = bool(data.get("media", {}).get("videos"))
    result = ExtractResult(
        platform="twitter",
        media_type="text",
        text_content=text,
        title=f"@{screen_name}: {text[:80]}".rstrip(),
        metadata={
            "author": author_name,
            "screen_name": screen_name,
            "tweet_id": tweet_id,
            "source_url": url,
        },
    )
    return result, has_video


def _fetch_article_via_playwright(url: str) -> ExtractResult:
    if not _PLAYWRIGHT_AVAILABLE:
        raise RuntimeError(
            "X article extraction requires Playwright. "
            "Run: playwright install chromium"
        )

    with _sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            # Block images/fonts to speed up load
            page.route("**/*.{png,jpg,jpeg,gif,webp,svg,woff,woff2,ttf}", lambda r: r.abort())
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
            # Wait for article body to appear
            try:
                page.wait_for_selector("[data-testid='article-content'], article, main", timeout=10000)
            except Exception:
                pass

            title = page.title().replace(" / X", "").strip()
            # Grab visible text from the article area, fall back to body
            try:
                content = page.locator("[data-testid='article-content']").inner_text(timeout=5000)
            except Exception:
                try:
                    content = page.locator("article").inner_text(timeout=5000)
                except Exception:
                    content = page.locator("body").inner_text(timeout=5000)
        finally:
            browser.close()

    return ExtractResult(
        platform="twitter",
        media_type="text",
        text_content=content.strip(),
        title=title or "X Article",
        metadata={"source_url": url, "extraction_method": "playwright"},
    )


class TwitterExtractor(Extractor):
    platform = "twitter"

    def can_handle(self, hostname: str) -> bool:
        return hostname.lower() in _HOSTS

    def extract(self, url: str, work_dir: Path) -> ExtractResult:
        # Resolve t.co short links before anything else
        parsed = urlparse(url)
        if parsed.hostname and parsed.hostname.lower() == "t.co":
            resp = httpx.head(url, timeout=10, follow_redirects=True)
            url = str(resp.url)
            # Some t.co links return HTTP 200 with a meta-refresh page instead of a 302.
            # In that case resp.url is still a t.co URL; parse the body for the real target.
            resolved = urlparse(url)
            if resolved.hostname and resolved.hostname.lower() == "t.co":
                body_resp = httpx.get(url, timeout=10, follow_redirects=True)
                meta_match = re.search(
                    r'content=["\']0;url=([^"\']+)["\']', body_resp.text, re.IGNORECASE
                )
                if meta_match:
                    url = meta_match.group(1)
                else:
                    raise ValueError(
                        f"t.co URL did not redirect via HTTP 302 or meta-refresh: {url}"
                    )

        # X articles bypass fxtwitter
        if _ARTICLE_RE.search(url):
            return _fetch_article_via_playwright(url)

        # fxtwitter first — instant for text/photo tweets, also tells us if video exists
        fx_result, has_video = _fetch_via_fxtwitter(url)
        if not has_video:
            return fx_result

        # Video tweet: use yt-dlp to extract audio
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
        if ffmpeg_dir:
            opts["ffmpeg_location"] = ffmpeg_dir
        try:
            with YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=True)
            media_path = next(work_dir.glob(f"{info['id']}.mp3"), None)
            if media_path is None:
                raise RuntimeError(
                    f"yt-dlp reported success but expected mp3 not found in {work_dir} "
                    f"for tweet {info.get('id')}. ffmpeg post-processing may have failed "
                    f"or produced an unexpected file extension."
                )
            return ExtractResult(
                platform="twitter",
                media_type="audio",
                media_path=media_path,
                title=info.get("title") or info.get("description", f"Tweet {info.get('id')}"),
                metadata={
                    "author": info.get("uploader"),
                    "tweet_id": info.get("id"),
                    "source_url": url,
                },
            )
        except DownloadError as exc:
            # yt-dlp failed on video — fall back to fxtwitter text result
            fx_result.metadata["extraction_warning"] = (
                f"video download failed, captured text only: {str(exc)[:120]}"
            )
            return fx_result
