from pathlib import Path

from sift.extractors.base import Extractor, ExtractResult, register_extractor
from sift.extractors.dispatch import dispatch_extract


class _Stub(Extractor):
    platform = "stub"

    def can_handle(self, hostname: str) -> bool:
        return hostname == "stub.example"

    def extract(self, url: str, work_dir: Path) -> ExtractResult:
        return ExtractResult(platform="stub", media_type="text", title="OK")


def test_dispatch_routes_by_hostname(tmp_path: Path):
    register_extractor(_Stub())
    result = dispatch_extract("https://stub.example/x", tmp_path)
    assert result.platform == "stub"
    assert result.title == "OK"


def test_dispatch_no_handler_returns_failure(tmp_path: Path):
    from sift.extractors.base import ExtractFailure
    result = dispatch_extract("https://no-handler-for-this.example/x", tmp_path)
    assert isinstance(result, ExtractFailure)
    assert result.error_class == "site-changed"
