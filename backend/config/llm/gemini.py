"""Gemini implementation of `BaseLLM`, via `google-genai`."""

from google import genai
from google.genai import types
from google.genai.errors import APIError

from config.llm.base import BaseLLM, LLMUnavailableError, T


class GeminiLLM(BaseLLM):
    """Gemini-backed LLM client."""

    def __init__(self, model_name: str, api_key: str) -> None:
        self.model_name = model_name
        self.api_key = api_key
        self.client = genai.Client(api_key=self.api_key)

    def generate(self, prompt: str, system_prompt: str | None = None) -> str:
        config = types.GenerateContentConfig(system_instruction=system_prompt)
        try:
            response = self.client.models.generate_content(
                model=self.model_name, contents=prompt, config=config
            )
        except APIError as e:
            raise LLMUnavailableError(str(e)) from e

        if response.text is None:
            raise ValueError("Gemini returned no text")
        return response.text

    def generate_structured(
        self, prompt: str, schema: type[T], system_prompt: str | None = None
    ) -> T:

        config = types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=schema,
            system_instruction=system_prompt,
        )
        try:
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=prompt,
                config=config,
            )
        except APIError as e:
            raise LLMUnavailableError(str(e)) from e

        if not isinstance(response.parsed, schema):
            raise TypeError(f"Gemini did not return a valid {schema.__name__}")
        return response.parsed
