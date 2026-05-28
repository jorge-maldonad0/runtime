"""The 24-hour autonomous loop.

This is the orchestration glue — it composes tracer, planner, optimizer,
kernels, and agents in the 5 phases below. Each phase writes its artifact
under ``$GITM_DATA_ROOT/runs/<run_id>/`` so a partial run is still useful.
"""

from __future__ import annotations

import json
import re
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from gitm._paths import data_root, traces_dir
from gitm.agents.policy import Policy, select_interventions
from gitm.kernels.library import load_library
from gitm.optimizer.apply import apply_intervention
from gitm.optimizer.attribution import attribute
from gitm.optimizer.monitor import check_invariants, residuals
from gitm.optimizer.qualification import qualify
from gitm.optimizer.report import Claim, build_provenance, write_report
from gitm.planner.graph import predict_graph
from gitm.tracer.capture import capture


_BUDGET_RE = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*([smhd])\s*$")


def _parse_budget_s(budget: str) -> float:
    m = _BUDGET_RE.match(budget.lower())
    if not m:
        raise ValueError(f"unparseable budget: {budget!r} (use 24h, 90m, 3600s, 1d)")
    value, unit = float(m.group(1)), m.group(2)
    return value * {"s": 1.0, "m": 60.0, "h": 3600.0, "d": 86400.0}[unit]


@dataclass
class LoopConfig:
    engine: Any | None = None
    workload: str | None = None
    budget: str = "24h"
    target: float = 0.15
    data_root: str | None = None
    top_n_interventions: int = 5


def run_loop(cfg: LoopConfig) -> dict[str, Any]:
    """Execute the 24-hour loop and return ``{summary, report_md, ...}``."""
    workload = cfg.workload or (getattr(cfg.engine, "workload_id", None) or "vllm-decode")
    run_id = uuid.uuid4().hex
    budget_s = _parse_budget_s(cfg.budget)
    started_ns = time.time_ns()

    root = data_root(cfg.data_root)
    run_dir = root / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    trace_path = traces_dir(cfg.data_root) / f"{run_id}.jsonl"

    # Phase 1 — capture, fingerprint, predict graph
    with capture(trace_path, workload_id=workload, run_id=run_id) as trace:
        # The capture context normally runs the workload here; in the embedded
        # path the caller already drives the workload outside the loop.
        pass

    qual = qualify(trace, target_floor=cfg.target)
    (run_dir / "qualification.json").write_text(
        json.dumps(
            {
                "commit": qual.commit,
                "floor": qual.floor,
                "fingerprint": qual.fingerprint,
                "diagnostic": qual.diagnostic,
            },
            indent=2,
        )
    )

    graph = predict_graph()
    (run_dir / "predicted_graph.json").write_text(
        json.dumps({"nodes": len(graph.nodes), "total_pred_s": graph.total_pred_s}, indent=2)
    )

    # Phase 2 — residuals + attribution
    res = residuals(trace, graph)
    violations = check_invariants(res)
    hypotheses = attribute(res, graph)
    (run_dir / "residuals.json").write_text(
        json.dumps(
            {
                "n_kernel_residuals": len(res.per_kernel),
                "n_violations": len(violations),
                "top_hypotheses": [
                    {"cause": h.cause_op, "effect": h.effect_op, "p_value": h.p_value}
                    for h in hypotheses.top(5)
                ],
            },
            indent=2,
        )
    )

    # Phase 3 — library + counterfactual replay ranking
    library = load_library()
    policy = Policy(require_qualification_commit=qual.commit, skip_high_risk=not qual.commit)
    ranked = select_interventions(trace, library, policy, top_n=cfg.top_n_interventions)
    (run_dir / "ranked_candidates.json").write_text(
        json.dumps(
            [
                {
                    "name": c.spec.name,
                    "predicted_delta": c.predicted_delta,
                    "rejected_reason": c.rejected_reason,
                }
                for c in ranked
            ],
            indent=2,
        )
    )

    # Phase 4 — apply with rollback gates
    claims: list[Claim] = []
    rolled_back: list[str] = []
    rejected: list[str] = []
    for c in ranked:
        if c.rejected_reason is not None:
            rejected.append(f"{c.spec.name} ({c.rejected_reason})")
            continue
        result = apply_intervention(c.spec)
        if result.rolled_back:
            rolled_back.append(c.spec.name)
        claims.append(
            Claim(
                summary=c.spec.summary,
                residual_invariant="kernel_time",
                residual_value=0.0,
                causal_evidence=", ".join(
                    f"{h.cause_op}→{h.effect_op} (p={h.p_value:.2g})" for h in hypotheses.top(2)
                )
                or "no strong causal signal",
                intervention_name=c.spec.name,
                predicted_delta=c.predicted_delta,
                measured_delta=result.measured_delta,
                rolled_back=result.rolled_back,
            )
        )
        if time.time_ns() - started_ns >= int(budget_s * 1e9):
            break

    # Phase 5 — stabilize + write report
    provenance = build_provenance(
        workload_id=workload,
        fingerprint=qual.fingerprint,
        run_id=run_id,
        started_at_ns=started_ns,
        trace_path=str(trace_path),
    )
    provenance.rejected_candidates = rejected
    provenance.rolled_back = rolled_back

    report_md = write_report(
        claims=claims,
        provenance=provenance,
        qualification_diagnostic=qual.diagnostic,
    )
    (run_dir / "report.md").write_text(report_md)

    summary = {
        "run_id": run_id,
        "workload": workload,
        "fingerprint": qual.fingerprint,
        "commit": qual.commit,
        "floor": qual.floor,
        "n_claims": len(claims),
        "n_rolled_back": len(rolled_back),
        "n_rejected": len(rejected),
        "report_path": str(run_dir / "report.md"),
    }
    return {"summary": summary, "report_md": report_md, "run_dir": str(run_dir)}
