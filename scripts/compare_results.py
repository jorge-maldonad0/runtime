"""Compare two verification reports — "did we both get the same results?".

    python scripts/compare_results.py reference.json mine.json

Splits fields into two classes:

* **Must match exactly** — the reproducibility contract. Code (git_sha), pinned
  package versions, Python, and dataset manifest sha256s. Any mismatch here means
  you are not running the same thing, so results are not comparable.
* **Advisory** — GPU SKU / driver / CUDA. These don't have to match, but perf
  numbers are only comparable across the *same* GPU SKU, so a mismatch is flagged
  loudly.

Exit 0 if the exact-match contract holds, 1 otherwise. Performance numbers
themselves live in the per-benchmark BaselineRun JSONs and are gated separately
by ``gitm.bench`` (the <2% spread rule) — this tool checks you're on the same
software+data footing for that comparison to mean anything.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

EXACT = ["git_sha", "gitm_version", "python", "dataset_manifests"]
EXACT_PKGS = ["pydantic", "numpy", "pandas", "pyarrow", "torch", "cudf-cu12"]
ADVISORY = ["gpu"]


def _load(path: Path) -> dict:
    return json.loads(Path(path).read_text())


def compare(ref: dict, other: dict) -> tuple[list[str], list[str]]:
    """Return (mismatches, advisories)."""
    mismatches: list[str] = []
    advisories: list[str] = []

    for f in EXACT:
        if ref.get(f) != other.get(f):
            mismatches.append(f"{f}: {ref.get(f)!r} != {other.get(f)!r}")

    rp, op = ref.get("packages", {}), other.get("packages", {})
    for pkg in EXACT_PKGS:
        if rp.get(pkg) != op.get(pkg):
            mismatches.append(f"packages.{pkg}: {rp.get(pkg)} != {op.get(pkg)}")

    if ref.get("git_dirty") or other.get("git_dirty"):
        advisories.append("a report was produced from a DIRTY git tree "
                          "(uncommitted changes) — not reproducible")

    for f in ADVISORY:
        if ref.get(f) != other.get(f):
            advisories.append(f"{f} differs: {ref.get(f)} vs {other.get(f)} "
                              "(perf numbers only comparable on the same GPU SKU)")
    return mismatches, advisories


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Compare two GITM verify reports.")
    p.add_argument("reference", type=Path)
    p.add_argument("other", type=Path)
    args = p.parse_args(argv)

    mismatches, advisories = compare(_load(args.reference), _load(args.other))

    for a in advisories:
        print(f"  ADVISORY: {a}")
    if mismatches:
        print(f"\n❌ not REPRODUCIBLE — {len(mismatches)} exact-match field(s) differ:")
        for m in mismatches:
            print(f"  - {m}")
        return 1
    print("\n✅ REPRODUCIBLE — code, deps, Python, and dataset manifests all match."
          + ("" if not advisories else " (see advisories above)"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
