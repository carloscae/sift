from pathlib import Path

import pytest


@pytest.fixture
def tmp_vault(tmp_path: Path) -> Path:
    """A scratch vault dir with raw/, captures/, .vault-ingest/ created."""
    (tmp_path / "raw").mkdir()
    (tmp_path / "captures").mkdir()
    (tmp_path / ".vault-ingest").mkdir()
    return tmp_path


@pytest.fixture(autouse=True)
def _clear_extractor_registry():
    """Drop any registered extractors before each test so module-level state
    from `sift.extractors` side-effect imports doesn't leak between tests."""
    try:
        from sift.extractors.base import clear_registry
        clear_registry()
    except ImportError:
        # base.py doesn't exist yet (Phase 0–1 tests run before Phase 2).
        pass
    yield
