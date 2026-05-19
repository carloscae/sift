from pathlib import Path
from unittest.mock import patch

from sift.extractors.generic_url import GenericUrlExtractor


def test_can_handle_anything_returns_true():
    e = GenericUrlExtractor()
    assert e.can_handle("example.com")
    assert e.can_handle("any-random-blog.io")


def test_extract_parses_readability_output(tmp_path: Path):
    e = GenericUrlExtractor()
    html = """
    <html><head><title>Article Title</title></head>
    <body>
      <article>
        <h1>Article Title</h1>
        <p>This is the body of the article. It has some content.</p>
      </article>
    </body></html>
    """

    with patch("sift.extractors.generic_url.httpx.get") as mock_get:
        mock_get.return_value.text = html
        mock_get.return_value.raise_for_status = lambda: None
        result = e.extract("https://example.com/post", tmp_path)

    assert result.platform == "generic"
    assert result.media_type == "text"
    assert result.title == "Article Title"
    assert "body of the article" in result.text_content
