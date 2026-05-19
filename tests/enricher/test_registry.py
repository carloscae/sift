import os
from unittest.mock import patch

import pytest

from sift.config import Config, EnricherConfig, OpenRouterConfig
from sift.enricher.openrouter import OpenRouterEnricher
from sift.enricher.registry import build_enricher


def test_build_openrouter_enricher_from_config(tmp_path):
    cfg = Config(
        vault=tmp_path,
        enricher=EnricherConfig(
            backend="openrouter",
            openrouter=OpenRouterConfig(api_key_env="MY_OR_KEY"),
        ),
    )
    with patch.dict(os.environ, {"MY_OR_KEY": "sk-or-xyz"}):
        enricher = build_enricher(cfg)
    assert isinstance(enricher, OpenRouterEnricher)
    assert enricher.api_key == "sk-or-xyz"


def test_missing_api_key_raises(tmp_path):
    cfg = Config(
        vault=tmp_path,
        enricher=EnricherConfig(
            backend="openrouter",
            openrouter=OpenRouterConfig(api_key_env="DEFINITELY_NOT_SET"),
        ),
    )
    with pytest.raises(RuntimeError, match="DEFINITELY_NOT_SET"):
        build_enricher(cfg)


def test_unknown_backend_raises(tmp_path):
    cfg = Config(vault=tmp_path, enricher=EnricherConfig(backend="local"))
    with pytest.raises(NotImplementedError, match="local"):
        build_enricher(cfg)
