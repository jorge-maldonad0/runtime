"""Environment probe — ``gitm doctor``."""

from __future__ import annotations

import platform
import sys
from typing import Any

from gitm import __version__
from gitm._paths import data_root


def doctor() -> dict[str, Any]:
    """Probe the runtime environment and return a JSON-able report."""
    info: dict[str, Any] = {
        "gitm_version": __version__,
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "data_root": str(data_root()),
    }

    from gitm.telemetry.backends import discover_backends

    backends = discover_backends()
    info["telemetry_backends"] = [
        {"vendor": b.vendor, "device_count": b.device_count()} for b in backends
    ]
    return info
