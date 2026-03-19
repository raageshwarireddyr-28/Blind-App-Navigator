"""
DRISHTI – Raspberry Pi sensor interface
========================================
Reads data from:
  • HC-SR04 ultrasonic distance sensors (front, left, right)
  • NEO-6M / NEO-8M GPS module (via UART)
  • MPU-6050 IMU (via I²C) – accelerometer + gyroscope

All sensor classes expose a simple `.read()` method that returns a dict.

Hardware wiring assumptions
----------------------------
HC-SR04 (front)  TRIG → GPIO 23   ECHO → GPIO 24
HC-SR04 (left)   TRIG → GPIO 17   ECHO → GPIO 27
HC-SR04 (right)  TRIG → GPIO 5    ECHO → GPIO 6
GPS UART         /dev/ttyAMA0  (or /dev/ttyS0)  9600 baud
MPU-6050         I²C bus 1, address 0x68
"""

from __future__ import annotations

import time
import logging
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Optional hardware imports – gracefully degrade when running off-device
# ---------------------------------------------------------------------------
try:
    import RPi.GPIO as GPIO  # type: ignore
    GPIO_AVAILABLE = True
except ImportError:
    GPIO_AVAILABLE = False
    logger.warning("RPi.GPIO not available – ultrasonic sensors disabled.")

try:
    import serial  # type: ignore
    import pynmea2  # type: ignore
    GPS_AVAILABLE = True
except ImportError:
    GPS_AVAILABLE = False
    logger.warning("pyserial / pynmea2 not available – GPS disabled.")

try:
    import smbus2  # type: ignore
    IMU_AVAILABLE = True
except ImportError:
    IMU_AVAILABLE = False
    logger.warning("smbus2 not available – IMU disabled.")


# ---------------------------------------------------------------------------
# Ultrasonic sensor
# ---------------------------------------------------------------------------
@dataclass
class UltrasonicSensor:
    """Single HC-SR04 sensor."""
    name: str
    trig_pin: int
    echo_pin: int
    max_distance_cm: float = 400.0  # practical sensing range

    def setup(self) -> None:
        if not GPIO_AVAILABLE:
            return
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(self.trig_pin, GPIO.OUT)
        GPIO.setup(self.echo_pin, GPIO.IN)
        GPIO.output(self.trig_pin, False)
        time.sleep(0.05)

    def read(self) -> dict:
        """Return distance in centimetres or -1 on error."""
        if not GPIO_AVAILABLE:
            return {"sensor": self.name, "distance_cm": -1, "error": "GPIO unavailable"}
        try:
            # Send 10 µs pulse
            GPIO.output(self.trig_pin, True)
            time.sleep(0.00001)
            GPIO.output(self.trig_pin, False)

            pulse_start = time.time()
            timeout = pulse_start + 0.04  # 40 ms timeout
            while GPIO.input(self.echo_pin) == 0:
                pulse_start = time.time()
                if pulse_start > timeout:
                    return {"sensor": self.name, "distance_cm": -1, "error": "echo timeout"}

            pulse_end = time.time()
            timeout = pulse_end + 0.04
            while GPIO.input(self.echo_pin) == 1:
                pulse_end = time.time()
                if pulse_end > timeout:
                    return {"sensor": self.name, "distance_cm": -1, "error": "echo timeout"}

            distance_cm = (pulse_end - pulse_start) * 17150  # speed of sound / 2
            distance_cm = round(min(distance_cm, self.max_distance_cm), 2)
            return {"sensor": self.name, "distance_cm": distance_cm}
        except Exception as exc:
            logger.exception("Ultrasonic read error: %s", exc)
            return {"sensor": self.name, "distance_cm": -1, "error": str(exc)}

    def cleanup(self) -> None:
        if GPIO_AVAILABLE:
            GPIO.cleanup([self.trig_pin, self.echo_pin])


# ---------------------------------------------------------------------------
# GPS module
# ---------------------------------------------------------------------------
class GPSModule:
    """Reads NMEA sentences from a UART-connected GPS module."""

    def __init__(self, port: str = "/dev/ttyAMA0", baudrate: int = 9600,
                 timeout: float = 1.0) -> None:
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self._serial: Optional[object] = None

    def connect(self) -> None:
        if not GPS_AVAILABLE:
            return
        self._serial = serial.Serial(
            self.port, self.baudrate, timeout=self.timeout
        )
        logger.info("GPS serial opened on %s @ %d baud", self.port, self.baudrate)

    def read(self) -> dict:
        """Return latitude, longitude, altitude and fix quality."""
        if not GPS_AVAILABLE or self._serial is None:
            return {"latitude": None, "longitude": None,
                    "altitude_m": None, "fix": False, "error": "GPS unavailable"}
        try:
            raw = self._serial.readline().decode("ascii", errors="replace").strip()
            if not raw.startswith("$"):
                return {"latitude": None, "longitude": None,
                        "altitude_m": None, "fix": False}
            msg = pynmea2.parse(raw)
            if msg.sentence_type in ("GGA", "RMC"):
                return {
                    "latitude":   getattr(msg, "latitude",  None),
                    "longitude":  getattr(msg, "longitude", None),
                    "altitude_m": getattr(msg, "altitude",  None),
                    "fix":        True,
                }
        except Exception as exc:
            logger.debug("GPS parse error: %s", exc)
        return {"latitude": None, "longitude": None,
                "altitude_m": None, "fix": False}

    def close(self) -> None:
        if self._serial is not None:
            self._serial.close()


