import os

from sift.config import Config
from sift.enricher.base import Enricher
from sift.enricher.openrouter import OpenRouterEnricher


def build_enricher(config: Config) -> Enricher:
    backend = config.enricher.backend
    if backend == "openrouter":
        or_cfg = config.enricher.openrouter
        api_key = os.environ.get(or_cfg.api_key_env)
        if not api_key:
            raise RuntimeError(
                f"OpenRouter API key not set: environment variable {or_cfg.api_key_env} is missing"
            )
        return OpenRouterEnricher(
            api_key=api_key,
            model_stt=or_cfg.model_stt,
            model_text=or_cfg.model_text,
            model_vision=or_cfg.model_vision,
        )
    if backend == "local":
        raise NotImplementedError("local enricher backend not yet implemented (v1.1)")
    raise ValueError(f"Unknown enricher backend: {backend}")
