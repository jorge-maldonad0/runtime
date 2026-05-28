"""Apply an intervention spec to the live workload, with rollback gate.

    apply_intervention(spec) -> ApplyResult

I1 fills in the vLLM-side application in W2 (GITM-020). The rollback snapshot
is taken before each apply; on failure the previous state is restored.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

from gitm.kernels.spec import InterventionSpec


@dataclass
class ApplyResult:
    applied: bool
    rolled_back: bool
    measured_delta: float | None
    error: str | None = None


def apply_intervention(spec: InterventionSpec) -> ApplyResult:
    """Live-apply an intervention with rollback gate.

    Stub for the W1 skeleton — returns ``applied=False`` with a clear error
    so end-to-end smoke tests pass and the agent loop can be exercised
    without a GPU.
    """
    return ApplyResult(
        applied=False,
        rolled_back=False,
        measured_delta=None,
        error="apply_intervention not yet implemented — wire up in GITM-020",
    )


def apply_intervention_from_file(path: Path) -> dict:
    with open(path) as fh:
        data = yaml.safe_load(fh)
    spec = InterventionSpec.model_validate(data)
    res = apply_intervention(spec)
    return {
        "intervention": spec.name,
        "applied": res.applied,
        "rolled_back": res.rolled_back,
        "measured_delta": res.measured_delta,
        "error": res.error,
    }