# ---------------------------------------------------------------------------
# IMU (MPU-6050)
# ---------------------------------------------------------------------------
class IMUSensor:
    """
    MPU-6050 accelerometer + gyroscope over I²C.

    Register map (subset):
      0x3B – ACCEL_XOUT_H  (6 bytes accel)
      0x43 – GYRO_XOUT_H   (6 bytes gyro)
      0x6B – PWR_MGMT_1
    """
    MPU6050_ADDR = 0x68
    PWR_MGMT_1   = 0x6B
    ACCEL_XOUT_H = 0x3B
    GYRO_XOUT_H  = 0x43
    ACCEL_SCALE  = 16384.0   # ±2 g
    GYRO_SCALE   = 131.0     # ±250 °/s

    def __init__(self, bus_num: int = 1) -> None:
        self.bus_num = bus_num
        self._bus: Optional[object] = None

    def connect(self) -> None:
        if not IMU_AVAILABLE:
            return
        self._bus = smbus2.SMBus(self.bus_num)
        # Wake up MPU-6050 (clear sleep bit)
        self._bus.write_byte_data(self.MPU6050_ADDR, self.PWR_MGMT_1, 0)
        logger.info("IMU (MPU-6050) initialised on I²C bus %d", self.bus_num)

    def _read_word_2c(self, register: int) -> float:
        high = self._bus.read_byte_data(self.MPU6050_ADDR, register)
        low  = self._bus.read_byte_data(self.MPU6050_ADDR, register + 1)
        val  = (high << 8) | low
        return val - 65536 if val >= 0x8000 else float(val)

    def read(self) -> dict:
        """Return acceleration (g) and angular rate (°/s) on all three axes."""
        if not IMU_AVAILABLE or self._bus is None:
            return {"accel": None, "gyro": None, "error": "IMU unavailable"}
        try:
            ax = self._read_word_2c(self.ACCEL_XOUT_H)     / self.ACCEL_SCALE
            ay = self._read_word_2c(self.ACCEL_XOUT_H + 2) / self.ACCEL_SCALE
            az = self._read_word_2c(self.ACCEL_XOUT_H + 4) / self.ACCEL_SCALE
            gx = self._read_word_2c(self.GYRO_XOUT_H)      / self.GYRO_SCALE
            gy = self._read_word_2c(self.GYRO_XOUT_H + 2)  / self.GYRO_SCALE
            gz = self._read_word_2c(self.GYRO_XOUT_H + 4)  / self.GYRO_SCALE
            return {
                "accel": {"x": round(ax, 4), "y": round(ay, 4), "z": round(az, 4)},
                "gyro":  {"x": round(gx, 4), "y": round(gy, 4), "z": round(gz, 4)},
            }
        except Exception as exc:
            logger.exception("IMU read error: %s", exc)
            return {"accel": None, "gyro": None, "error": str(exc)}

    def close(self) -> None:
        if self._bus is not None:
            self._bus.close()


# ---------------------------------------------------------------------------
# Convenience: read all sensors at once
# ---------------------------------------------------------------------------
@dataclass
class SensorHub:
    ultrasonic_front: UltrasonicSensor = field(
        default_factory=lambda: UltrasonicSensor("front", trig_pin=23, echo_pin=24))
    ultrasonic_left: UltrasonicSensor = field(
        default_factory=lambda: UltrasonicSensor("left",  trig_pin=17, echo_pin=27))
    ultrasonic_right: UltrasonicSensor = field(
        default_factory=lambda: UltrasonicSensor("right", trig_pin=5,  echo_pin=6))
    gps: GPSModule = field(default_factory=GPSModule)
    imu: IMUSensor = field(default_factory=IMUSensor)

    def setup(self) -> None:
        for us in (self.ultrasonic_front, self.ultrasonic_left, self.ultrasonic_right):
            us.setup()
        self.gps.connect()
        self.imu.connect()

    def read_all(self) -> dict:
        return {
            "ultrasonic": [
                self.ultrasonic_front.read(),
                self.ultrasonic_left.read(),
                self.ultrasonic_right.read(),
            ],
            "gps": self.gps.read(),
            "imu": self.imu.read(),
        }

    def cleanup(self) -> None:
        for us in (self.ultrasonic_front, self.ultrasonic_left, self.ultrasonic_right):
            us.cleanup()
        self.gps.close()
        self.imu.close()


# ---------------------------------------------------------------------------
# Quick test
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    hub = SensorHub()
    hub.setup()
    try:
        while True:
            data = hub.read_all()
            print(data)
            time.sleep(1)
    except KeyboardInterrupt:
        hub.cleanup()
