from pathlib import Path

import pytest

from sift.config import Config, load_config


def test_load_config_resolves_paths(tmp_vault: Path):
    config_path = tmp_vault / "vault-ingest.yaml"
    config_path.write_text(
        f"vault: {tmp_vault}\n"
        "raw_dir: raw\n"
        "output_dir: captures\n"
        "state_dir: .vault-ingest\n"
        "raw_ttl_days: 7\n"
        "enricher:\n"
        "  backend: openrouter\n"
        "  openrouter:\n"
        "    api_key_env: OPENROUTER_API_KEY\n"
        "    model_stt: groq/whisper-large-v3-turbo\n"
        "    model_text: google/gemini-2.5-flash-lite\n"
        "    model_vision: google/gemini-2.5-flash\n"
    )

    config = load_config(config_path)

    assert isinstance(config, Config)
    assert config.vault == tmp_vault
    assert config.raw_path == tmp_vault / "raw"
    assert config.captures_path == tmp_vault / "captures"
    assert config.state_path == tmp_vault / ".vault-ingest"
    assert config.raw_ttl_days == 7
    assert config.enricher.backend == "openrouter"
    assert config.enricher.openrouter.model_stt == "groq/whisper-large-v3-turbo"


def test_load_config_missing_file_raises(tmp_path: Path):
    with pytest.raises(FileNotFoundError):
        load_config(tmp_path / "nope.yaml")
