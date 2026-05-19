from pathlib import Path

from click.testing import CliRunner

from sift.cli import main


def test_add_then_run_creates_capture(tmp_path: Path):
    runner = CliRunner()
    vault = tmp_path / "vault"
    runner.invoke(main, ["init", str(vault)])

    result = runner.invoke(main, ["add", "https://example.com/foo", "--vault", str(vault)])
    assert result.exit_code == 0, result.output

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
