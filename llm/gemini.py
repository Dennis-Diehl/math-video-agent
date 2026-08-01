"""Gemini implementation of `BaseLLM`.

Uses `google-genai`. Which model is used is decided by the caller by
passing the appropriate model name at construction time — see config.py
for `gemini_model_flash` / `gemini_model_flash_lite`.
"""

from google import genai
from google.genai import types

from llm.base import BaseLLM, T


class GeminiLLM(BaseLLM):
    """Gemini-backed LLM client."""

    def __init__(self, model_name: str, api_key: str) -> None:
        """Initialize the Gemini client for a specific model.

        Args:
            model_name: Gemini model identifier, e.g. "gemini-3.5-flash".
            api_key: Gemini API key.
        """
        self.model_name = model_name
        self.api_key = api_key
        self.client = genai.Client(api_key=self.api_key)

    def generate(self, prompt: str, system_prompt: str | None = None) -> str:
        config = types.GenerateContentConfig(system_instruction=system_prompt)
        response = self.client.models.generate_content(
            model=self.model_name, contents=prompt, config=config
        )

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
        response = self.client.models.generate_content(
            model=self.model_name,
            contents=prompt,
            config=config,
        )

        if not isinstance(response.parsed, schema):
            raise TypeError(f"Gemini did not return a valid {schema.__name__}")
        return response.parsed
