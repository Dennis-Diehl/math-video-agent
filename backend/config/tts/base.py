"""Abstract TTS interface. Depend on `BaseTTS`, not a concrete engine."""

from abc import ABC, abstractmethod
from pathlib import Path


class BaseTTS(ABC):
    """Abstract base class for all text-to-speech engines."""

    @abstractmethod
    def synthesize(self, text: str, destination: Path) -> float:
        """Speak `text` to `destination`, return its duration in seconds."""
        raise NotImplementedError
