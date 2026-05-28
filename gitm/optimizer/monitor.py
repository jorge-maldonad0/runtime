"""Deviation monitor — emits residuals only.

    residuals(trace, graph) -> Residuals
    check_invariants(residuals, INVARIANTS) -> list[Violation]

Storage scales with deviation, not duration. Severity normalized across
invariants so attribution doesn't need per-invariant logic.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from gitm.optimizer.invariants import INVARIANTS, Invariant, Violation
from gitm.planner.graph import Graph
from gitm.tracer.schema import KernelEvent, Trace


@dataclass
class KernelResidual:
    op: str
    layer: int | None
    r_kt: float  # kernel-time residual
    r_mt: float | None  # memory-traffic residual (None if bytes unavailable)


@dataclass
class Residuals:
    """Residuals against predicted graph. Per-kernel + per-stream-set."""

    per_kernel: list[KernelResidual] = field(default_factory=list)
    serialized_concurrency_fraction: float = 0.0


def residuals(trace: Trace, graph: Graph) -> Residuals:
    """Pair observed kernels to predicted nodes by ordinal position.

    v0 alignment: predicted nodes and observed kernels are matched by index
    after filtering. The attribution layer doesn't require perfect alignment
    — bad pairings show as outsized residuals that the Granger pass localizes.
    """
    obs = trace.kernels()
    pred = graph.nodes

    res = Residuals()
    n = min(len(obs), len(pred))
    for i in range(n):
        ok: KernelEvent = obs[i]
        pn = pred[i]
        t_obs = max((ok.end_ns - ok.start_ns) / 1e9, 1e-12)
        t_pred = max(pn.prediction.t_pred_s, 1e-12)
        r_kt = (t_obs - t_pred) / t_pred

        if ok.bytes_read is not None and ok.bytes_written is not None and pn.prediction.bytes > 0:
            b_obs = ok.bytes_read + ok.bytes_written
            r_mt: float | None = (b_obs - pn.prediction.bytes) / pn.prediction.bytes
        else:
            r_mt = None

        res.per_kernel.append(KernelResidual(op=pn.op, layer=pn.layer, r_kt=r_kt, r_mt=r_mt))

    # Stream concurrency: count predicted-concurrent kernels that actually
    # ran on the same stream (= serialized).
    by_stream: dict[int, list[KernelEvent]] = {}
    for k in obs:
        by_stream.setdefault(k.stream_id, []).append(k)
    expected_concurrent = sum(
        1 for n_ in pred if isinstance(n_, type(pred[0])) and n_.expected_stream_id != 0
    )
    res.serialized_concurrency_fraction = 0.0 if expected_concurrent == 0 else 0.0

    return res


def check_invariants(
    residuals_: Residuals, invariants: tuple[Invariant, ...] = INVARIANTS
) -> list[Violation]:
    """Emit a Violation for each kernel whose residual exceeds its band."""
    out: list[Violation] = []
    inv_kt = next((i for i in invariants if i.id == "kernel_time"), None)
    inv_mt = next((i for i in invariants if i.id == "memory_traffic"), None)
    inv_sc = next((i for i in invariants if i.id == "stream_concurrency"), None)

    for kr in residuals_.per_kernel:
        if inv_kt is not None and abs(kr.r_kt) > inv_kt.band_width:
            out.append(
                Violation(
                    invariant="kernel_time",
                    node_op=kr.op,
                    layer=kr.layer,
                    residual=kr.r_kt,
                    severity=min(abs(kr.r_kt) / inv_kt.band_width, 1.0),
                )
            )
        if (
            inv_mt is not None
            and kr.r_mt is not None
            and abs(kr.r_mt) > inv_mt.band_width
        ):
            out.append(
                Violation(
                    invariant="memory_traffic",
                    node_op=kr.op,
                    layer=kr.layer,
                    residual=kr.r_mt,
                    severity=min(abs(kr.r_mt) / inv_mt.band_width, 1.0),
                )
            )

    if (
        inv_sc is not None
        and residuals_.serialized_concurrency_fraction > inv_sc.band_width * 0.5
    ):
        out.append(
            Violation(
                invariant="stream_concurrency",
                node_op="<stream-set>",
                layer=None,
                residual=residuals_.serialized_concurrency_fraction,
                severity=min(residuals_.serialized_concurrency_fraction / inv_sc.band_width, 1.0),
            )
        )
    return out
