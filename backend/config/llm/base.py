"""Abstract LLM interface. Depend on `BaseLLM`, not a concrete provider."""

from abc import ABC, abstractmethod
from typing import TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


class BaseLLM(ABC):
    """Abstract base class for all LLM providers."""

    @abstractmethod
    def generate(self, prompt: str, system_prompt: str | None = None) -> str:
        """Generate free-form text for a prompt.

        Args:
            prompt: The user/task prompt.
            system_prompt: Optional system instruction.

        Returns:
            The raw text response from the model.
        """
        raise NotImplementedError

    @abstractmethod
    def generate_structured(
        self, prompt: str, schema: type[T], system_prompt: str | None = None
    ) -> T:
        """Generate a response validated against a Pydantic schema.

        Args:
            prompt: The user/task prompt.
            schema: Pydantic model class describing the expected output shape.
            system_prompt: Optional system instruction.

        Returns:
            An instance of `schema` populated from the model's response.
        """
        raise NotImplementedError
