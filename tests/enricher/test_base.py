from sift.enricher.base import (
    CaptionResult,
    Enricher,
    OCRResult,
    SummaryResult,
    TranscriptResult,
)


def test_result_types_carry_cost():
    t = TranscriptResult(text="hello world", model="groq/whisper", cost_usd=0.0007)
    assert t.cost_usd == 0.0007
    assert t.text == "hello world"


def test_result_types_exported():
    # Public surface of the enricher base module.
    assert CaptionResult.__name__ == "CaptionResult"
    assert OCRResult.__name__ == "OCRResult"
    assert SummaryResult.__name__ == "SummaryResult"


def test_enricher_is_abstract():
    import pytest
    with pytest.raises(TypeError):
        Enricher()
