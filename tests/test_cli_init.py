from pathlib import Path

from click.testing import CliRunner

from sift.cli import main


def test_init_creates_vault_scaffolding(tmp_path: Path):
    runner = CliRunner()
    result = runner.invoke(main, ["init", str(tmp_path)])
    assert result.exit_code == 0, result.output
    assert (tmp_path / "raw").is_dir()
    assert (tmp_path / "captures").is_dir()
    assert (tmp_path / ".vault-ingest").is_dir()
    assert (tmp_path / "vault-ingest.yaml").is_file()


def test_init_writes_config_pointing_at_vault(tmp_path: Path):
    runner = CliRunner()
    runner.invoke(main, ["init", str(tmp_path)])
    config = (tmp_path / "vault-ingest.yaml").read_text()
    assert f"vault: {tmp_path}" in config
    assert "raw_dir: raw" in config
