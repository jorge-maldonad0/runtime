"""Vendor backend autodiscovery.

Initialize every known vendor backend; return only the live ones. A single
binary works unchanged on NVIDIA-only, AMD-only, and mixed-vendor nodes.
"""

from __future__ import annotations

from gitm.telemetry.backends.base import Backend


def discover_backends() -> list[Backend]:
    """Return all live vendor backends in discovery order.

    Each candidate is constructed in a try/except — if its vendor library is
    missing or no devices are present, it is silently skipped. The result is
    deterministic given the host.
    """
    found: list[Backend] = []

    try:
        from gitm.telemetry.backends.nvidia import NvidiaBackend

        nv = NvidiaBackend()
        if nv.device_count() > 0:
            found.append(nv)
        else:
            nv.close()
    except Exception:
        pass

    try:
        from gitm.telemetry.backends.amd import AmdBackend

        amd = AmdBackend()
        if amd.device_count() > 0:
            found.append(amd)
        else:
            amd.close()
    except Exception:
        pass

    return found
