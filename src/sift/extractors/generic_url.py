from pathlib import Path

import httpx
from lxml.html import fromstring
from readability import Document

from sift.extractors.base import Extractor, ExtractResult

# httpx.get() (module-level) does not accept max_redirects - that's a
# Client.__init__ parameter only. Bare httpx also gets 403'd by a lot of
# sites, so send a browser-like User-Agent too.
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)


class GenericUrlExtractor(Extractor):
    """Catch-all for article URLs. Registered last in the dispatch chain."""

    platform = "generic"

    def __init__(self, http_client: httpx.Client | None = None) -> None:
        """`http_client` is injectable for tests; production leaves it None
        and a short-lived client is created per request."""
        self._http_client = http_client

    def can_handle(self, hostname: str) -> bool:
        return True

    def extract(self, url: str, work_dir: Path) -> ExtractResult:
        headers = {"User-Agent": USER_AGENT}
        if self._http_client is not None:
            resp = self._http_client.get(url, headers=headers)
        else:
            with httpx.Client(follow_redirects=True, max_redirects=5, timeout=30.0) as client:
                resp = client.get(url, headers=headers)
        resp.raise_for_status()

        doc = Document(resp.text)
        title = doc.short_title() or "Untitled"
        body_html = doc.summary()
        text = fromstring(body_html).text_content().strip()

        return ExtractResult(
            platform="generic",
            media_type="text",
            title=title,
            text_content=text,
            metadata={"source_url": url, "content_length": len(text)},
        )
