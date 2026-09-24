"""Hardware probing against a fake filesystem root: nothing here touches real devices."""

from pathlib import Path

import pytest

from jarvis_agent.hardware import HARDWARE, HardwareStatus, default_probes, detect


def touch(root: Path, rel: str, text: str = "") -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


@pytest.fixture
def pi(tmp_path: Path) -> Path:
    """A fake Pi root with every device present."""
    touch(tmp_path, "dev/hailo0")
    touch(tmp_path, "sys/class/video4linux/v4l-subdev0/name", "imx500 10-001a\n")
    touch(tmp_path, "proc/asound/card1/pcm0c/info")
    touch(tmp_path, "proc/asound/card2/pcm0p/info")
    touch(tmp_path, "sys/class/drm/card1-DSI-1/status", "connected\n")
    return tmp_path


def test_off_device_nothing_is_detected(tmp_path: Path) -> None:
    status = detect(dict.fromkeys(HARDWARE, "auto"), default_probes(tmp_path))
    assert not any(s.present for s in status.values())
    assert {s.reason for s in status.values()} == {"not detected"}


def test_auto_detects_every_device_on_a_pi(pi: Path) -> None:
    status = detect(dict.fromkeys(HARDWARE, "auto"), default_probes(pi))
    assert all(s.present for s in status.values())
    assert status["hailo"].reason == "detected: /dev/hailo0"
    assert status["imx500"].reason == "detected: v4l-subdev0: imx500 10-001a"
    assert status["mic"].reason == "detected: /proc/asound/card1/pcm0c"
    assert status["speaker"].reason == "detected: /proc/asound/card2/pcm0p"


def test_hailo_without_driver_found_on_pci(tmp_path: Path) -> None:
    touch(tmp_path, "sys/bus/pci/devices/0000:01:00.0/vendor", "0x1e60\n")
    touch(tmp_path, "sys/bus/pci/devices/0000:00:00.0/vendor", "0x14e4\n")
    status = detect({"hailo": "auto"}, default_probes(tmp_path))
    assert status["hailo"].reason == "detected: PCI 0000:01:00.0"


def test_disconnected_display_and_other_cameras_do_not_count(tmp_path: Path) -> None:
    touch(tmp_path, "sys/class/drm/card1-HDMI-A-1/status", "disconnected\n")
    touch(tmp_path, "sys/class/video4linux/video0/name", "uvcvideo\n")
    status = detect({"display": "auto", "imx500": "auto"}, default_probes(tmp_path))
    assert not status["display"].present and not status["imx500"].present


def test_on_and_off_skip_the_probe(pi: Path) -> None:
    def boom() -> str | None:
        raise AssertionError("probed")

    status = detect({"hailo": "off", "mic": "on"}, {"hailo": boom, "mic": boom})
    assert (status["hailo"].present, status["hailo"].reason) == (False, "off in config")
    assert (status["mic"].present, status["mic"].reason) == (True, "on in config")


def test_a_failing_probe_counts_as_absent() -> None:
    def broken() -> str | None:
        raise PermissionError("no access to /sys")

    status = detect({"hailo": "auto", "mic": "auto"}, {"hailo": broken})
    assert status["hailo"] == HardwareStatus(False, "probe failed: no access to /sys")
    assert status["mic"].reason == "not detected"  # no probe registered
