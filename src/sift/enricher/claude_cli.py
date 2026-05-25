import json
import shutil
import subprocess
from pathlib import Path

import httpx
import structlog

from sift.enricher.base import CaptionResult, Enricher, SummaryResult, TranscriptResult

logger = structlog.get_logger()

_SUMMARISE_PROMPT = """\
You receive transcribed audio or extracted text from a web capture.
Return ONLY a JSON object with these keys:
- title: string, <=80 chars, descriptive headline
- summary: string, 2-3 sentences
- tags: array of 2-5 lowercase strings

No prose, no markdown, just the JSON object."""


class ClaudeCliEnricher(Enricher):
    def __init__(
        self,
        claude_bin: str = "claude",
        whisper_svc_url: str = "http://localhost:8742",
        client: httpx.Client | None = None,
    ):
        resolved = shutil.which(claude_bin) or claude_bin
        self.claude_bin = resolved
        self.whisper_svc_url = whisper_svc_url.rstrip("/")
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
        prompt = f"{_SUMMARISE_PROMPT}\n\n{user_content}"

        result = subprocess.run(
            [self.claude_bin, "-p", prompt],
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode != 0:
            raise RuntimeError(f"claude CLI exited {result.returncode}: {result.stderr[:300]}")

        raw = result.stdout.strip()
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
