"""Event telemetry — per-kernel activity records from CUPTI / rocprof.

The trace is the empirical half of the residual equation. Per-kernel start
and end timestamps, stream IDs, memory transfer events. Required for the
kernel-time invariant.
"""

from __future__ import annotations

from gitm.tracer.capture import capture
from gitm.tracer.schema import KernelEvent, MemcpyEvent, SyncEvent, Trace, TraceEvent

__all__ = [
    "capture",
    "Trace",
    "TraceEvent",
    "KernelEvent",
    "MemcpyEvent",
    "SyncEvent",
]
