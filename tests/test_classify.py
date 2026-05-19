from pathlib import Path

from sift.classify import ItemKind, classify_path, classify_url


def test_classify_url_tiktok():
    item = classify_url("https://www.tiktok.com/@user/video/123")
    assert item.kind == ItemKind.URL
    assert item.platform == "tiktok"


def test_classify_url_youtube():
    assert classify_url("https://youtu.be/abc123").platform == "youtube"
    assert classify_url("https://www.youtube.com/watch?v=abc").platform == "youtube"
    assert classify_url("https://www.youtube.com/shorts/abc").platform == "youtube"


def test_classify_url_generic():
    item = classify_url("https://example.com/article")
    assert item.kind == ItemKind.URL
    assert item.platform == "generic"


def test_classify_path_audio(tmp_path: Path):
    audio = tmp_path / "voice.mp3"
    audio.write_bytes(b"")
    assert classify_path(audio).kind == ItemKind.AUDIO


def test_classify_path_image(tmp_path: Path):
    img = tmp_path / "screenshot.png"
    img.write_bytes(b"")
    assert classify_path(img).kind == ItemKind.IMAGE


def test_classify_path_url_file(tmp_path: Path):
    url_file = tmp_path / "link.url"
    url_file.write_text("https://tiktok.com/foo\n")
    item = classify_path(url_file)
    assert item.kind == ItemKind.URL
    assert item.platform == "tiktok"
    assert item.source == "https://tiktok.com/foo"
