"""
DRISHTI – Main orchestration script
=====================================
Coordinates all AI-layer components into a single processing loop that
runs continuously on the Raspberry Pi:

  1. Capture a frame from the ESP32-CAM MJPEG stream
  2. Run YOLO-Tiny object detection  →  speak obstacle warnings
  3. Check for text in the scene      →  read aloud via OCR
  4. On voice command                 →  describe the full scene with Gemini
  5. Publish location via GPS to the Flutter caregiver app (via MQTT or HTTP)

Run
---
    python main.py

Environment variables (see individual module docs for full lists)
-----------------------------------------------------------------
GEMINI_API_KEY      Google Generative AI API key
ESP32_STREAM_URL    MJPEG stream URL  (default http://192.168.1.100/stream)
WHISPER_MODEL       tiny | base | small | medium | large  (default tiny)
TTS_ENGINE          gtts | pyttsx3  (default gtts)
ALERT_DISTANCE_CM   Obstacle warning distance in cm  (default 80)
CAREGIVER_API_URL   REST endpoint for Flutter app location updates
"""

from __future__ import annotations

import logging
import os
import time
from typing import Optional

from audio_feedback import AudioFeedback
from object_detection import ObjectDetector
from ocr import TextReader
from scene_description import SceneDescriber
from speech_to_text import SpeechRecognizer

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Optionally import sensor hub (only works on real hardware)
# ---------------------------------------------------------------------------
try:
    import sys
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "hardware", "raspberry_pi"))
    from sensors import SensorHub  # type: ignore
    SENSORS_AVAILABLE = True
except ImportError:
    SENSORS_AVAILABLE = False
    logger.warning("SensorHub not available – sensor data skipped.")

try:
    import requests as _requests  # type: ignore
    HTTP_AVAILABLE = True
except ImportError:
    HTTP_AVAILABLE = False

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
ALERT_DISTANCE_CM = int(os.getenv("ALERT_DISTANCE_CM", "80"))
CAREGIVER_API_URL = os.getenv("CAREGIVER_API_URL", "")
LOOP_INTERVAL_S   = float(os.getenv("LOOP_INTERVAL_S", "1.0"))


# ---------------------------------------------------------------------------
# Helper: push location to caregiver app
# ---------------------------------------------------------------------------
def _push_location(latitude: Optional[float], longitude: Optional[float]) -> None:
    if not CAREGIVER_API_URL or not HTTP_AVAILABLE:
        return
    if latitude is None or longitude is None:
        return
    try:
        _requests.post(
            CAREGIVER_API_URL,
            json={"latitude": latitude, "longitude": longitude},
            timeout=3,
        )
    except Exception as exc:
        logger.debug("Location push failed: %s", exc)


# ---------------------------------------------------------------------------
# Helper: get one JPEG frame
# ---------------------------------------------------------------------------
def _get_frame(describer: SceneDescriber) -> Optional[bytes]:
    return describer.capture_frame_from_stream()


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------
def run() -> None:  # noqa: C901 – complexity is intentional for orchestration
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    logger.info("DRISHTI starting …")

    # Initialise all components
    audio    = AudioFeedback()
    detector = ObjectDetector()
    reader   = TextReader()
    describer = SceneDescriber()
    recognizer = SpeechRecognizer()

    detector.load()
    recognizer.load_model()

    sensors: Optional[object] = None
    if SENSORS_AVAILABLE:
        sensors = SensorHub()
        sensors.setup()  # type: ignore[union-attr]

    audio.speak("DRISHTI navigation system is ready.")

    try:
        while True:
            loop_start = time.time()

            # ----------------------------------------------------------
            # 1. Sensor readings
            # ----------------------------------------------------------
            sensor_data: dict = {}
            if sensors is not None:
                sensor_data = sensors.read_all()  # type: ignore[union-attr]
                gps = sensor_data.get("gps", {})
                _push_location(gps.get("latitude"), gps.get("longitude"))

                # Proximity warnings
                for us in sensor_data.get("ultrasonic", []):
                    dist = us.get("distance_cm", -1)
                    name = us.get("sensor", "obstacle")
                    if 0 < dist < ALERT_DISTANCE_CM:
                        audio.speak(f"Caution! {name} obstacle {int(dist)} centimetres away.")

            # ----------------------------------------------------------
            # 2. Capture frame
            # ----------------------------------------------------------
            jpeg = _get_frame(describer)
            if jpeg is None:
                logger.warning("No frame available – skipping vision pipeline.")
                time.sleep(LOOP_INTERVAL_S)
                continue

            # ----------------------------------------------------------
            # 3. Object detection
            # ----------------------------------------------------------
            detections = detector.detect_from_bytes(jpeg)
            if detections:
                summary = detector.summarise(detections)
                audio.speak(summary)
                logger.info("Detection: %s", summary)

            # ----------------------------------------------------------
            # 4. OCR – read visible text
            # ----------------------------------------------------------
            ocr_text = reader.extract_from_bytes(jpeg)
            if ocr_text:
                audio.speak(f"Text detected: {ocr_text}")
                logger.info("OCR: %s", ocr_text)

            # ----------------------------------------------------------
            # 5. Voice command – listen for a short burst
            # ----------------------------------------------------------
            spoken = recognizer.listen_and_transcribe(duration=2)
            if spoken:
                logger.info("Voice command: %s", spoken)
                if any(kw in spoken.lower() for kw in ("describe", "what", "where", "scene")):
                    scene = describer.describe(jpeg_bytes=jpeg)
                    audio.speak(scene)
                elif any(kw in spoken.lower() for kw in ("stop", "exit", "quit")):
                    audio.speak("Shutting down DRISHTI. Goodbye.")
                    break

            # ----------------------------------------------------------
            # Maintain loop cadence
            # ----------------------------------------------------------
            elapsed = time.time() - loop_start
            sleep_time = max(0.0, LOOP_INTERVAL_S - elapsed)
            time.sleep(sleep_time)

    except KeyboardInterrupt:
        logger.info("Interrupted by user.")
    finally:
        if sensors is not None:
            sensors.cleanup()  # type: ignore[union-attr]
        logger.info("DRISHTI stopped.")


if __name__ == "__main__":
    run()
