import json
from pathlib import Path

import httpx
import pytest
import respx

from sift.enricher.openrouter import OpenRouterEnricher


@pytest.fixture
def enricher() -> OpenRouterEnricher:
    return OpenRouterEnricher(
        api_key="sk-or-test",
        model_text="google/gemini-2.5-flash-lite",
        model_vision="google/gemini-2.5-flash",
        whisper_svc_url="http://localhost:8742",
    )


@respx.mock
def test_transcribe_calls_whisper_svc(tmp_path: Path, enricher: OpenRouterEnricher):
    audio = tmp_path / "voice.mp3"
    audio.write_bytes(b"fake-mp3-bytes")

    route = respx.post("http://localhost:8742/transcribe").mock(
        return_value=httpx.Response(
            200,
            json={"transcript": "Hello there.", "language": "en", "model": "mlx-community/whisper-large-v3-turbo"},
        )
    )

    result = enricher.transcribe(audio)

    assert route.called
    assert result.text == "Hello there."
    assert result.model == "mlx-community/whisper-large-v3-turbo"
    assert result.cost_usd == 0.0


@respx.mock
def test_summarise_returns_title_summary_tags(enricher: OpenRouterEnricher):
    route = respx.post("https://openrouter.ai/api/v1/chat/completions").mock(
        return_value=httpx.Response(
            200,
            json={
                "choices": [{
                    "message": {
                        "content": json.dumps({
                            "title": "How to ship fast",
                            "summary": "Ship small. Ship often.",
                            "tags": ["productivity", "shipping"],
                        }),
                    },
                }],
                "usage": {"prompt_tokens": 200, "completion_tokens": 40},
            },
        )
    )

    result = enricher.summarise("Long transcript text...")

    assert route.called
    assert result.title == "How to ship fast"
    assert result.summary == "Ship small. Ship often."
    assert "productivity" in result.tags
    assert result.cost_usd >= 0


@respx.mock
def test_caption_sends_image_as_base64(tmp_path: Path, enricher: OpenRouterEnricher):
    img = tmp_path / "shot.png"
    img.write_bytes(b"\x89PNG\r\n\x1a\n" + b"fake-png")

    route = respx.post("https://openrouter.ai/api/v1/chat/completions").mock(
        return_value=httpx.Response(
            200,
            json={
                "choices": [{
                    "message": {
                        "content": json.dumps({
                            "caption": "A screenshot of a tweet.",
                            "ocr_text": "Hello world",
                            "tags": ["screenshot", "twitter"],
                        }),
                    },
                }],
                "usage": {"prompt_tokens": 500, "completion_tokens": 30},
            },
        )
    )

    result = enricher.caption(img)

    assert route.called
    assert result.caption == "A screenshot of a tweet."
    assert result.ocr_text == "Hello world"
    req = route.calls.last.request
    body = json.loads(req.content)
    # Confirm at least one user-message part has image_url
    has_image = any(
        "image_url" in (p if isinstance(p, dict) else {})
        for msg in body["messages"]
        for p in (msg["content"] if isinstance(msg["content"], list) else [])
    )
    assert has_image
