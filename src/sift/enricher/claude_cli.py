import json
import re
import shutil
import subprocess
import time
from pathlib import Path

import httpx
import structlog

from sift.enricher.base import CaptionResult, Enricher, SummaryResult, TranscriptResult

logger = structlog.get_logger()

# Raised the 60s that was in place before: six of sixteen logged watcher
# failures were bare "claude CLI exited 1" with empty stderr, plus two 60s
# timeouts. A realistic 4.3k-char prompt measured ~10s end-to-end on the
# actual machine, so latency isn't the routine problem — this budget is
# about surviving a slow moment, not raising the normal case.
_SUMMARISE_TIMEOUT_SEC = 180
_RETRY_BACKOFF_SEC = 2
_JSON_OBJECT_RE = re.compile(r"\{.*\}", re.DOTALL)


def _extract_json_object(raw: str) -> str:
    """Return the outermost {...} block found in *raw*.

    Defensive against the CLI wrapping JSON in markdown fences (stripped
    before this is called) or emitting stray text around the object —
    cheap insurance against the empty-stderr failures where stdout wasn't
    exactly the bare JSON object.
    """
    match = _JSON_OBJECT_RE.search(raw)
    if not match:
        raise ValueError(f"no JSON object found in claude CLI output: {raw[:200]!r}")
    return match.group(0)

_SUMMARISE_PROMPT = """\
You receive text from a web capture (article, tweet thread, video transcript, etc).
Analyze it critically and return ONLY a JSON object with these keys:
- title: string, <=80 chars, descriptive headline
- summary: string, markdown-formatted analysis using this exact structure:
    One sentence verdict (credibility, usefulness, or both). Direct and opinionated — no hedging.

    **Worth knowing:**
    - 2-4 bullets of genuinely useful or accurate points with enough specific detail to be \
actionable in a future conversation without re-reading the source. If reader context is \
provided, flag relevance to their specific workflows.

    **Weak:** one sentence on what is inaccurate, hyped, fabricated, or missing. Omit if \
nothing is weak.
- tags: array of 2-5 lowercase strings

No prose outside the JSON, just the JSON object."""


def _build_prompt(user_context: str | None) -> str:
    if not user_context:
        return _SUMMARISE_PROMPT
    return (
        _SUMMARISE_PROMPT
        + f"\n\nReader context (use to personalise relevance judgments):\n{user_context}"
    )


class ClaudeCliEnricher(Enricher):
    def __init__(
        self,
        claude_bin: str = "claude",
        whisper_svc_url: str = "http://localhost:8742",
        user_context: str | None = None,
        client: httpx.Client | None = None,
        model: str = "sonnet",
    ):
        resolved = shutil.which(claude_bin) or claude_bin
        self.claude_bin = resolved
        self.whisper_svc_url = whisper_svc_url.rstrip("/")
        self._prompt = _build_prompt(user_context)
        self._client = client or httpx.Client(timeout=120.0)
        # Pinned so Carlos's default model (opusplan) can't silently change
        # what backs every capture's summary. Not yet wired through
        # vault-ingest.yaml (enricher.claude_cli.model) — that requires a
        # Config field and registry.py wiring outside this session's file
        # ownership; "sonnet" is hardcoded as the default until then.
        self.model = model

    def transcribe(self, audio_path: Path) -> TranscriptResult:
        with audio_path.open("rb") as f:
            resp = self._client.post(
                f"{self.whisper_svc_url}/transcribe",
                files={"file": (audio_path.name, f, "audio/mpeg")},
                timeout=300.0,
            )
        resp.raise_for_status()
        body = resp.json()
        return TranscriptResult(
            text=body["transcript"],
            model=body.get("model", "whisper-large-v3-turbo"),
            cost_usd=0.0,
        )

    def caption(self, image_path: Path) -> CaptionResult:
        raise NotImplementedError(
            "claude-cli backend does not support image captioning; use openrouter for vision tasks"
        )

    def summarise(self, text: str, context: dict | None = None) -> SummaryResult:
        ctx = context or {}
        user_content = (
            f"Source: {ctx.get('source', 'unknown')}\n"
            f"Platform: {ctx.get('platform', 'unknown')}\n\n"
            f"Content:\n{text[:8000]}"
        )
        prompt = f"{self._prompt}\n\n{user_content}"
        argv = [self.claude_bin, "-p", "--model", self.model, "--strict-mcp-config"]

        last_error: Exception | None = None
        for attempt in (1, 2):
            try:
                result = subprocess.run(
                    argv,
                    input=prompt.encode(),
                    capture_output=True,
                    timeout=_SUMMARISE_TIMEOUT_SEC,
                )
            except subprocess.TimeoutExpired:
                last_error = RuntimeError(
                    f"claude CLI timed out after {_SUMMARISE_TIMEOUT_SEC}s"
                )
                logger.warning("claude-cli-timeout", attempt=attempt)
            else:
                if result.returncode != 0:
                    last_error = RuntimeError(
                        f"claude CLI exited {result.returncode}: "
                        f"{result.stderr.decode(errors='replace')[:300]}"
                    )
                    logger.warning(
                        "claude-cli-nonzero-exit", attempt=attempt, returncode=result.returncode
                    )
                else:
                    raw = result.stdout.decode(errors="replace").strip()
                    # Strip markdown code fences if present
                    if raw.startswith("```"):
                        raw = "\n".join(raw.splitlines()[1:])
                        if raw.endswith("```"):
                            raw = raw[: raw.rfind("```")]
                    try:
                        data = json.loads(_extract_json_object(raw))
                    except (ValueError, json.JSONDecodeError) as exc:
                        last_error = RuntimeError(
                            f"claude CLI returned unparseable output: {raw[:200]!r}"
                        )
                        logger.warning(
                            "claude-cli-unparseable-output", attempt=attempt, error=str(exc)
                        )
                    else:
                        return SummaryResult(
                            title=data.get("title", "Untitled")[:80],
                            summary=data.get("summary", ""),
                            tags=[t.lower() for t in data.get("tags", [])][:5],
                            model="claude-cli",
                            cost_usd=0.0,
                        )

            if attempt == 1:
                time.sleep(_RETRY_BACKOFF_SEC)

        raise last_error
