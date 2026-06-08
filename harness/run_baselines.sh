#!/usr/bin/env bash
# Run all three KITTI PointPillars baselines (seeds 42, 43, 44) and
# check convergence.
#
# Usage:
#   bash harness/run_baselines.sh
#
# Required env vars:
#   GITM_DATA_ROOT      — root for datasets, checkpoints, and run outputs
#   OPENPCDET_CFG       — path to pointpillar.yaml  (set by setup_openpcdet.sh)
#   OPENPCDET_CKPT      — path to pointpillar_7728.pth  (set by setup_openpcdet.sh)
#
# Each baseline writes to $GITM_DATA_ROOT/runs/kitti_baseline_{1,2,3}.json
# After all three complete, the script prints a convergence summary.

set -euo pipefail

: "${GITM_DATA_ROOT:?ERROR: GITM_DATA_ROOT is not set}"
: "${OPENPCDET_CFG:?ERROR: OPENPCDET_CFG is not set (path to pointpillar.yaml)}"
: "${OPENPCDET_CKPT:?ERROR: OPENPCDET_CKPT is not set (path to pointpillar_7728.pth)}"

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
RUNS_DIR="$GITM_DATA_ROOT/runs"
mkdir -p "$RUNS_DIR"

N_FRAMES="${N_FRAMES:-7481}"   # set to smaller number for a quick check

run_baseline() {
  local seed="$1"
  local run_num="$2"
  local out="$RUNS_DIR/kitti_baseline_${run_num}.json"

  echo ""
  echo "══════════════════════════════════════════"
  echo "  Baseline $run_num  (seed=$seed, frames=$N_FRAMES)"
  echo "══════════════════════════════════════════"

  python -m gitm.benchmarks.kitti.baseline \
    --cfg    "$OPENPCDET_CFG" \
    --ckpt   "$OPENPCDET_CKPT" \
    --seed   "$seed" \
    --frames "$N_FRAMES" \
    --output "$out"

  echo "  Wrote: $out"
}

run_baseline 42 1
run_baseline 43 2
run_baseline 44 3

echo ""
echo "══════════════════════════════════════════"
echo "  Convergence check"
echo "══════════════════════════════════════════"

python - "$RUNS_DIR/kitti_baseline_1.json" \
         "$RUNS_DIR/kitti_baseline_2.json" \
         "$RUNS_DIR/kitti_baseline_3.json" << 'PYEOF'
import json, sys

paths = sys.argv[1:]
results = []
for p in paths:
    with open(p) as f:
        results.append(json.load(f))

fps_vals = [r["frames_per_second"] for r in results]
gpu_vals = [r["gpu_active_pct"] for r in results]

spread = (max(fps_vals) - min(fps_vals)) / max(fps_vals) * 100
ok = spread <= 2.0

print(f"  fps:  {' | '.join(f'{v:.2f}' for v in fps_vals)}")
print(f"  gpu%: {' | '.join(f'{v:.1f}' for v in gpu_vals)}")
print(f"  spread: {spread:.2f}%  ({'PASS ✓' if ok else 'FAIL — re-run and investigate'})")

max_gpu = max(gpu_vals)
if max_gpu > 85.0:
    print(f"\n  WARNING: GPU active {max_gpu:.1f}% > 85% — flag Adit for 500-frame fallback.")
else:
    print(f"\n  GPU active < 85% ✓")

if not ok:
    sys.exit(1)
PYEOF

echo ""
echo "All three baselines complete."
echo "Fill fps + stall numbers into benchmarks/kitti/spec.md and benchmarks/kitti/results.md"
