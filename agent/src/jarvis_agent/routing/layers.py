"""Compute layers and the providers that run on them.

A provider is one backend placed on one layer. ``backend=None`` means it is not present on
this device: off-device (devcontainer, CI) the camera and NPU slots are empty, so selection
falls through to the CPU orchestrator or a remote model.
"""

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from enum import StrEnum


class ComputeLayer(StrEnum):
    CAMERA = "camera"  # IMX500 on-sensor inference (Pi-only)
    NPU = "npu"  # Hailo-10H (Pi-only)
    CPU = "cpu"  # Pi 5 orchestrator, or the dev machine
    REMOTE = "remote"  # cloud / larger local model over HTTP; never on the hot path


@dataclass(frozen=True)
class Provider[T]:
    name: str
    layer: ComputeLayer
    backend: T | None = None

    @property
    def available(self) -> bool:
        return self.backend is not None


class NoProviderError(LookupError):
    """No available provider on any of the requested layers."""


def pick[T](providers: Iterable[Provider[T]], order: Sequence[ComputeLayer]) -> Provider[T]:
    """The first available provider, trying the layers in ``order`` in turn."""
    candidates = list(providers)
    for layer in order:
        for provider in candidates:
            if provider.layer == layer and provider.available:
                return provider
    raise NoProviderError(f"no available provider on layers: {', '.join(order)}")
