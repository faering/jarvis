"""Where synthesized speech is played. The real sink (speaker on the Pi) is hardware-only."""

from typing import Protocol


class AudioSink(Protocol):
    async def play(self, wav: bytes) -> None:
        """Play ``wav`` and return once it has finished (or was stopped)."""
        ...

    async def stop(self) -> None:
        """Stop any playback now. Must be safe to call when nothing is playing."""
        ...


class NullSink:
    """Discards audio instantly: for tests, CI and the devcontainer (no speaker)."""

    async def play(self, wav: bytes) -> None:
        return None

    async def stop(self) -> None:
        return None
