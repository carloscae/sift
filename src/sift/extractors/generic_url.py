from pathlib import Path

import httpx
from readability import Document

from sift.extractors.base import Extractor, ExtractResult


class GenericUrlExtractor(Extractor):
    """Catch-all for article URLs. Registered last in the dispatch chain."""

    platform = "generic"

    def can_handle(self, hostname: str) -> bool:
        return True

    def extract(self, url: str, work_dir: Path) -> ExtractResult:
        resp = httpx.get(url, follow_redirects=True, timeout=30.0)
        resp.raise_for_status()

        doc = Document(resp.text)
        title = doc.short_title() or "Untitled"
        from lxml.html import fromstring
        body_html = doc.summary()
        text = fromstring(body_html).text_content().strip()

        return ExtractResult(
            platform="generic",
            media_type="text",
            title=title,
            text_content=text,
            metadata={"source_url": url, "content_length": len(text)},
        )
