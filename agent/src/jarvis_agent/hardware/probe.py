"""Hardware presence: ``on`` / ``off`` from config, or ``auto`` = probe at startup.

Probes only look at the filesystem (``/dev``, ``/sys``, ``/proc``); no hardware libraries,
so they run anywhere and simply find nothing off-device (devcontainer, CI, laptop). Every
probe takes the filesystem root, so tests point it at a fake tree.
"""

import logging
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

log = logging.getLogger(__name__)

Toggle = Literal["on", "off", "auto"]
HARDWARE = ("hailo", "imx500", "mic", "speaker", "display")

# A probe returns evidence (e.g. the device path) if the hardware is present, else None.
Probe = Callable[[], str | None]

HAILO_PCI_VENDOR = "0x1e60"  # Hailo Technologies


@dataclass(frozen=True)
class HardwareStatus:
    present: bool
    reason: str  # "on in config", "off in config", "detected: /dev/hailo0", "not detected"


def probe_hailo(root: Path = Path("/")) -> str | None:
    """The Hailo driver's device node, or a Hailo PCI function (driver not loaded)."""
    if (dev := root / "dev/hailo0").exists():
        return f"/{dev.relative_to(root)}"
    for vendor in sorted((root / "sys/bus/pci/devices").glob("*/vendor")):
        if vendor.read_text().strip().lower() == HAILO_PCI_VENDOR:
            return f"PCI {vendor.parent.name}"
    return None


def probe_imx500(root: Path = Path("/")) -> str | None:
    """An IMX500 sensor among the V4L2 devices (the AI Camera)."""
    for name in sorted((root / "sys/class/video4linux").glob("*/name")):
        if "imx500" in (text := name.read_text().strip()).lower():
            return f"{name.parent.name}: {text}"
    return None


def probe_mic(root: Path = Path("/")) -> str | None:
    """An ALSA capture device (``pcmNc``)."""
    return _first(root, "proc/asound/card*/pcm*c")


def probe_speaker(root: Path = Path("/")) -> str | None:
    """An ALSA playback device (``pcmNp``)."""
    return _first(root, "proc/asound/card*/pcm*p")


def probe_display(root: Path = Path("/")) -> str | None:
    """A connected DRM connector (HDMI / DSI touchscreen)."""
    for status in sorted((root / "sys/class/drm").glob("card*-*/status")):
        if status.read_text().strip() == "connected":
            return status.parent.name
    return None


def default_probes(root: Path = Path("/")) -> dict[str, Probe]:
    probes = {
        "hailo": probe_hailo,
        "imx500": probe_imx500,
        "mic": probe_mic,
        "speaker": probe_speaker,
        "display": probe_display,
    }
    return {name: (lambda fn=fn: fn(root)) for name, fn in probes.items()}


def detect(
    toggles: Mapping[str, Toggle], probes: Mapping[str, Probe] | None = None
) -> dict[str, HardwareStatus]:
    """Resolve every toggle: ``on``/``off`` are trusted as-is, ``auto`` runs its probe.

    A probe that raises counts as not detected (with the error as the reason), so a flaky
    ``/sys`` read never stops startup.
    """
    probes = default_probes() if probes is None else probes
    status: dict[str, HardwareStatus] = {}
    for name, toggle in toggles.items():
        if toggle != "auto":
            status[name] = HardwareStatus(toggle == "on", f"{toggle} in config")
            continue
        probe = probes.get(name)
        try:
            evidence = probe() if probe else None
        except OSError as exc:
            log.warning("hardware probe %s failed: %s", name, exc)
            status[name] = HardwareStatus(False, f"probe failed: {exc}")
            continue
        status[name] = (
            HardwareStatus(True, f"detected: {evidence}")
            if evidence
            else HardwareStatus(False, "not detected")
        )
    return status


def _first(root: Path, pattern: str) -> str | None:
    match = next(iter(sorted(root.glob(pattern))), None)
    return f"/{match.relative_to(root)}" if match else None
