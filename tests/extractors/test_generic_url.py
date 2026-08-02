from pathlib import Path

import httpx

from sift.extractors.generic_url import GenericUrlExtractor

_HTML = """
<html><head><title>Article Title</title></head>
<body>
  <article>
    <h1>Article Title</h1>
    <p>This is the body of the article. It has some content.</p>
  </article>
</body></html>
"""


def test_can_handle_anything_returns_true():
    e = GenericUrlExtractor()
    assert e.can_handle("example.com")
    assert e.can_handle("any-random-blog.io")


def test_extract_parses_readability_output(tmp_path: Path):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=_HTML)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    e = GenericUrlExtractor(http_client=client)

    result = e.extract("https://example.com/post", tmp_path)

    assert result.platform == "generic"
    assert result.media_type == "text"
    assert result.title == "Article Title"
    assert "body of the article" in result.text_content


def test_extract_sends_browser_user_agent(tmp_path: Path):
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["user_agent"] = request.headers.get("user-agent", "")
        return httpx.Response(200, text=_HTML)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    e = GenericUrlExtractor(http_client=client)

    e.extract("https://example.com/post", tmp_path)

    assert "Mozilla" in captured["user_agent"]


def test_extract_default_client_accepts_real_httpx_kwargs(tmp_path: Path, monkeypatch):
    """Regression: httpx.get() (module-level) does not accept max_redirects,
    only httpx.Client(...) does. This exercises the real, unmocked
    construction of httpx.Client(follow_redirects=True, max_redirects=5,
    timeout=30.0) that extract() performs when no client is injected - if
    that call signature were wrong (e.g. still calling httpx.get with
    max_redirects), this would raise TypeError instead of returning a result.
    """

    def fake_get(self, url, **kwargs):
        return httpx.Response(200, text=_HTML, request=httpx.Request("GET", url))

    monkeypatch.setattr(httpx.Client, "get", fake_get)

    e = GenericUrlExtractor()
    result = e.extract("https://example.com/post", tmp_path)

    assert result.media_type == "text"
    assert "body of the article" in result.text_content
