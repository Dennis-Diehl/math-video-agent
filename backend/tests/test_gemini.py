from typing import Any
from unittest.mock import MagicMock

import pytest
from google.genai.errors import APIError
from pydantic import BaseModel

from config.llm.base import LLMUnavailableError
from config.llm.gemini import GeminiLLM


class DummySchema(BaseModel):
    value: str


def make_llm(response: Any = None, raises: Exception | None = None) -> GeminiLLM:
    """A GeminiLLM whose client.models.generate_content is mocked instead of
    making a real API call — no api key/network needed for this test."""
    llm = GeminiLLM("gemini-test", "fake-key")
    llm.client = MagicMock()
    if raises is not None:
        llm.client.models.generate_content.side_effect = raises
    else:
        llm.client.models.generate_content.return_value = response
    return llm


def test_generate_wraps_an_api_error_as_llm_unavailable():
    llm = make_llm(raises=APIError(429, {"error": {"message": "quota exceeded"}}))

    with pytest.raises(LLMUnavailableError):
        llm.generate("prompt")


def test_generate_structured_wraps_an_api_error_as_llm_unavailable():
    llm = make_llm(raises=APIError(429, {"error": {"message": "quota exceeded"}}))

    with pytest.raises(LLMUnavailableError):
        llm.generate_structured("prompt", schema=DummySchema)


def test_generate_still_raises_value_error_when_gemini_returns_no_text():
    llm = make_llm(response=MagicMock(text=None))

    with pytest.raises(ValueError):
        llm.generate("prompt")


def test_generate_structured_still_raises_type_error_on_a_bad_schema_match():
    llm = make_llm(response=MagicMock(parsed=None))

    with pytest.raises(TypeError):
        llm.generate_structured("prompt", schema=DummySchema)
