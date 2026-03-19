"""
DRISHTI – Scene description using Google Gemini Vision API
===========================================================
Fetches a JPEG frame from the ESP32-CAM MJPEG stream (or a static image
file), sends it to the Gemini 1.5 Flash model and returns a concise
natural-language scene description suitable for audio feedback.

Environment variables
---------------------
GEMINI_API_KEY   Your Google Generative AI API key
ESP32_STREAM_URL MJPEG stream URL (default http://192.168.1.100/stream)
"""

from __future__ import annotations

import io
import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

try:
    import google.generativeai as genai  # type: ignore
    GENAI_AVAILABLE = True
except ImportError:
    GENAI_AVAILABLE = False
    logger.warning("google-generativeai not installed – scene description disabled.")

try:
    import requests  # type: ignore
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False

try:
    from PIL import Image  # type: ignore
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False


# ---------------------------------------------------------------------------
# Gemini Vision client
# ---------------------------------------------------------------------------
class SceneDescriber:
    """Describes a scene captured from the ESP32-CAM using Gemini Vision."""

    DEFAULT_PROMPT = (
        "You are an AI assistant helping a visually impaired person navigate safely. "
        "Describe the scene in the image clearly and concisely in 2-3 sentences. "
        "Highlight obstacles, people, text, and notable landmarks."
    )

    def __init__(
        self,
        api_key: Optional[str] = None,
        model_name: str = "gemini-1.5-flash",
        stream_url: Optional[str] = None,
        prompt: Optional[str] = None,
    ) -> None:
        self.api_key = api_key or os.getenv("GEMINI_API_KEY", "")
        self.model_name = model_name
        self.stream_url = stream_url or os.getenv(
            "ESP32_STREAM_URL", "http://192.168.1.100/stream"
        )
        self.prompt = prompt or self.DEFAULT_PROMPT
        self._model = None

        if GENAI_AVAILABLE and self.api_key:
            genai.configure(api_key=self.api_key)
            self._model = genai.GenerativeModel(self.model_name)
            logger.info("Gemini model '%s' ready.", self.model_name)
        else:
            logger.warning(
                "Gemini model not initialised (missing API key or library)."
            )

    # ------------------------------------------------------------------
    # Frame acquisition
    # ------------------------------------------------------------------
    def capture_frame_from_stream(self) -> Optional[bytes]:
        """
        Read one JPEG frame from the ESP32-CAM MJPEG stream.
        Returns raw JPEG bytes or None on failure.
        """
        if not REQUESTS_AVAILABLE:
            logger.error("requests library not available.")
            return None
        try:
            with requests.get(self.stream_url, stream=True, timeout=5) as resp:
                resp.raise_for_status()
                buf = b""
                for chunk in resp.iter_content(chunk_size=1024):
                    buf += chunk
                    start = buf.find(b"\xff\xd8")  # JPEG SOI marker
                    end   = buf.find(b"\xff\xd9")  # JPEG EOI marker
                    if start != -1 and end != -1 and end > start:
                        return buf[start: end + 2]
        except Exception as exc:
            logger.exception("Frame capture error: %s", exc)
        return None

    def load_frame_from_file(self, path: str) -> Optional[bytes]:
        """Load a JPEG image from disk for offline testing."""
        try:
            with open(path, "rb") as fh:
                return fh.read()
        except OSError as exc:
            logger.error("Cannot open image file: %s", exc)
            return None

    # ------------------------------------------------------------------
    # Scene description
    # ------------------------------------------------------------------
    def describe(self, jpeg_bytes: Optional[bytes] = None,
                 image_path: Optional[str] = None) -> str:
        """
        Send an image to Gemini and return a scene description.

        Pass either raw JPEG bytes or a file path.  If neither is given,
        the method captures a fresh frame from the MJPEG stream.
        """
        if not GENAI_AVAILABLE or self._model is None:
            return "Scene description unavailable (Gemini not configured)."

        # Resolve image source
        if jpeg_bytes is None:
            if image_path:
                jpeg_bytes = self.load_frame_from_file(image_path)
            else:
                jpeg_bytes = self.capture_frame_from_stream()

        if jpeg_bytes is None:
            return "Could not acquire an image for scene description."

        try:
            if PIL_AVAILABLE:
                image = Image.open(io.BytesIO(jpeg_bytes))
            else:
                # Gemini SDK also accepts raw bytes with a mime type
                image = {"mime_type": "image/jpeg", "data": jpeg_bytes}

            response = self._model.generate_content([self.prompt, image])
            return response.text.strip()
        except Exception as exc:
            logger.exception("Gemini API error: %s", exc)
            return f"Scene description failed: {exc}"


# ---------------------------------------------------------------------------
# Quick test
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    describer = SceneDescriber()
    # Replace with an actual image path for offline testing:
    description = describer.describe(image_path="/tmp/test_frame.jpg")
    print("Scene:", description)
