from pathlib import Path
from unittest.mock import patch

from click.testing import CliRunner

from sift.cli import main
from sift.extractors.base import ExtractFailure


def _stub_failure(url: str = "https://example.com") -> ExtractFailure:
    return ExtractFailure(
        url=url,
        platform="generic",
        error_class="unknown",
        error_detail="(no extraction in this test)",
    )


def test_add_then_run_creates_capture(tmp_path: Path):
    runner = CliRunner()
    vault = tmp_path / "vault"
    runner.invoke(main, ["init", str(vault)])

    result = runner.invoke(main, ["add", "https://example.com/foo", "--vault", str(vault)])
    assert result.exit_code == 0, result.output

    with patch("sift.pipeline.dispatch_extract", return_value=_stub_failure()):
        result = runner.invoke(main, ["run", "--vault", str(vault)])
    assert result.exit_code == 0, result.output

    captures = list((vault / "captures").glob("*.md"))
    assert len(captures) == 1


def test_add_file_path(tmp_path: Path):
    runner = CliRunner()
    vault = tmp_path / "vault"
    runner.invoke(main, ["init", str(vault)])

    voice = tmp_path / "voice.mp3"
    voice.write_bytes(b"x")

    result = runner.invoke(main, ["add", str(voice), "--vault", str(vault)])
    assert result.exit_code == 0, result.output
    assert any((vault / "raw").iterdir())


def test_status_reports_pending(tmp_path: Path):
    runner = CliRunner()
    vault = tmp_path / "vault"
    runner.invoke(main, ["init", str(vault)])
    runner.invoke(main, ["add", "https://example.com", "--vault", str(vault)])

    result = runner.invoke(main, ["status", "--vault", str(vault)])
    assert result.exit_code == 0
    assert "1 pending" in result.output


def test_add_uses_config_flag(tmp_path: Path):
    """`sift add --config <path>` reads from a custom config location."""
    runner = CliRunner()
    vault = tmp_path / "vault"
    custom_config = tmp_path / "elsewhere" / "sift.yaml"
    custom_config.parent.mkdir()
    runner.invoke(main, ["init", str(vault), "--config", str(custom_config)])

    result = runner.invoke(
        main, ["add", "https://example.com/foo", "--config", str(custom_config)]
    )
    assert result.exit_code == 0, result.output
    # Queue file should be created based on vault from the custom config.
    assert (vault / ".vault-ingest" / "queue.json").is_file()


def test_add_uses_sift_config_env(tmp_path: Path, monkeypatch):
    """SIFT_CONFIG env var resolves the config path when --config not given."""
    runner = CliRunner()
    vault = tmp_path / "vault"
    custom_config = tmp_path / "envcfg" / "sift.yaml"
    custom_config.parent.mkdir()
    runner.invoke(main, ["init", str(vault), "--config", str(custom_config)])

    monkeypatch.setenv("SIFT_CONFIG", str(custom_config))
    result = runner.invoke(main, ["add", "https://example.com/foo"])
    assert result.exit_code == 0, result.output
    assert (vault / ".vault-ingest" / "queue.json").is_file()


def test_add_now_does_not_claim_processed_specific_item(tmp_path: Path):
    """--now should not claim it processed only the new item."""
    runner = CliRunner()
    vault = tmp_path / "vault"
    runner.invoke(main, ["init", str(vault)])
    runner.invoke(main, ["add", "https://a.com", "--vault", str(vault)])  # pre-existing pending

    with patch("sift.pipeline.dispatch_extract", return_value=_stub_failure()):
        result = runner.invoke(main, ["add", "https://b.com", "--now", "--vault", str(vault)])
    assert result.exit_code == 0
    # Should not contain a specific item_id claim — should be the new generic message.
    assert "Processed item " not in result.output
    assert "Queue processed" in result.output
    # Both items should now be processed (2 captures emitted).
    captures = list((vault / "captures").glob("*.md"))
    assert len(captures) == 2
