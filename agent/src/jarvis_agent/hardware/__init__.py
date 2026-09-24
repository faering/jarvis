"""Hardware layer: which devices this Jarvis has, from config toggles plus startup probes.

The bottom of the four layers (hardware -> backends -> capabilities -> tools). The real
inference path (Hailo SDK, IMX500, GPIO) is Pi-only; this package only detects presence.
"""

from jarvis_agent.hardware.probe import (
    HARDWARE,
    HardwareStatus,
    Probe,
    Toggle,
    default_probes,
    detect,
)

__all__ = ["HARDWARE", "HardwareStatus", "Probe", "Toggle", "default_probes", "detect"]
