"""Kokoro implementation of `BaseTTS`. Runs locally, no API key needed."""

from pathlib import Path

import soundfile as sf
from kokoro import KPipeline

from config.tts.base import BaseTTS

# Kokoro always produces audio at this rate; it is not configurable.
SAMPLE_RATE = 24000


class KokoroTTS(BaseTTS):
    """Speech synthesis with a local Kokoro model."""

    def __init__(self, voice: str, lang_code: str):
        self.voice = voice
        self._pipeline = KPipeline(lang_code=lang_code)  # built once, reused across calls

    def synthesize(self, text: str, destination: Path) -> float:
        """Speak `text` to `destination`, return its duration in seconds."""
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
