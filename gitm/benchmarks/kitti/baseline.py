"""KITTI PointPillars baseline runner.

Runs three convergent baselines over the 7,481 training frames, records the
stall breakdown, and writes a JSON result file per run.

Usage (on the RunPod GPU box):

    python -m gitm.benchmarks.kitti.baseline \\
        --cfg   /path/to/OpenPCDet/tools/cfgs/kitti_models/pointpillar.yaml \\
        --ckpt  $GITM_DATA_ROOT/checkpoints/kitti/pointpillar_7728.pth \\
        --seed  42 \\
        --frames 7481 \\
        --output $GITM_DATA_ROOT/runs/kitti_baseline_1.json

Stall breakdown methodology (proxy without CUPTI):
    data_stall_pct  = mean fraction of frame time on file-load + voxelization
    sync_stall_pct  = mean fraction of frame time on NMS (CPU-serialized)
    gpu_active_pct  = mean fraction of frame time in GPU backbone + BEV head
    cpu_pct         = 100 - data_stall_pct - sync_stall_pct - gpu_active_pct

NVML utilization is sampled at 5 Hz throughout the warm window as an
independent cross-check. It is stored in the JSON but not used for the
primary stall breakdown.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import threading
import time
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
MANIFEST_PATH = REPO_ROOT / "benchmarks" / "kitti" / "manifest.yaml"

WARM_FRAMES = 100  # discard before timing window
NVML_SAMPLE_HZ = 5


def _load_manifest_frame_paths(manifest_path: Path) -> list[Path]:
    """Return ordered list of velodyne .bin paths from the manifest."""
    import yaml

    with manifest_path.open() as fh:
        manifest = yaml.safe_load(fh)

    root = Path(manifest["kitti_object"]["root"])
    paths = []
    for frame in manifest["frames"]:
        entry = frame.get("velodyne")
        if entry is None:
            continue
        paths.append(root / entry["path"])
    return paths


def _sample_nvml(samples: list[float], stop_event: threading.Event) -> None:
    """Background thread: sample GPU 0 utilization at NVML_SAMPLE_HZ."""
    try:
        import pynvml

        pynvml.nvmlInit()
        handle = pynvml.nvmlDeviceGetHandleByIndex(0)
        interval = 1.0 / NVML_SAMPLE_HZ
        while not stop_event.is_set():
            util = pynvml.nvmlDeviceGetUtilizationRates(handle).gpu
            samples.append(float(util))
            time.sleep(interval)
        pynvml.nvmlShutdown()
    except Exception:
        pass  # no GPU or pynvml absent — nvml_mean_pct will be null in output


def _convergence_check(results: list[dict]) -> tuple[bool, float]:
    """Return (within_2pct, spread_pct) for a list of run results."""
    if len(results) < 2:
        return True, 0.0
    fps_vals = [r["frames_per_second"] for r in results]
    spread = (max(fps_vals) - min(fps_vals)) / max(fps_vals) * 100
    return spread <= 2.0, spread


def run_baseline(
    cfg_path: str | Path,
    ckpt_path: str | Path,
    seed: int,
    n_frames: int,
    output_path: str | Path,
    manifest_path: str | Path = MANIFEST_PATH,
) -> dict[str, Any]:
    """Run one baseline over n_frames KITTI frames and write JSON to output_path.

    Returns the result dict (same content as the JSON file).
    """
    import random

    from gitm.benchmarks.kitti.workunit import WorkUnit

    manifest_path = Path(manifest_path)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    all_paths = _load_manifest_frame_paths(manifest_path)
    if not all_paths:
        raise RuntimeError(f"Manifest {manifest_path} has no valid velodyne entries")

    rng = random.Random(seed)
    shuffled = list(all_paths)
    rng.shuffle(shuffled)
    run_paths = shuffled[:n_frames]

    total = len(run_paths)
    if total < WARM_FRAMES + 1:
        raise ValueError(
            f"n_frames={n_frames} is too small; need > {WARM_FRAMES} for warm window"
        )

    unit = WorkUnit.from_checkpoint(cfg_path=cfg_path, ckpt_path=ckpt_path)

    print(f"Warming up ({WARM_FRAMES} frames)…")
    for path in run_paths[:WARM_FRAMES]:
        unit.run(path)

    # Warm window
    warm_paths = run_paths[WARM_FRAMES:]
    nvml_samples: list[float] = []
    stop_event = threading.Event()
    nvml_thread = threading.Thread(
        target=_sample_nvml, args=(nvml_samples, stop_event), daemon=True
    )
    nvml_thread.start()

    t_wall_start = time.perf_counter()

    data_stall_fracs: list[float] = []
    sync_stall_fracs: list[float] = []
    gpu_active_fracs: list[float] = []
    total_detections = 0

    for i, path in enumerate(warm_paths):
        if i % 500 == 0:
            print(f"  {i}/{len(warm_paths)}")
        result = unit.run(path)
        data_stall_fracs.append(result.data_stall_frac)
        sync_stall_fracs.append(result.sync_stall_frac)
        gpu_active_fracs.append(result.gpu_active_frac)
        total_detections += result.n_detections

    t_wall_end = time.perf_counter()
    stop_event.set()
    nvml_thread.join(timeout=5)

    n_warm = len(warm_paths)
    elapsed = t_wall_end - t_wall_start
    fps = n_warm / elapsed

    data_stall_pct = sum(data_stall_fracs) / n_warm * 100
    sync_stall_pct = sum(sync_stall_fracs) / n_warm * 100
    gpu_active_pct = sum(gpu_active_fracs) / n_warm * 100
    cpu_pct = max(0.0, 100.0 - data_stall_pct - sync_stall_pct - gpu_active_pct)
    nvml_mean = sum(nvml_samples) / len(nvml_samples) if nvml_samples else None

    import platform
    import socket

    output = {
        "frames_per_second": round(fps, 3),
        "seed": seed,
        "n_frames_warm_window": n_warm,
        "gpu_active_pct": round(gpu_active_pct, 2),
        "data_stall_pct": round(data_stall_pct, 2),
        "sync_stall_pct": round(sync_stall_pct, 2),
        "cpu_pct": round(cpu_pct, 2),
        "nvml_mean_util_pct": round(nvml_mean, 2) if nvml_mean is not None else None,
        "total_detections": total_detections,
        "elapsed_s": round(elapsed, 3),
        "hostname": socket.gethostname(),
        "python": platform.python_version(),
        "cfg_path": str(cfg_path),
        "ckpt_path": str(ckpt_path),
        "manifest_path": str(manifest_path),
        "captured_at_iso": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }

    output_path.write_text(json.dumps(output, indent=2))
    print(f"\nResult: {fps:.1f} fps | GPU active {gpu_active_pct:.1f}% | wrote {output_path}")

    if nvml_mean is not None and nvml_mean > 85.0:
        print(
            f"\nWARNING: NVML util={nvml_mean:.1f}% > 85% — flag Adit: workload may be "
            "near-saturated. Consider the 500-frame fallback."
        )

    return output


def _check_convergence_across_runs(run_paths: list[Path]) -> None:
    """Read existing baseline JSONs and report convergence."""
    results = []
    for p in run_paths:
        if p.exists():
            with p.open() as fh:
                results.append(json.load(fh))
    ok, spread = _convergence_check(results)
    if len(results) >= 2:
        status = "PASS" if ok else "FAIL"
        print(
            f"Convergence ({len(results)} runs): {status} — spread={spread:.2f}% "
            f"(threshold 2.0%)"
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run one KITTI PointPillars baseline.")
    parser.add_argument("--cfg", required=True, help="OpenPCDet config .yaml path.")
    parser.add_argument("--ckpt", required=True, help="PointPillars checkpoint .pth path.")
    parser.add_argument("--seed", type=int, default=42, help="Random seed (42/43/44).")
    parser.add_argument("--frames", type=int, default=7481, help="Frames in warm window.")
    parser.add_argument("--output", required=True, help="Output .json path.")
    parser.add_argument(
        "--check-convergence",
        nargs="+",
        metavar="JSON",
        help="After writing, check convergence against these existing baseline JSONs.",
    )
    args = parser.parse_args(argv)

    run_baseline(
        cfg_path=args.cfg,
        ckpt_path=args.ckpt,
        seed=args.seed,
        n_frames=args.frames,
        output_path=args.output,
    )

    if args.check_convergence:
        all_paths = [Path(args.output)] + [Path(p) for p in args.check_convergence]
        _check_convergence_across_runs(all_paths)

    return 0


if __name__ == "__main__":
    sys.exit(main())
