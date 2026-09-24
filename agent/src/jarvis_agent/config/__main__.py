"""``python -m jarvis_agent.config``: print the resolved config and what Jarvis can do.

Reads the same layers as startup (profile, ``JARVIS_CONFIG``, env), probes the hardware and
resolves the capabilities. Secrets are masked. Exits 1 on invalid config.
"""

import json
import os
import sys
from collections.abc import Mapping
from typing import TextIO

from jarvis_agent.capabilities import Available, resolve
from jarvis_agent.config.loader import ConfigError, load_config
from jarvis_agent.hardware import Probe, detect


def main(
    environ: Mapping[str, str] | None = None,
    probes: Mapping[str, Probe] | None = None,
    out: TextIO = sys.stdout,
) -> int:
    try:
        config = load_config(os.environ if environ is None else environ)
        hardware = detect(config.hardware.model_dump(), probes)
        report = resolve(Available.from_config(config, hardware), config.capabilities)
    except ConfigError as exc:
        print(exc, file=sys.stderr)
        return 1

    print(f"Sources (later wins): {' -> '.join(config.sources)}", file=out)
    # JSON mode renders SecretStr as "**********".
    print(json.dumps(config.model_dump(mode="json"), indent=2), file=out)
    print("\nHardware", file=out)
    for name, status in hardware.items():
        print(f"  {name:<16} {'yes' if status.present else 'no':<9} {status.reason}", file=out)
    print("\nCapabilities", file=out)
    for name, on in report.enabled.items():
        provider = on.provider
        print(f"  {name:<16} {'enabled':<9} {provider.name} ({provider.layer})", file=out)
    for name, off in report.disabled.items():
        flag = "REQUIRED " if off.required else ""
        print(f"  {name:<16} {'disabled':<9} {flag}{off.reason}", file=out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
