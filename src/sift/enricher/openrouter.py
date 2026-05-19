from pathlib import Path

import httpx
import structlog

from sift.enricher.base import (
    CaptionResult,
    Enricher,
    SummaryResult,
    TranscriptResult,
)

logger = structlog.get_logger()

_OR_BASE = "https://openrouter.ai/api/v1"

_STT_COST_PER_SEC = {
    "groq/whisper-large-v3-turbo": 0.000011,
    "openai/whisper-1": 0.0001,
}
_DEFAULT_STT_COST_PER_SEC = 0.0001


class OpenRouterEnricher(Enricher):
    def __init__(
        self,
        api_key: str,
        model_stt: str,
        model_text: str,
        model_vision: str,
        client: httpx.Client | None = None,
    ):
        self.api_key = api_key
        self.model_stt = model_stt
        self.model_text = model_text
        self.model_vision = model_vision
        self._client = client or httpx.Client(timeout=120.0)

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "HTTP-Referer": "https://github.com/carloscae/sift",
            "X-Title": "sift",
        }

    def transcribe(self, audio_path: Path) -> TranscriptResult:
        with audio_path.open("rb") as f:
            files = {"file": (audio_path.name, f, "audio/mpeg")}
            data = {"model": self.model_stt}
            resp = self._client.post(
                f"{_OR_BASE}/audio/transcriptions",
                headers=self._headers(),
                files=files,
                data=data,
            )
        resp.raise_for_status()
        body = resp.json()

        duration = body.get("usage", {}).get("input_audio_seconds", 0)
        per_sec = _STT_COST_PER_SEC.get(self.model_stt, _DEFAULT_STT_COST_PER_SEC)
        cost = duration * per_sec

        return TranscriptResult(
            text=body["text"],
            model=self.model_stt,
            cost_usd=round(cost, 6),
            duration_sec=duration or None,
        )

    def caption(self, image_path: Path) -> CaptionResult:
        raise NotImplementedError("caption() implemented in Task 3.4")

    def summarise(self, text: str, context: dict | None = None) -> SummaryResult:
        raise NotImplementedError("summarise() implemented in Task 3.3")
