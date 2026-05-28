"""Intervention library — curated levers for vLLM decode workloads.

Each entry in ``library.yaml`` has applicability conditions, expected delta
range with cited source, and safety gate. Every entry is reviewed by Adit
before commit. I2 curates entries in W2 (GITM-031..033).
"""

from __future__ import annotations

from gitm.kernels.library import load_library
from gitm.kernels.spec import InterventionSpec

__all__ = ["InterventionSpec", "load_library"]
