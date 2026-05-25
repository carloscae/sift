import re
from pathlib import Path
from urllib.parse import urlparse

import httpx
from yt_dlp import YoutubeDL
from yt_dlp.utils import DownloadError

from sift.extractors.base import Extractor, ExtractResult

_HOSTS = {"twitter.com", "www.twitter.com", "x.com", "www.x.com", "t.co"}
_TWEET_ID_RE = re.compile(r"/status/(\d+)")
_FXTWITTER_API = "https://api.fxtwitter.com/status/{tweet_id}"
_ARTICLE_RE = re.compile(r"x\.com/i/article/")


def _extract_tweet_id(url: str) -> str | None:
    m = _TWEET_ID_RE.search(url)
    return m.group(1) if m else None


def _fetch_via_fxtwitter(url: str) -> ExtractResult:
    tweet_id = _extract_tweet_id(url)
    if not tweet_id:
        raise ValueError(f"Cannot extract tweet ID from URL: {url}")
    api_url = _FXTWITTER_API.format(tweet_id=tweet_id)
    resp = httpx.get(api_url, timeout=15, follow_redirects=True)
    resp.raise_for_status()
    data = resp.json().get("tweet", {})
    text = data.get("text", "")
    author = data.get("author", {})
    author_name = author.get("name", "")
    screen_name = author.get("screen_name", "")
    return ExtractResult(
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


def _fetch_article_via_playwright(url: str) -> ExtractResult:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
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

        # Try yt-dlp first — works for video tweets
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
        try:
            with YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=True)
            media_path = next(work_dir.glob(f"{info['id']}.mp3"), None)
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
        except DownloadError as e:
            # yt-dlp redirected to a Twitter Article — use Playwright
            if _ARTICLE_RE.search(str(e)):
                return _fetch_article_via_playwright(url)
            # No video — fall back to fxtwitter for text/thread extraction
            return _fetch_via_fxtwitter(url)
