"""Kokoro implementation of `BaseTTS`.

Kokoro runs locally: model weights are fetched from Hugging Face once, and
synthesis after that costs nothing and needs no API key. Voice and language
come from the caller — see `kokoro_voice` / `kokoro_lang_code` in
`config/config.py`.
"""

from pathlib import Path

import soundfile as sf
from kokoro import KPipeline

from config.tts.base import BaseTTS

# Kokoro always produces audio at this rate; it is not configurable.
SAMPLE_RATE = 24000


class KokoroTTS(BaseTTS):
    """Speech synthesis with a local Kokoro model."""

    def __init__(self, voice: str, lang_code: str):
        """Prepare the engine.

        Args:
            voice: A Kokoro voice name, e.g. `af_heart`.
            lang_code: Kokoro's language code, e.g. `a` for American English.
        """
        self.voice = voice
        # Reused across calls: building a pipeline costs seconds, and downloads
        # a model on first use.
        self._pipeline = KPipeline(lang_code=lang_code)

    def synthesize(self, text: str, destination: Path) -> float:
        """Speak `text` and write the audio to `destination`.

        Args:
            text: The words to speak.
            destination: Where to write the audio file.

        Returns:
            How long the narration lasts, in seconds.

        Raises:
            RuntimeError: If Kokoro returns no audio for the text.
        """
        # Kokoro splits long text and yields one result per chunk.
        chunks = [result.audio for result in self._pipeline(text, voice=self.voice)]
        if not chunks:
            raise RuntimeError(f"Kokoro produced no audio for: {text!r}")

        destination.parent.mkdir(parents=True, exist_ok=True)
        samples = 0
        with sf.SoundFile(
            destination, mode="w", samplerate=SAMPLE_RATE, channels=1, format="WAV"
        ) as audio_file:
            for chunk in chunks:
                audio_file.write(chunk)
                samples += len(chunk)

        return samples / SAMPLE_RATE
