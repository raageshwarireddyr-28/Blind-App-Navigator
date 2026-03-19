"""
DRISHTI – GSM module interface (SIM800L / SIM7600)
===================================================
Sends SMS alerts (SOS) and optionally makes voice calls via AT commands
over a UART serial connection.

Usage example
-------------
>>> gsm = GSMModule(port="/dev/ttyUSB0")
>>> gsm.connect()
>>> gsm.send_sms("+919876543210", "SOS! Help needed at 12.9716, 77.5946")
>>> gsm.close()
"""

from __future__ import annotations

import time
import logging
from typing import Optional

logger = logging.getLogger(__name__)

try:
    import serial  # type: ignore
    SERIAL_AVAILABLE = True
except ImportError:
    SERIAL_AVAILABLE = False
    logger.warning("pyserial not installed – GSM module disabled.")


class GSMModule:
    """Thin wrapper around AT-command GSM/GPRS modems."""

    def __init__(self, port: str = "/dev/ttyUSB0", baudrate: int = 9600,
                 timeout: float = 3.0) -> None:
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self._serial: Optional[object] = None

    # ------------------------------------------------------------------
    # Connection management
    # ------------------------------------------------------------------
    def connect(self) -> bool:
        """Open the serial port and verify modem is responsive."""
        if not SERIAL_AVAILABLE:
            logger.error("pyserial not available.")
            return False
        try:
            self._serial = serial.Serial(
                self.port, self.baudrate, timeout=self.timeout
            )
            time.sleep(1)
            response = self._send_at("AT")
            if "OK" in response:
                logger.info("GSM modem ready on %s", self.port)
                return True
            logger.error("Modem not responding: %s", response)
            return False
        except Exception as exc:
            logger.exception("GSM connect error: %s", exc)
            return False

    def close(self) -> None:
        if self._serial is not None:
            self._serial.close()
            self._serial = None

    # ------------------------------------------------------------------
    # Low-level AT command helper
    # ------------------------------------------------------------------
    def _send_at(self, command: str, wait: float = 0.5) -> str:
        if self._serial is None:
            return ""
        self._serial.write((command + "\r\n").encode())
        time.sleep(wait)
        response = ""
        while self._serial.in_waiting:
            response += self._serial.read(self._serial.in_waiting).decode(
                "ascii", errors="replace"
            )
        return response.strip()

    # ------------------------------------------------------------------
    # SMS
    # ------------------------------------------------------------------
    def send_sms(self, phone_number: str, message: str) -> bool:
        """
        Send an SMS via AT commands.

        Returns True on success, False otherwise.
        """
        if self._serial is None:
            logger.error("GSM not connected.")
            return False
        try:
            # Set SMS text mode
            if "OK" not in self._send_at("AT+CMGF=1"):
                logger.error("Failed to set SMS text mode.")
                return False

            # Specify recipient
            self._send_at(f'AT+CMGS="{phone_number}"', wait=0.3)

            # Send message body followed by Ctrl+Z (0x1A)
            self._serial.write((message + chr(26)).encode())
            time.sleep(3)  # modem needs time to transmit
            response = self._serial.read(self._serial.in_waiting).decode(
                "ascii", errors="replace"
            )
            if "+CMGS" in response or "OK" in response:
                logger.info("SMS sent to %s", phone_number)
                return True
            logger.error("SMS send failed: %s", response)
            return False
        except Exception as exc:
            logger.exception("send_sms error: %s", exc)
            return False

    # ------------------------------------------------------------------
    # Voice call
    # ------------------------------------------------------------------
    def make_call(self, phone_number: str) -> bool:
        """Dial a voice call.  Returns True if the call was initiated."""
        if self._serial is None:
            return False
        response = self._send_at(f"ATD{phone_number};", wait=2.0)
        if "OK" in response or "CONNECT" in response:
            logger.info("Call initiated to %s", phone_number)
            return True
        logger.error("Call failed: %s", response)
        return False

    def end_call(self) -> bool:
        """Hang up an ongoing call."""
        return "OK" in self._send_at("ATH")

    # ------------------------------------------------------------------
    # Signal quality
    # ------------------------------------------------------------------
    def signal_quality(self) -> int:
        """
        Return RSSI value (0–31, 99 = unknown).
        AT+CSQ response: +CSQ: <rssi>,<ber>
        """
        response = self._send_at("AT+CSQ")
        try:
            rssi_str = response.split("+CSQ:")[1].split(",")[0].strip()
            return int(rssi_str)
        except (IndexError, ValueError):
            return -1


# ---------------------------------------------------------------------------
# Quick test
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import os
    logging.basicConfig(level=logging.INFO)

    gsm = GSMModule(port=os.getenv("GSM_PORT", "/dev/ttyUSB0"))
    if gsm.connect():
        rssi = gsm.signal_quality()
        print(f"Signal quality (RSSI): {rssi}")
        # gsm.send_sms("+91XXXXXXXXXX", "DRISHTI SOS test message")
    gsm.close()
