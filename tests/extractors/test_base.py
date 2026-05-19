from pathlib import Path

from sift.extractors.base import (
    ExtractFailure,
    Extractor,
    ExtractResult,
    get_extractor,
    register_extractor,
)


class _FakeExtractor(Extractor):
    platform = "fake"

    def can_handle(self, hostname: str) -> bool:
        return hostname == "fake.com"

    def extract(self, url: str, work_dir: Path) -> ExtractResult:
        return ExtractResult(
            platform="fake",
            media_type="audio",
            title="Fake Title",
            metadata={"author": "someone"},
        )


def test_register_and_lookup():
    register_extractor(_FakeExtractor())
    extractor = get_extractor("fake.com")
    assert extractor is not None
    assert extractor.platform == "fake"


def test_unknown_hostname_returns_none():
    assert get_extractor("definitely-not-registered.example") is None


def test_extract_failure_carries_diagnostic_info():
    f = ExtractFailure(
        url="https://x.com/foo",
        platform="x",
        error_class="anti-scrape",
        error_detail="403 returned by twitter.com",
        suggested_t2="Save the post as screenshot and drop in raw/",
    )
    assert f.error_class == "anti-scrape"
    assert "screenshot" in f.suggested_t2
