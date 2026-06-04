"""Vendor backends for state telemetry.

The Backend protocol abstracts over NVML, ROCm SMI, and any future vendor.
``discover_backends()`` returns only the live ones — one binary runs unchanged
on NVIDIA-only, AMD-only, and mixed-vendor nodes.
"""

from __future__ import annotations

from gitm.telemetry.backends.base import Backend
from gitm.telemetry.backends.discover import discover_backends

__all__ = ["Backend", "discover_backends"]
