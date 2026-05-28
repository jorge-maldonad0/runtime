"""24-hour loop phase orchestration.

The loop has 5 phases. Each phase has a clear input/output and a budget; the
scheduler enforces the budget and persists artifacts between phases so a
partial run is still useful.

    Hour 0-2   capture trace, fingerprint workload, predict graph
    Hour 2-6   residuals, attribution
    Hour 6-12  library query, counterfactual replay ranking
    Hour 12-20 apply top-N with rollback gates
    Hour 20-24 stabilize + write provenance report
"""

from __future__ import annotations

from gitm.scheduler.loop import LoopConfig, run_loop

__all__ = ["LoopConfig", "run_loop"]
