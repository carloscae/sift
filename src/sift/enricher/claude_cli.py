import json
import shutil
import subprocess
from pathlib import Path

import httpx
import structlog

from sift.enricher.base import CaptionResult, Enricher, SummaryResult, TranscriptResult

logger = structlog.get_logger()

_SUMMARISE_PROMPT = """\
You receive text from a web capture (article, tweet thread, video transcript, etc).
Analyze it critically and return ONLY a JSON object with these keys:
- title: string, <=80 chars, descriptive headline
- summary: string, markdown-formatted analysis using this exact structure:
    One sentence verdict (credibility, usefulness, or both). Direct and opinionated — no hedging.

    **Worth knowing:**
    - 2-4 bullets of genuinely useful or accurate points with enough specific detail to be actionable \
in a future conversation without re-reading the source. If reader context is provided, flag relevance to \
their specific workflows.

    **Weak:** one sentence on what is inaccurate, hyped, fabricated, or missing. Omit if nothing is weak.
- tags: array of 2-5 lowercase strings

No prose outside the JSON, just the JSON object."""


def _build_prompt(user_context: str | None) -> str:
    if not user_context:
        return _SUMMARISE_PROMPT
    return _SUMMARISE_PROMPT + f"\n\nReader context (use to personalise relevance judgments):\n{user_context}"


class ClaudeCliEnricher(Enricher):
    def __init__(
        self,
        claude_bin: str = "claude",
        whisper_svc_url: str = "http://localhost:8742",
        user_context: str | None = None,
        client: httpx.Client | None = None,
    ):
        resolved = shutil.which(claude_bin) or claude_bin
        self.claude_bin = resolved
        self.whisper_svc_url = whisper_svc_url.rstrip("/")
        self._prompt = _build_prompt(user_context)
        self._client = client or httpx.Client(timeout=120.0)

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

        result = subprocess.run(
            [self.claude_bin, "-p"],
            input=prompt.encode(),
            capture_output=True,
            timeout=60,
        )
        if result.returncode != 0:
            raise RuntimeError(f"claude CLI exited {result.returncode}: {result.stderr.decode(errors='replace')[:300]}")

        raw = result.stdout.decode().strip()
        # Strip markdown code fences if present
        if raw.startswith("```"):
            raw = "\n".join(raw.splitlines()[1:])
            if raw.endswith("```"):
                raw = raw[: raw.rfind("```")]

        data = json.loads(raw)
        return SummaryResult(
            title=data.get("title", "Untitled")[:80],
            summary=data.get("summary", ""),
            tags=[t.lower() for t in data.get("tags", [])][:5],
            model="claude-cli",
            cost_usd=0.0,
        )
