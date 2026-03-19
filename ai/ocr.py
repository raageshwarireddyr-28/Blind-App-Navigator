"""
DRISHTI – OCR text reading using Tesseract
==========================================
Extracts text from an image (e.g. signboards, notices, product labels)
using pytesseract and optionally preprocesses the image with OpenCV for
better accuracy.

Environment variables
---------------------
TESSERACT_CMD    Path to the tesseract binary (default: tesseract)
OCR_LANG         Tesseract language code (default: eng)
"""

from __future__ import annotations

import logging
import os
from typing import Optional

import numpy as np  # type: ignore

logger = logging.getLogger(__name__)

try:
    import pytesseract  # type: ignore
    from pytesseract import Output  # type: ignore
    TESSERACT_AVAILABLE = True
    _cmd = os.getenv("TESSERACT_CMD", "tesseract")
    pytesseract.pytesseract.tesseract_cmd = _cmd
except ImportError:
    TESSERACT_AVAILABLE = False
    logger.warning("pytesseract not installed – OCR disabled.")

try:
    import cv2  # type: ignore
    CV2_AVAILABLE = True
except ImportError:
    CV2_AVAILABLE = False

try:
    from PIL import Image  # type: ignore
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False


# ---------------------------------------------------------------------------
# OCR engine
# ---------------------------------------------------------------------------
class TextReader:
    """Reads text from images using Tesseract OCR."""

    def __init__(
        self,
        language: Optional[str] = None,
        preprocess: bool = True,
    ) -> None:
        self.language = language or os.getenv("OCR_LANG", "eng")
        self.preprocess = preprocess

    # ------------------------------------------------------------------
    # Image preprocessing
    # ------------------------------------------------------------------
    def _preprocess_image(self, image: np.ndarray) -> np.ndarray:
        """
        Apply grayscale conversion, denoising, and adaptive thresholding
        to improve Tesseract accuracy on low-contrast images.
        """
        if not CV2_AVAILABLE:
            return image
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        denoised = cv2.fastNlMeansDenoising(gray, h=10)
        # Adaptive threshold works well for uneven lighting
        binary = cv2.adaptiveThreshold(
            denoised, 255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY, 11, 2,
        )
        return binary

    # ------------------------------------------------------------------
    # Core extraction
    # ------------------------------------------------------------------
    def extract_from_array(self, image: np.ndarray) -> str:
        """
        Extract text from a numpy image array (BGR or grayscale).

        Returns the recognised text, stripped of leading/trailing whitespace.
        """
        if not TESSERACT_AVAILABLE:
            return ""
        try:
            proc = self._preprocess_image(image) if self.preprocess else image
            if PIL_AVAILABLE:
                pil_img = Image.fromarray(proc)
            else:
                pil_img = proc  # pytesseract can also accept numpy arrays
            text = pytesseract.image_to_string(pil_img, lang=self.language)
            return text.strip()
        except Exception as exc:
            logger.exception("OCR error: %s", exc)
            return ""

    def extract_from_bytes(self, jpeg_bytes: bytes) -> str:
        """Decode a JPEG byte buffer and extract text."""
        if not CV2_AVAILABLE:
            logger.error("OpenCV required for JPEG decoding.")
            return ""
        img_array = np.frombuffer(jpeg_bytes, dtype=np.uint8)
        image = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
        if image is None:
            logger.error("Failed to decode JPEG bytes.")
            return ""
        return self.extract_from_array(image)

    def extract_from_file(self, image_path: str) -> str:
        """Extract text from an image file."""
        if not TESSERACT_AVAILABLE:
            return ""
        try:
            if PIL_AVAILABLE:
                image = Image.open(image_path)
                if self.preprocess and CV2_AVAILABLE:
                    arr = np.array(image)
                    proc = self._preprocess_image(arr)
                    image = Image.fromarray(proc)
                return pytesseract.image_to_string(image, lang=self.language).strip()
            elif CV2_AVAILABLE:
                img = cv2.imread(image_path)
                return self.extract_from_array(img)
            else:
                return pytesseract.image_to_string(image_path, lang=self.language).strip()
        except Exception as exc:
            logger.exception("OCR file error: %s", exc)
            return ""

    def has_text(self, image: np.ndarray, min_confidence: int = 60) -> bool:
        """
        Return True if any text with confidence ≥ min_confidence is found
        in the image – useful for deciding whether to trigger a full read.
        """
        if not TESSERACT_AVAILABLE:
            return False
        try:
            proc = self._preprocess_image(image) if self.preprocess else image
            data = pytesseract.image_to_data(
                proc, lang=self.language, output_type=Output.DICT
            )
            for conf in data["conf"]:
                if isinstance(conf, (int, float)) and int(conf) >= min_confidence:
                    return True
        except Exception as exc:
            logger.debug("has_text error: %s", exc)
        return False

    def speak_text(self, text: str, audio_feedback) -> None:  # noqa: ANN001
        """Pass extracted text to an AudioFeedback instance to be read aloud."""
        if text:
            audio_feedback.speak(f"Text detected: {text}")
        else:
            audio_feedback.speak("No readable text found.")


# ---------------------------------------------------------------------------
# Quick test
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    reader = TextReader()
    result = reader.extract_from_file("/tmp/test_sign.jpg")
    print("OCR result:", result if result else "(no text found)")
