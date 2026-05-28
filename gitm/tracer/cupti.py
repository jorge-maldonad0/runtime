"""CUPTI backend stub — I1 fills this in Tue/Wed of Week 1.

CUPTI activity API callbacks are registered on ``start()``; per-kernel events
are buffered in C and drained on ``stop()`` into Python-side ``KernelEvent``
records. Memory + sync callbacks are added the next day.

Until the C bindings land, ``CuptiBackend()`` raises ``RuntimeError`` so
``capture()`` falls back to no-op.
"""

from __future__ import annotations

from gitm.tracer.schema import TraceEvent


class CuptiBackend:
    vendor = "nvidia"

    def __init__(self) -> None:
        raise RuntimeError("CUPTI backend not yet implemented — wire up in GITM-014")

    def device_count(self) -> int:  # pragma: no cover - stub
        return 0

    def start(self) -> None:  # pragma: no cover - stub
        ...

    def stop(self) -> list[TraceEvent]:  # pragma: no cover - stub
        return []
