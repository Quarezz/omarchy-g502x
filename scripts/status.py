#!/usr/bin/python3
"""Read G502 X LIGHTSPEED charge from sysfs and DPI over HID++. Prints one JSON object."""

from __future__ import annotations

import json
import signal
import sys
from io import StringIO
from pathlib import Path

SYSFS_ROOT = Path("/sys/class/power_supply")

# G502 X LIGHTSPEED on the LIGHTSPEED dongle only.
TRUSTED_VID = "046D"
TRUSTED_RECEIVER_PID = "C547"
TRUSTED_WPID = "409F"

JOB_DEADLINE_SEC = 2.0
MAX_SYSFS_BYTES = 256
MAX_TEXT = 48
MAX_JSON_BYTES = 2048
MAX_BATTERY_NODES = 8
KNOWN_MODELS = (
    "G502 X LIGHTSPEED",
    "Logitech G502 X LIGHTSPEED",
    "Logitech G502 X LS",
    "G502 X LS",
    "G502 X",
)
STATUS_LABELS = {
    "charging": "Charging",
    "discharging": "Discharging",
    "full": "Full",
    "not charging": "Not charging",
    "unknown": "Unknown",
}


class JobTimeout(Exception):
    pass


def _on_alarm(_signum, _frame) -> None:
    raise JobTimeout("hid++ deadline")


def _id(value) -> str:
    return str(value or "").strip().upper()


def _plain(value: str, max_len: int = MAX_TEXT) -> str:
    out: list[str] = []
    for ch in str(value or ""):
        code = ord(ch)
        if code < 32 or code == 127 or code > 126:
            continue
        out.append(ch)
        if len(out) >= max_len:
            break
    return "".join(out).strip()


def _read(path: Path) -> str:
    try:
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            return handle.read(MAX_SYSFS_BYTES)
    except OSError:
        return ""


def _hid_vid_pid(uevent: str) -> tuple[str, str]:
    for line in uevent.splitlines():
        if not line.startswith("HID_ID="):
            continue
        parts = line.split("=", 1)[1].strip().split(":")
        if len(parts) != 3:
            return "", ""
        vid = parts[1].upper()[-4:]
        pid = parts[2].upper()[-4:]
        return vid, pid
    return "", ""


def _trusted_battery(entry: Path) -> bool:
    device = entry / "device"
    try:
        hid = device.resolve()
    except OSError:
        return False
    vid, pid = _hid_vid_pid(_read(hid / "uevent"))
    if vid != TRUSTED_VID or pid != TRUSTED_WPID:
        return False
    parent = hid.parent
    if parent is None:
        return False
    pvid, ppid = _hid_vid_pid(_read(parent / "uevent"))
    return pvid == TRUSTED_VID and ppid == TRUSTED_RECEIVER_PID


def _status_label(raw: str) -> str:
    return STATUS_LABELS.get(_plain(raw, 32).lower(), "Unknown")


def _model_label(raw: str) -> str:
    name = _plain(raw, MAX_TEXT)
    for known in KNOWN_MODELS:
        if name.casefold() == known.casefold():
            return known
    return "G502 X"


def _empty_battery() -> dict:
    return {
        "present": False,
        "model": "",
        "percent": None,
        "status": "",
        "charging": False,
        "full": False,
        "discharging": False,
        "dpi": None,
    }


def _battery() -> dict:
    found = 0
    for entry in sorted(SYSFS_ROOT.glob("hidpp_battery_*")):
        found += 1
        if found > MAX_BATTERY_NODES:
            break
        if not _trusted_battery(entry):
            continue
        status = _status_label(_read(entry / "status"))
        percent_raw = _plain(_read(entry / "capacity"), 8)
        try:
            percent = int(percent_raw)
        except ValueError:
            percent = None
        if percent is not None:
            percent = max(0, min(100, percent))
        charging = status == "Charging" or status == "Full"
        discharging = status == "Discharging"
        full = status == "Full" or (charging and percent is not None and percent >= 99)
        return {
            "present": True,
            "model": _model_label(_read(entry / "model_name")),
            "percent": percent,
            "status": status,
            "charging": charging and not full,
            "full": full,
            "discharging": discharging,
        }
    return _empty_battery()


def _trusted_receiver(info) -> bool:
    return _id(getattr(info, "vendor_id", None)) == TRUSTED_VID and _id(
        getattr(info, "product_id", None)
    ) == TRUSTED_RECEIVER_PID


def _trusted_device(dev) -> bool:
    if _id(getattr(dev, "wpid", None)) != TRUSTED_WPID:
        return False
    rec = getattr(dev, "receiver", None)
    rec_pid = _id(getattr(rec, "product_id", None) if rec is not None else None)
    rec_vid = _id(getattr(rec, "vendor_id", None) if rec is not None else None)
    if rec_pid != TRUSTED_RECEIVER_PID:
        return False
    if rec_vid and rec_vid != TRUSTED_VID:
        return False
    return True


def _close(dev) -> None:
    closer = getattr(dev, "close", None)
    if callable(closer):
        try:
            closer()
        except Exception:
            pass


def _devices():
    from logitech_receiver import base
    from logitech_receiver import receiver as hid_receiver

    for info in base.receivers_and_devices():
        if getattr(info, "isDevice", False):
            continue
        if not _trusted_receiver(info):
            continue
        try:
            opened = hid_receiver.create_receiver(base, info)
            candidates = list(opened) if opened else []
        except Exception:
            continue
        for item in candidates:
            if item and _trusted_device(item):
                yield item


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
    previous = signal.getsignal(signal.SIGALRM)
    matched = None
    try:
        signal.signal(signal.SIGALRM, _on_alarm)
        signal.setitimer(signal.ITIMER_REAL, JOB_DEADLINE_SEC)
        for dev in _devices():
            matched = dev
            if set_to is not None:
                return _set_dpi(dev, set_to)
            return _read_dpi(dev)
    except (JobTimeout, Exception):
        return None
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous)
        sys.stderr = stderr
        if matched is not None:
            _close(matched)
    return None


def _parse_set_dpi(argv: list[str]) -> int | None:
    if len(argv) < 3 or argv[1] != "--set-dpi":
        return None
    try:
        value = int(argv[2])
    except ValueError:
        return None
    if value not in (400, 800, 1600, 3200, 6400):
        return None
    return value


def _emit(payload: dict) -> None:
    text = json.dumps(payload, separators=(",", ":"), ensure_ascii=True)
    if len(text.encode("ascii", "replace")) > MAX_JSON_BYTES:
        text = json.dumps(_empty_battery(), separators=(",", ":"), ensure_ascii=True)
    sys.stdout.write(text + "\n")
    sys.stdout.flush()


def main() -> int:
    payload = _battery()
    wanted = _parse_set_dpi(sys.argv)
    if payload["present"]:
        payload["dpi"] = _hid_dpi(wanted)
    else:
        payload["dpi"] = None
    _emit(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
