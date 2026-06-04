"""Live CUPTI capture smoke — run on a GPU box.

Launches a real CUDA workload (a few matmuls via torch) inside
``gitm.tracer.capture`` and asserts the CUPTI tracer ingested *sane* kernel
events. This is the check that proves the kernel-level ingestion works on real
hardware — and it is built to catch a CUPTI struct-version mismatch: if the
pinned record layout (``CUpti_ActivityKernel9`` etc.) doesn't match the box's
``cupti_activity.h``, the fields read as garbage, so we reject kernels with
non-positive duration or empty names instead of trusting a non-empty list.

Exit codes: 0 = pass, 1 = fail, 2 = skip (no torch / no CUDA device).
"""

from __future__ import annotations

import sys
from pathlib import Path


def main() -> int:
    try:
        import torch
    except Exception:
        print("SKIP: torch not installed (pip install torch)")
        return 2
    if not torch.cuda.is_available():
        print("SKIP: no CUDA device visible to torch")
        return 2

    from gitm.tracer._cupti import load_shim

    if load_shim() is None:
        print("FAIL: CUPTI shim not built — run `python -m gitm.tracer._cupti.build`")
        return 1

    from gitm.tracer import capture

    out = Path("/tmp/gitm_gpu_capture.jsonl")
    with capture(out, workload_id="gpu-smoke") as trace:
        a = torch.randn(1024, 1024, device="cuda")
        b = torch.randn(1024, 1024, device="cuda")
        acc = a
        for _ in range(20):
            acc = acc @ b
        # force a host<->device copy so memcpy activities show up too
        _ = acc.sum().item()
        torch.cuda.synchronize()

    kernels = [e for e in trace.events if e.kind == "kernel"]
    memcpys = [e for e in trace.events if e.kind == "memcpy"]
    print(f"captured {len(trace.events)} events: {len(kernels)} kernels, {len(memcpys)} memcpy")

    if not kernels:
        print("FAIL: no kernel events captured (CUPTI not collecting?)")
        return 1

    # Sanity gate — catches struct-version mismatch reading garbage fields.
    bad = [k for k in kernels if k.end_ns <= k.start_ns or not k.name]
    if bad:
        print(f"FAIL: {len(bad)}/{len(kernels)} kernels have bad duration/name — "
              "likely a CUPTI struct-version mismatch. Check the pinned "
              "CUpti_ActivityKernel* version in cupti_shim.c against this box's "
              "cupti_activity.h.")
        return 1

    print("sample kernels:", [k.name[:40] for k in kernels[:3]])
    print(f"PASS: live CUPTI capture produced {len(kernels)} sane kernel events")
    if not out.exists() or not out.read_text().strip():
        print("WARN: trace JSONL was not written")
    return 0


if __name__ == "__main__":
    sys.exit(main())
