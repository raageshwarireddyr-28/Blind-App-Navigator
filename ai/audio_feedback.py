"""
DRISHTI – Audio feedback using Google Text-to-Speech (gTTS)
===========================================================
Converts text to speech and plays it through the default audio output.
Supports both online TTS (gTTS) and a fallback using pyttsx3 for
offline use when the device has no internet connection.

Environment variables
---------------------
TTS_ENGINE   "gtts" (default) | "pyttsx3"
TTS_LANG     BCP-47 language code for gTTS, e.g. "en"  (default: "en")
"""

from __future__ import annotations

import io
import logging
import os
import tempfile
from typing import Optional

logger = logging.getLogger(__name__)

try:
    from gtts import gTTS  # type: ignore
    GTTS_AVAILABLE = True
except ImportError:
    GTTS_AVAILABLE = False
    logger.warning("gTTS not installed – falling back to pyttsx3 if available.")

try:
    import pyttsx3  # type: ignore
    PYTTSX3_AVAILABLE = True
except ImportError:
    PYTTSX3_AVAILABLE = False

try:
    import pygame  # type: ignore
    PYGAME_AVAILABLE = True
except ImportError:
    PYGAME_AVAILABLE = False

try:
    from playsound import playsound  # type: ignore
    PLAYSOUND_AVAILABLE = True
except ImportError:
    PLAYSOUND_AVAILABLE = False


# ---------------------------------------------------------------------------
# Audio feedback engine
# ---------------------------------------------------------------------------
class AudioFeedback:
    """Converts text to speech and plays it on the device speakers."""

    def __init__(
        self,
        engine: Optional[str] = None,
        language: str = "en",
    ) -> None:
        self.language = language
        self.engine = engine or os.getenv("TTS_ENGINE", "gtts")
        self._pyttsx3_engine = None

        if self.engine == "pyttsx3" and PYTTSX3_AVAILABLE:
            self._pyttsx3_engine = pyttsx3.init()
            self._pyttsx3_engine.setProperty("rate", 150)
            logger.info("pyttsx3 TTS engine ready.")
        elif self.engine == "gtts" and GTTS_AVAILABLE:
            if PYGAME_AVAILABLE:
                pygame.mixer.init()
            logger.info("gTTS engine ready (language=%s).", self.language)
        else:
            logger.warning("No TTS engine available – audio feedback disabled.")

    def speak(self, text: str) -> None:
        """Convert *text* to speech and play it immediately."""
        if not text:
            return
        logger.info("Speaking: %s", text)
        if self.engine == "pyttsx3" and self._pyttsx3_engine:
            self._speak_pyttsx3(text)
        elif self.engine == "gtts" and GTTS_AVAILABLE:
            self._speak_gtts(text)
        else:
            print(f"[TTS] {text}")  # fallback: print to console

    def _speak_gtts(self, text: str) -> None:
        """Synthesise with gTTS and play the resulting MP3."""
        tmp_path: Optional[str] = None
        try:
            tts = gTTS(text=text, lang=self.language, slow=False)
            with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
                tts.save(tmp.name)
                tmp_path = tmp.name
            self._play_audio(tmp_path)
        except Exception as exc:
            logger.exception("gTTS error: %s", exc)
        finally:
            if tmp_path is not None:
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass

    def _speak_pyttsx3(self, text: str) -> None:
        """Synthesise and play with pyttsx3 (offline, synchronous)."""
        try:
            self._pyttsx3_engine.say(text)
            self._pyttsx3_engine.runAndWait()
        except Exception as exc:
            logger.exception("pyttsx3 error: %s", exc)

    def _play_audio(self, file_path: str) -> None:
        """Play an audio file using pygame or playsound."""
        if PYGAME_AVAILABLE:
            try:
                pygame.mixer.music.load(file_path)
                pygame.mixer.music.play()
                while pygame.mixer.music.get_busy():
                    pygame.time.Clock().tick(10)
                return
            except Exception as exc:
                logger.warning("pygame playback error: %s", exc)
        if PLAYSOUND_AVAILABLE:
            try:
                playsound(file_path)
                return
            except Exception as exc:
                logger.warning("playsound error: %s", exc)
        # Last resort – use system command
        os.system(f"mpg123 -q {file_path} 2>/dev/null || aplay {file_path} 2>/dev/null")

    def save_to_file(self, text: str, output_path: str) -> bool:
        """Save TTS audio to an MP3 file without playing it."""
        if not GTTS_AVAILABLE:
            logger.error("gTTS not available – cannot save audio file.")
            return False
        try:
            tts = gTTS(text=text, lang=self.language, slow=False)
            tts.save(output_path)
            logger.info("Audio saved to %s", output_path)
            return True
        except Exception as exc:
            logger.exception("save_to_file error: %s", exc)
            return False


# ---------------------------------------------------------------------------
# Quick test
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    feedback = AudioFeedback()
    feedback.speak("Hello! DRISHTI navigation system is ready.")
