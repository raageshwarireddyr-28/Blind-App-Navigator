"""
DRISHTI – Speech-to-text using OpenAI Whisper
==============================================
Captures audio from the default microphone (or a WAV file),
transcribes it with the local OpenAI Whisper model, and returns
the recognised text so that other modules can act on voice commands.

Environment variables
---------------------
WHISPER_MODEL   Whisper model size: tiny | base | small | medium | large
                Default: tiny  (fastest, suitable for Raspberry Pi)
"""

from __future__ import annotations

import io
import logging
import os
import tempfile
from typing import Optional

logger = logging.getLogger(__name__)

try:
    import whisper  # type: ignore  (openai-whisper package)
    WHISPER_AVAILABLE = True
except ImportError:
    WHISPER_AVAILABLE = False
    logger.warning("openai-whisper not installed – speech-to-text disabled.")

try:
    import sounddevice as sd  # type: ignore
    import numpy as np        # type: ignore
    import scipy.io.wavfile as wav  # type: ignore
    AUDIO_AVAILABLE = True
except ImportError:
    AUDIO_AVAILABLE = False
    logger.warning("sounddevice / numpy / scipy not installed – microphone recording disabled.")


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
SAMPLE_RATE = 16000  # Hz – Whisper expects 16 kHz
DEFAULT_DURATION = 5  # seconds to record per utterance


# ---------------------------------------------------------------------------
# Speech recogniser
# ---------------------------------------------------------------------------
class SpeechRecognizer:
    """Records audio from the microphone and transcribes it with Whisper."""

    def __init__(
        self,
        model_size: Optional[str] = None,
        language: str = "en",
        device: str = "cpu",
    ) -> None:
        self.model_size = model_size or os.getenv("WHISPER_MODEL", "tiny")
        self.language = language
        self.device = device
        self._model = None

    def load_model(self) -> None:
        """Load the Whisper model into memory (call once at startup)."""
        if not WHISPER_AVAILABLE:
            logger.error("Whisper library not available.")
            return
        logger.info("Loading Whisper model '%s' …", self.model_size)
        self._model = whisper.load_model(self.model_size, device=self.device)
        logger.info("Whisper model ready.")

    # ------------------------------------------------------------------
    # Audio capture
    # ------------------------------------------------------------------
    def record(self, duration: int = DEFAULT_DURATION) -> Optional[bytes]:
        """
        Record *duration* seconds from the default microphone.
        Returns PCM data as a WAV-formatted bytes object, or None on failure.
        """
        if not AUDIO_AVAILABLE:
            logger.error("Audio libraries not available – cannot record.")
            return None
        try:
            logger.info("Recording for %d seconds …", duration)
            audio_data = sd.rec(
                int(duration * SAMPLE_RATE),
                samplerate=SAMPLE_RATE,
                channels=1,
                dtype="int16",
            )
            sd.wait()
            # Convert to WAV bytes
            buf = io.BytesIO()
            wav.write(buf, SAMPLE_RATE, audio_data)
            return buf.getvalue()
        except Exception as exc:
            logger.exception("Recording error: %s", exc)
            return None

    # ------------------------------------------------------------------
    # Transcription
    # ------------------------------------------------------------------
    def transcribe_bytes(self, wav_bytes: bytes) -> str:
        """Transcribe a WAV byte buffer and return the recognised text."""
        if not WHISPER_AVAILABLE or self._model is None:
            return ""
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            tmp.write(wav_bytes)
            tmp_path = tmp.name
        try:
            result = self._model.transcribe(tmp_path, language=self.language)
            return result["text"].strip()
        except Exception as exc:
            logger.exception("Transcription error: %s", exc)
            return ""
        finally:
            os.unlink(tmp_path)

    def transcribe_file(self, wav_path: str) -> str:
        """Transcribe a WAV file on disk and return the recognised text."""
        if not WHISPER_AVAILABLE or self._model is None:
            return ""
        try:
            result = self._model.transcribe(wav_path, language=self.language)
            return result["text"].strip()
        except Exception as exc:
            logger.exception("Transcription file error: %s", exc)
            return ""

    def listen_and_transcribe(self, duration: int = DEFAULT_DURATION) -> str:
        """Record from the microphone, then transcribe immediately."""
        wav_bytes = self.record(duration)
        if wav_bytes is None:
            return ""
        return self.transcribe_bytes(wav_bytes)


# ---------------------------------------------------------------------------
# Quick test
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    recognizer = SpeechRecognizer()
    recognizer.load_model()
    print("Say something …")
    text = recognizer.listen_and_transcribe(duration=5)
    print("You said:", text)
