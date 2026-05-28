"""Public embedded API.

    from gitm import optimize
    optimize(engine, budget="24h", target=0.15)
"""

from __future__ import annotations

from typing import Any

from gitm.scheduler import LoopConfig, run_loop


def optimize(
    engine: Any | None = None,
    *,
    workload: str | None = None,
    budget: str = "24h",
    target: float = 0.15,
    data_root: str | None = None,
) -> dict[str, Any]:
    """Run the autonomous 24-hour optimization loop and return a report.

    Either pass an ``engine`` (e.g. a running vLLM engine handle) for the
    embedded path, or pass ``workload`` (e.g. ``"vllm-decode"``) for the CLI
    path. ``budget`` and ``target`` follow the SKU contract: a verified floor
    of ``target`` fraction improvement within ``budget`` wall time, or a
    qualification-gate diagnostic explaining why the floor was not committed.
    """
    cfg = LoopConfig(
        engine=engine,
        workload=workload,
        budget=budget,
        target=target,
        data_root=data_root,
    )
    return run_loop(cfg)
