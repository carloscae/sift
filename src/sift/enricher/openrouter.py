import json
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


def _raise_with_body(resp: httpx.Response, endpoint: str) -> None:
    """Like resp.raise_for_status() but includes the response body in the error message.

    OpenRouter (and most JSON APIs) put the real human-readable error in the body;
    httpx's default exception only shows the status code + URL.
    """
    if resp.is_success:
        return
    body_preview = resp.text[:500] if resp.text else ""
    raise httpx.HTTPStatusError(
        f"OpenRouter {endpoint} returned {resp.status_code}: {body_preview}",
        request=resp.request,
        response=resp,
    )


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
        _raise_with_body(resp, "/audio/transcriptions")
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
        import base64
        mime = {
            "png": "image/png",
            "jpg": "image/jpeg",
            "jpeg": "image/jpeg",
            "webp": "image/webp",
        }.get(image_path.suffix.lstrip(".").lower(), "image/jpeg")
        b64 = base64.b64encode(image_path.read_bytes()).decode()
        data_url = f"data:{mime};base64,{b64}"

        system_prompt = (
            "Describe the image, and if there is any readable text, extract it verbatim. "
            "Return a JSON object with keys: caption (string), ocr_text (string, '' if no text), "
            "tags (array of 2-5 lowercase string tags). Return ONLY the JSON."
        )

        payload = {
            "model": self.model_vision,
            "messages": [
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "Describe this image and extract any text."},
                        {"type": "image_url", "image_url": {"url": data_url}},
                    ],
                },
            ],
            "response_format": {"type": "json_object"},
        }
        resp = self._client.post(
            f"{_OR_BASE}/chat/completions",
            headers={**self._headers(), "Content-Type": "application/json"},
            json=payload,
        )
        _raise_with_body(resp, "/chat/completions")
        body = resp.json()
        content = body["choices"][0]["message"]["content"]
        data = json.loads(content)

        usage = body.get("usage", {})
        prompt_tokens = usage.get("prompt_tokens", 0)
        completion_tokens = usage.get("completion_tokens", 0)
        cost = (prompt_tokens * 0.00000030) + (completion_tokens * 0.00000250)

        return CaptionResult(
            caption=data.get("caption", ""),
            ocr_text=data.get("ocr_text", ""),
            tags=[t.lower() for t in data.get("tags", [])][:5],
            model=self.model_vision,
            cost_usd=round(cost, 6),
        )

    def summarise(self, text: str, context: dict | None = None) -> SummaryResult:
        system_prompt = (
            "You receive transcribed audio or extracted text. "
            "Produce a JSON object with keys: title (string, <=80 chars), "
            "summary (2-3 sentence string), tags (array of 2-5 lowercase string tags). "
            "Return ONLY the JSON, no prose."
        )
        ctx = context or {}
        user_prompt = (
            f"Source: {ctx.get('source', 'unknown')}\n"
            f"Platform: {ctx.get('platform', 'unknown')}\n\n"
            f"Content:\n{text[:8000]}"
        )

        payload = {
            "model": self.model_text,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "response_format": {"type": "json_object"},
        }
        resp = self._client.post(
            f"{_OR_BASE}/chat/completions",
            headers={**self._headers(), "Content-Type": "application/json"},
            json=payload,
        )
        _raise_with_body(resp, "/chat/completions")
        body = resp.json()
        content = body["choices"][0]["message"]["content"]
        data = json.loads(content)

        usage = body.get("usage", {})
        prompt_tokens = usage.get("prompt_tokens", 0)
        completion_tokens = usage.get("completion_tokens", 0)
        cost = (prompt_tokens * 0.00000010) + (completion_tokens * 0.00000040)

        return SummaryResult(
            title=data.get("title", "Untitled")[:80],
            summary=data.get("summary", ""),
            tags=[t.lower() for t in data.get("tags", [])][:5],
            model=self.model_text,
            cost_usd=round(cost, 6),
        )
