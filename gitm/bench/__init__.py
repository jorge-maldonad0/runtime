"""Shared benchmark systems layer.

The benchmark *layer* is deliberately dumb and identical across domains (HFT,
biotech, edge/robotics) so the runtime layer — planner, deviation monitor,
causal attribution — does the real work against a heterogeneous workload mix
without per-benchmark plumbing. Everything domain-specific lives in a single
``bench.toml`` per benchmark; everything mechanical lives here and is reused.

What this package gives every benchmark pair:

* :mod:`gitm.bench.schema` — the canonical data shapes: ``BenchConfig`` (parsed
  ``bench.toml``), ``StallPhase`` (one row of the stall-breakdown table), and
  ``BaselineRun`` (the ``<name>_baseline_N.json`` contract).
* :mod:`gitm.bench.manifest` — streaming sha256 manifest build + verify, so any
  holder of ``manifest.yaml`` can re-fetch byte-identical TB-scale datasets.
* :mod:`gitm.bench.baseline` — the two sign-off gates: three seeds agree within
  2 % (``spread``) and GPU active % stays under the ceiling (``saturation``).
* :mod:`gitm.bench.profile` — the GITM profiling wrapper around nsys/rocprof +
  py-spy/sar that produces the stall-breakdown table.
* :mod:`gitm.bench.edge_manifest` — the nuScenes+KITTI ``manifest.jsonl`` builder.
* :mod:`gitm.bench.results` — renders ``results.md``.

Driven from each ``benchmarks/<name>/Makefile`` via ``python -m gitm.bench``.
"""

from __future__ import annotations

from gitm.bench.schema import BaselineRun, BenchConfig, StallPhase

__all__ = ["BaselineRun", "BenchConfig", "StallPhase"]
