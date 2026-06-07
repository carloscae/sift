from pathlib import Path

import pytest
from pydantic import ValidationError

from sift.config import Config, load_config


def test_load_config_resolves_paths(tmp_vault: Path):
    config_path = tmp_vault / "vault-ingest.yaml"
    config_path.write_text(
        f"vault: {tmp_vault}\n"
        "raw_dir: raw\n"
        "output_dir: captures\n"
        "state_dir: .vault-ingest\n"
        "enricher:\n"
        "  backend: openrouter\n"
        "  openrouter:\n"
        "    api_key_env: OPENROUTER_API_KEY\n"
        "    model_text: google/gemini-2.5-flash-lite\n"
        "    model_vision: google/gemini-2.5-flash\n"
        "    whisper_svc_url: http://localhost:8742\n"
    )

    config = load_config(config_path)

    assert isinstance(config, Config)
    assert config.vault == tmp_vault
    assert config.raw_path == tmp_vault / "raw"
    assert config.captures_path == tmp_vault / "captures"
    assert config.state_path == tmp_vault / ".vault-ingest"
    assert config.enricher.backend == "openrouter"
    assert config.enricher.openrouter.whisper_svc_url == "http://localhost:8742"


def test_load_config_missing_file_raises(tmp_path: Path):
    with pytest.raises(FileNotFoundError):
        load_config(tmp_path / "nope.yaml")


def test_invalid_backend_raises_validation_error(tmp_vault: Path):
    config_path = tmp_vault / "vault-ingest-bad-backend.yaml"
    config_path.write_text(
        f"vault: {tmp_vault}\n"
        "enricher:\n"
        "  backend: claude_cli\n"  # underscore instead of hyphen — must be rejected
    )

    with pytest.raises(ValidationError):
        load_config(config_path)
