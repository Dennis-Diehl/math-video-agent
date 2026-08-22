"""Abstract TTS interface.

Code that needs speech synthesis depends on `BaseTTS`, not on a concrete
engine, which keeps the engine swappable and lets pipeline nodes be tested
against a fake instead of running real synthesis.
"""

from abc import ABC, abstractmethod
from pathlib import Path


class BaseTTS(ABC):
    """Abstract base class for all text-to-speech engines."""

    @abstractmethod
    def synthesize(self, text: str, destination: Path) -> float:
        """Speak `text` and write the audio to `destination`.

        The duration is returned rather than measured later because the
        engine already knows it, and `codegen_node` needs it to time each
        scene to its narration.

        Args:
            text: The words to speak.
            destination: Where to write the audio file. Missing parent
                directories are created.

        Returns:
            The narration's length in seconds.
        """
        raise NotImplementedError
