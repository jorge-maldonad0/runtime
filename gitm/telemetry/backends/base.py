"""Backend protocol — vendor-neutral interface to GPU state sampling."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from gitm.telemetry.schema import Sample, WorkloadLabels


@runtime_checkable
class Backend(Protocol):
    """Protocol every vendor backend implements.

    Implementations must be process-safe: a single backend object is shared
    across the collector daemon thread.
    """

    vendor: str  # "nvidia" | "amd"

    def device_count(self) -> int:
        """Number of live GPUs this backend can see."""

    def sample(self, gpu_index: int, labels: WorkloadLabels | None = None) -> Sample:
        """Sample one GPU. Must not raise on per-field failures — use ``_try``."""

    def close(self) -> None:
        """Release vendor library handles."""
