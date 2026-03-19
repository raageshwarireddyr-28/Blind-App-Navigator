"""
DRISHTI – Real-time object detection using YOLO-Tiny on TFLite
==============================================================
Runs YOLOv5-Tiny (or any compatible single-shot detector) exported to
TFLite on the Raspberry Pi, providing fast on-device obstacle detection
without an internet connection.

Model & label file setup
-------------------------
1. Export YOLOv5n to TFLite:
       python export.py --weights yolov5n.pt --include tflite --img 320
2. Copy yolov5n_float32.tflite → models/yolo_tiny.tflite
3. Copy coco.names               → models/coco.names

Environment variables
---------------------
TFLITE_MODEL_PATH   Path to the .tflite model file
TFLITE_LABELS_PATH  Path to the class-names text file
CONFIDENCE_THRESH   Minimum detection confidence (default 0.5)
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

import numpy as np  # type: ignore

logger = logging.getLogger(__name__)

try:
    from tflite_runtime.interpreter import Interpreter  # type: ignore
    TFLITE_AVAILABLE = True
except ImportError:
    try:
        import tensorflow as tf  # type: ignore  # fallback to full TF
        Interpreter = tf.lite.Interpreter
        TFLITE_AVAILABLE = True
    except ImportError:
        TFLITE_AVAILABLE = False
        logger.warning("TFLite runtime not available – object detection disabled.")

try:
    import cv2  # type: ignore
    CV2_AVAILABLE = True
except ImportError:
    CV2_AVAILABLE = False
    logger.warning("OpenCV not available – image decoding limited.")


# ---------------------------------------------------------------------------
# Data class for detections
# ---------------------------------------------------------------------------
@dataclass
class Detection:
    label: str
    confidence: float
    x1: int
    y1: int
    x2: int
    y2: int

    def __str__(self) -> str:
        return (
            f"{self.label} ({self.confidence:.0%}) "
            f"@ [{self.x1},{self.y1},{self.x2},{self.y2}]"
        )


# ---------------------------------------------------------------------------
# Object detector
# ---------------------------------------------------------------------------
class ObjectDetector:
    """YOLO-Tiny TFLite object detector."""

    # Default paths (relative to the ai/ directory)
    _DEFAULT_MODEL  = os.path.join(os.path.dirname(__file__), "models", "yolo_tiny.tflite")
    _DEFAULT_LABELS = os.path.join(os.path.dirname(__file__), "models", "coco.names")

    def __init__(
        self,
        model_path: Optional[str] = None,
        labels_path: Optional[str] = None,
        confidence_threshold: float = 0.5,
        input_size: int = 320,
    ) -> None:
        self.model_path = model_path or os.getenv("TFLITE_MODEL_PATH", self._DEFAULT_MODEL)
        self.labels_path = labels_path or os.getenv("TFLITE_LABELS_PATH", self._DEFAULT_LABELS)
        self.confidence_threshold = float(
            os.getenv("CONFIDENCE_THRESH", str(confidence_threshold))
        )
        self.input_size = input_size
        self._interpreter = None
        self._labels: List[str] = []

    def load(self) -> bool:
        """Load the TFLite model and class labels."""
        if not TFLITE_AVAILABLE:
            logger.error("TFLite runtime not available.")
            return False

        if not Path(self.model_path).exists():
            logger.error("Model file not found: %s", self.model_path)
            return False

        try:
            self._interpreter = Interpreter(model_path=self.model_path)
            self._interpreter.allocate_tensors()
            logger.info("TFLite model loaded: %s", self.model_path)
        except Exception as exc:
            logger.exception("Failed to load TFLite model: %s", exc)
            return False

        # Load labels
        if Path(self.labels_path).exists():
            with open(self.labels_path, "r") as fh:
                self._labels = [line.strip() for line in fh if line.strip()]
        else:
            logger.warning("Labels file not found: %s", self.labels_path)
        return True

    # ------------------------------------------------------------------
    # Pre-processing
    # ------------------------------------------------------------------
    def _preprocess(self, image: np.ndarray) -> np.ndarray:
        """Resize and normalise the image for YOLO-Tiny input."""
        if CV2_AVAILABLE:
            resized = cv2.resize(image, (self.input_size, self.input_size))
        else:
            # Fallback: nearest-neighbour resize using slicing
            h, w = image.shape[:2]
            resized = image[
                ::max(1, h // self.input_size),
                ::max(1, w // self.input_size),
            ][: self.input_size, : self.input_size]

        img_float = resized.astype(np.float32) / 255.0
        return np.expand_dims(img_float, axis=0)

    # ------------------------------------------------------------------
    # Inference
    # ------------------------------------------------------------------
    def detect(self, image: np.ndarray) -> List[Detection]:
        """
        Run inference on a BGR or RGB numpy image array.

        Returns a list of Detection objects sorted by confidence.
        """
        if self._interpreter is None:
            logger.error("Model not loaded – call load() first.")
            return []

        input_details  = self._interpreter.get_input_details()
        output_details = self._interpreter.get_output_details()

        input_data = self._preprocess(image)
        self._interpreter.set_tensor(input_details[0]["index"], input_data)
        self._interpreter.invoke()

        # Output tensor layout: [1, num_detections, 6]
        # Each row: [x1, y1, x2, y2, confidence, class_id]
        raw = self._interpreter.get_tensor(output_details[0]["index"])[0]

        h, w = image.shape[:2]
        detections: List[Detection] = []

        for row in raw:
            confidence = float(row[4])
            if confidence < self.confidence_threshold:
                continue
            class_id = int(row[5])
            label = self._labels[class_id] if class_id < len(self._labels) else str(class_id)
            x1 = int(row[0] * w)
            y1 = int(row[1] * h)
            x2 = int(row[2] * w)
            y2 = int(row[3] * h)
            detections.append(Detection(label, confidence, x1, y1, x2, y2))

        return sorted(detections, key=lambda d: d.confidence, reverse=True)

    def detect_from_bytes(self, jpeg_bytes: bytes) -> List[Detection]:
        """Decode a JPEG byte buffer and run detection."""
        if not CV2_AVAILABLE:
            logger.error("OpenCV required for JPEG decoding.")
            return []
        img_array = np.frombuffer(jpeg_bytes, dtype=np.uint8)
        image = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
        if image is None:
            logger.error("Failed to decode JPEG bytes.")
            return []
        return self.detect(image)

    def summarise(self, detections: List[Detection]) -> str:
        """Return a concise human-readable summary of detected objects."""
        if not detections:
            return "No obstacles detected."
        labels = [d.label for d in detections[:5]]  # top-5 only
        unique_counts: dict = {}
        for lbl in labels:
            unique_counts[lbl] = unique_counts.get(lbl, 0) + 1
        parts = [
            f"{count} {lbl}" if count > 1 else lbl
            for lbl, count in unique_counts.items()
        ]
        return "Detected: " + ", ".join(parts) + "."


# ---------------------------------------------------------------------------
# Quick test
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    detector = ObjectDetector()
    if detector.load():
        # Replace with a real image path for testing
        if CV2_AVAILABLE:
            test_img = cv2.imread("/tmp/test_frame.jpg")
            if test_img is not None:
                results = detector.detect(test_img)
                print(detector.summarise(results))
            else:
                print("Test image not found.")
        else:
            print("OpenCV not available for test.")
    else:
        print("Model not loaded – place yolo_tiny.tflite in ai/models/")
