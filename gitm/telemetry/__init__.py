"""State telemetry — point-in-time GPU samples at ~1 Hz.

Source: NVML on NVIDIA, ROCm SMI on AMD. Costs microseconds per sample.
Shape: summary, not trace. Required for thermal, power, and clock invariants.
"""

from __future__ import annotations

from gitm.telemetry.collector import Collector, CollectorConfig
from gitm.telemetry.schema import Sample, ThrottleReason, WorkloadLabels

__all__ = [
    "Collector",
    "CollectorConfig",
    "Sample",
    "ThrottleReason",
    "WorkloadLabels",
]
