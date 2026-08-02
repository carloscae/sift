import json
import subprocess
from unittest.mock import patch

import pytest

from sift.enricher.claude_cli import ClaudeCliEnricher

VALID_JSON = json.dumps(
    {"title": "A Title", "summary": "A summary.", "tags": ["one", "two"]}
)


def _completed(returncode: int, stdout: str = "", stderr: str = "") -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(
        args=["claude", "-p"], returncode=returncode, stdout=stdout.encode(), stderr=stderr.encode()
    )


@pytest.fixture
def enricher() -> ClaudeCliEnricher:
    return ClaudeCliEnricher(claude_bin="claude")


def test_summarise_pins_model_and_strict_mcp_config(enricher: ClaudeCliEnricher):
    """No model pinned + MCP servers loaded for a single JSON call was the
    root cause of Carlos's opusplan-drift and unauthorized-MCP failures."""
    with patch(
        "sift.enricher.claude_cli.subprocess.run", return_value=_completed(0, VALID_JSON)
    ) as mock_run:
        enricher.summarise("some text")

    argv = mock_run.call_args.args[0]
    assert "--model" in argv
    assert argv[argv.index("--model") + 1] == "sonnet"
    assert "--strict-mcp-config" in argv
    assert mock_run.call_args.kwargs["timeout"] == 180


def test_summarise_model_is_configurable():
    enricher = ClaudeCliEnricher(claude_bin="claude", model="opus")
    with patch(
        "sift.enricher.claude_cli.subprocess.run", return_value=_completed(0, VALID_JSON)
    ) as mock_run:
        enricher.summarise("some text")

    argv = mock_run.call_args.args[0]
    assert argv[argv.index("--model") + 1] == "opus"


def test_summarise_retries_once_on_nonzero_exit_then_succeeds(enricher: ClaudeCliEnricher):
    """Six of sixteen logged failures were 'claude CLI exited 1' with empty
    stderr — a single retry with backoff makes these survivable."""
    with patch(
        "sift.enricher.claude_cli.subprocess.run",
        side_effect=[_completed(1, "", ""), _completed(0, VALID_JSON)],
    ) as mock_run, patch("sift.enricher.claude_cli.time.sleep") as mock_sleep:
        result = enricher.summarise("some text")

    assert result.title == "A Title"
    assert mock_run.call_count == 2
    mock_sleep.assert_called_once()


def test_summarise_retries_once_on_timeout_then_succeeds(enricher: ClaudeCliEnricher):
    """Two logged failures were 60s timeouts — raise the budget and retry once."""
    timeout_exc = subprocess.TimeoutExpired(cmd=["claude", "-p"], timeout=180)
    with patch(
        "sift.enricher.claude_cli.subprocess.run",
        side_effect=[timeout_exc, _completed(0, VALID_JSON)],
    ) as mock_run, patch("sift.enricher.claude_cli.time.sleep") as mock_sleep:
        result = enricher.summarise("some text")

    assert result.title == "A Title"
    assert mock_run.call_count == 2
    mock_sleep.assert_called_once()


def test_summarise_raises_after_both_attempts_fail(enricher: ClaudeCliEnricher):
    with patch(
        "sift.enricher.claude_cli.subprocess.run",
        side_effect=[_completed(1, "", "boom"), _completed(1, "", "boom again")],
    ), patch("sift.enricher.claude_cli.time.sleep"), pytest.raises(RuntimeError):
        enricher.summarise("some text")


def test_summarise_tolerates_noise_around_json_object(enricher: ClaudeCliEnricher):
    """Defensive JSON parsing: extract the outermost {...} rather than
    assuming the whole of stdout is the object — survives stray text around
    it (e.g. a stray warning line the CLI printed to stdout)."""
    noisy = f"Some stray preamble line\n{VALID_JSON}\ntrailing noise"
    with patch("sift.enricher.claude_cli.subprocess.run", return_value=_completed(0, noisy)):
        result = enricher.summarise("some text")

    assert result.title == "A Title"
    assert result.summary == "A summary."
    assert result.tags == ["one", "two"]


def test_summarise_still_strips_markdown_fences(enricher: ClaudeCliEnricher):
    fenced = f"```json\n{VALID_JSON}\n```"
    with patch("sift.enricher.claude_cli.subprocess.run", return_value=_completed(0, fenced)):
        result = enricher.summarise("some text")

    assert result.title == "A Title"
