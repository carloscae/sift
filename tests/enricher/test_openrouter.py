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
        model_stt="groq/whisper-large-v3-turbo",
        model_text="google/gemini-2.5-flash-lite",
        model_vision="google/gemini-2.5-flash",
    )


@respx.mock
def test_transcribe_posts_audio_and_parses(tmp_path: Path, enricher: OpenRouterEnricher):
    audio = tmp_path / "voice.mp3"
    audio.write_bytes(b"fake-mp3-bytes")

    route = respx.post("https://openrouter.ai/api/v1/audio/transcriptions").mock(
        return_value=httpx.Response(
            200,
            json={"text": "Hello there.", "usage": {"input_audio_seconds": 12}},
        )
    )

    result = enricher.transcribe(audio)

    assert route.called
    assert result.text == "Hello there."
    assert result.model == "groq/whisper-large-v3-turbo"
    assert result.cost_usd > 0


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
