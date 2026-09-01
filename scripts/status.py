#!/usr/bin/python3
"""Read G502 X LIGHTSPEED charge from sysfs and DPI over HID++. Prints one JSON object."""

from __future__ import annotations

import json
import sys
from io import StringIO
from pathlib import Path

SYSFS_ROOT = Path("/sys/class/power_supply")


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return ""


def _battery() -> dict:
    for entry in sorted(SYSFS_ROOT.glob("hidpp_battery_*")):
        model = _read(entry / "model_name")
        if "G502" not in model and "g502" not in model.lower():
            continue
        status = _read(entry / "status")
        percent_raw = _read(entry / "capacity")
        try:
            percent = int(percent_raw)
        except ValueError:
            percent = None
        charging = status.lower() in ("charging", "full")
        discharging = status.lower() == "discharging"
        return {
            "present": True,
            "model": model or "G502 X LIGHTSPEED",
            "percent": percent,
            "status": status or "Unknown",
            "charging": charging and percent is not None and percent < 99,
            "full": status.lower() == "full" or (charging and percent is not None and percent >= 99),
            "discharging": discharging,
        }
    return {
        "present": False,
        "model": "",
        "percent": None,
        "status": "",
        "charging": False,
        "full": False,
        "discharging": False,
    }


def _devices():
    from logitech_receiver import base
    from logitech_receiver import device as hid_device
    from logitech_receiver import receiver as hid_receiver

    for info in base.receivers_and_devices():
        try:
            if getattr(info, "isDevice", False):
                opened = hid_device.create_device(base, info)
                candidates = [opened] if opened else []
            else:
                opened = hid_receiver.create_receiver(base, info)
                candidates = list(opened) if opened else []
        except Exception:
            continue
        for item in candidates:
            if item:
                yield item


def _matches(dev) -> bool:
    name = str(getattr(dev, "name", "") or "")
    wpid = str(getattr(dev, "wpid", "") or "").upper()
    return "G502" in name or wpid == "409F"


def _read_dpi(dev) -> int | None:
    from logitech_receiver.hidpp20_constants import SupportedFeature

    reply = dev.feature_request(SupportedFeature.ADJUSTABLE_DPI, 0x20)
    if not reply or len(reply) < 5:
        return None
    current = (reply[1] << 8) | reply[2]
    if current == 0:
        current = (reply[3] << 8) | reply[4]
    if current <= 0:
        return None
    return int(current)


def _set_dpi(dev, dpi: int) -> int | None:
    from logitech_receiver.hidpp20_constants import SupportedFeature

    payload = bytes([0x00, (dpi >> 8) & 0xFF, dpi & 0xFF])
    reply = dev.feature_request(SupportedFeature.ADJUSTABLE_DPI, 0x30, payload)
    if not reply or len(reply) < 3:
        return _read_dpi(dev)
    current = (reply[1] << 8) | reply[2]
    if current <= 0:
        return _read_dpi(dev)
    return int(current)


def _hid_dpi(set_to: int | None) -> int | None:
    stderr = sys.stderr
    sys.stderr = StringIO()
    try:
        for dev in _devices():
            if not _matches(dev):
                continue
            if set_to is not None:
                return _set_dpi(dev, set_to)
            return _read_dpi(dev)
    except Exception:
        return None
    finally:
        sys.stderr = stderr
    return None


def _parse_set_dpi(argv: list[str]) -> int | None:
    if len(argv) < 3 or argv[1] != "--set-dpi":
        return None
    try:
        value = int(argv[2])
    except ValueError:
        return None
    value = max(100, min(25600, int(round(value / 50.0) * 50)))
    return value


def main() -> int:
    payload = _battery()
    wanted = _parse_set_dpi(sys.argv)
    if payload["present"]:
        payload["dpi"] = _hid_dpi(wanted)
    else:
        payload["dpi"] = None
    print(json.dumps(payload))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
