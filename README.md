# DRISHTI – AI-Powered Smart Navigation Assistant for the Visually Impaired

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Platform: Raspberry Pi](https://img.shields.io/badge/Hardware-Raspberry%20Pi%204-red)](https://www.raspberrypi.com/)
[![Flutter](https://img.shields.io/badge/Mobile-Flutter%203-blue)](https://flutter.dev/)
[![Python](https://img.shields.io/badge/AI-Python%203.10%2B-yellow)](https://python.org)

**DRISHTI** (दृष्टि – Sanskrit for *vision*) is an open-source, AI-powered wearable navigation system that gives visually impaired users real-time audio feedback about their surroundings. It combines a smart pair of ESP32-CAM glasses, a Raspberry Pi 4 smart cane, and a Flutter caregiver app.

---

## ✨ Features

| Feature | Technology |
|---------|-----------|
| Scene description | Google Gemini 1.5 Flash Vision API |
| Voice commands | OpenAI Whisper (on-device) |
| Audio feedback | Google Text-to-Speech (gTTS) |
| Edge object detection | YOLO-Tiny on TFLite |
| Sign / text reading | Tesseract OCR |
| Obstacle proximity alerts | HC-SR04 Ultrasonic sensors |
| Navigation & orientation | NEO-8M GPS + MPU-6050 IMU |
| Emergency SOS | GSM (SIM800L) + Flutter push notification |
| Caregiver live tracking | Flutter app with OpenStreetMap |

---

## 🗂 Project Structure

```
Blind-App-Navigator/
├── hardware/
│   ├── esp32_cam/
│   │   └── esp32_cam_stream.ino     # Arduino sketch – MJPEG stream over Wi-Fi
│   └── raspberry_pi/
│       ├── sensors.py               # Ultrasonic + GPS + IMU driver
│       └── gsm.py                   # GSM AT-command helper (SMS / calls)
│
├── ai/
│   ├── main.py                      # Main orchestration loop
│   ├── scene_description.py         # Gemini Vision scene description
│   ├── speech_to_text.py            # OpenAI Whisper speech recogniser
│   ├── audio_feedback.py            # gTTS / pyttsx3 audio output
│   ├── object_detection.py          # YOLO-Tiny TFLite object detector
│   ├── ocr.py                       # Tesseract OCR text reader
│   ├── requirements.txt             # Python dependencies
│   └── models/                      # Place TFLite model & labels here
│       ├── yolo_tiny.tflite         # (not included – download separately)
│       └── coco.names               # (not included – download separately)
│
├── mobile/
│   └── drishti_app/                 # Flutter caregiver app
│       ├── lib/
│       │   ├── main.dart            # App entry point, routing & providers
│       │   ├── screens/
│       │   │   ├── home_screen.dart # Dashboard – status, location, SOS button
│       │   │   ├── map_screen.dart  # Live GPS map (OpenStreetMap via flutter_map)
│       │   │   └── sos_screen.dart  # Emergency alert status screen
│       │   └── services/
│       │       ├── gps_service.dart # Location stream + route history
│       │       └── sos_service.dart # SOS HTTP dispatch + local notifications
│       ├── android/
│       │   └── app/src/main/
│       │       └── AndroidManifest.xml
│       └── pubspec.yaml
│
├── README.md
└── .gitignore
```

---

## 🔧 Hardware Setup

### Components
| Component | Purpose |
|-----------|---------|
| ESP32-CAM (AI-Thinker) | Glasses – captures and streams video over Wi-Fi |
| Raspberry Pi 4 (2 GB+) | Smart cane brain – runs AI pipeline |
| HC-SR04 × 3 | Ultrasonic obstacle detection (front / left / right) |
| NEO-6M / NEO-8M GPS | Outdoor navigation & caregiver tracking |
| MPU-6050 | Inertial measurement (fall detection, orientation) |
| SIM800L / SIM7600 | GSM – SOS SMS + voice call |
| 3 W speaker + microphone | Audio I/O for feedback and voice commands |

### Wiring (GPIO – BCM numbering)

| Sensor | Signal | GPIO |
|--------|--------|------|
| HC-SR04 Front | TRIG / ECHO | 23 / 24 |
| HC-SR04 Left | TRIG / ECHO | 17 / 27 |
| HC-SR04 Right | TRIG / ECHO | 5 / 6 |
| GPS | TX → RX | /dev/ttyAMA0 |
| MPU-6050 | SDA / SCL | 2 / 3 (I²C bus 1) |
| GSM | TX / RX | /dev/ttyUSB0 |

---

## 🤖 AI Layer – Raspberry Pi Setup

### 1. System dependencies
```bash
sudo apt update && sudo apt install -y \
    tesseract-ocr \
    libportaudio2 \
    mpg123 \
    python3-pip
```

### 2. Python environment
```bash
cd ai/
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 3. Environment variables
Create `ai/.env` (or export in your shell):
```bash
export GEMINI_API_KEY="your-google-ai-key"
export ESP32_STREAM_URL="http://192.168.1.100/stream"
export WHISPER_MODEL="tiny"          # tiny | base | small
export TTS_ENGINE="gtts"             # gtts | pyttsx3
export ALERT_DISTANCE_CM="80"        # obstacle warning threshold
export CAREGIVER_API_URL="https://your-backend/api/location"
```

### 4. Download YOLO-Tiny TFLite model
```bash
# Export from YOLOv5 repository:
git clone https://github.com/ultralytics/yolov5
cd yolov5
pip install -r requirements.txt
python export.py --weights yolov5n.pt --include tflite --img 320
cp yolov5n_float32.tflite ../ai/models/yolo_tiny.tflite

# COCO class names
curl -o ai/models/coco.names \
  https://raw.githubusercontent.com/ultralytics/yolov5/master/data/coco128.yaml
```

### 5. Run
```bash
cd ai/
python main.py
```

---

## 📡 ESP32-CAM Setup

1. Open `hardware/esp32_cam/esp32_cam_stream.ino` in the Arduino IDE.
2. Update `WIFI_SSID` and `WIFI_PASS` with your network credentials.
3. Select board **AI Thinker ESP32-CAM** and upload.
4. Open the Serial Monitor at 115200 baud to get the stream URL.

> **Note:** Ensure the ESP32 and Raspberry Pi are on the same Wi-Fi network.

---

## 📱 Flutter App Setup

### Prerequisites
- Flutter SDK ≥ 3.0 – [install guide](https://docs.flutter.dev/get-started/install)
- Android Studio or Xcode

### Run
```bash
cd mobile/drishti_app/
flutter pub get
flutter run
```

### Configure backend URL
Edit `lib/services/sos_service.dart` and replace `_backendUrl` with your
actual backend endpoint.

### Build (Android release)
```bash
flutter build apk --release
```

---

## 🔐 Security & Privacy

- API keys are read from environment variables – **never commit them to Git**.
- Location data is transmitted only to the configured caregiver backend over HTTPS.
- Audio is processed locally by Whisper; only the scene-description query is sent to Gemini.

---

## 🗺 Roadmap

- [ ] Fall detection using IMU data
- [ ] Offline mode with a locally cached ONNX Gemini alternative
- [ ] Multi-language support (Hindi, Tamil, Telugu …)
- [ ] Wearable form factor PCB design
- [ ] Firebase Realtime Database integration for caregiver app

---

## 📄 License

MIT License – see [LICENSE](LICENSE) for details.

---

## 🙏 Acknowledgements

- [Google Gemini](https://ai.google.dev/) · [OpenAI Whisper](https://github.com/openai/whisper)
- [Ultralytics YOLOv5](https://github.com/ultralytics/yolov5) · [Tesseract OCR](https://github.com/tesseract-ocr/tesseract)
- [Flutter](https://flutter.dev/) · [flutter_map](https://github.com/fleaflet/flutter_map)
