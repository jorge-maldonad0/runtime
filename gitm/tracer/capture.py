"""Trace capture context manager.

    with gitm.tracer.capture(out_path) as trace:
        run_workload()
    # trace.events populated; JSONL written to out_path

CUPTI / rocprof backends are wired up behind ``_backend()``. When neither is
available (dev box without GPU), capture is a no-op that still writes a
well-formed empty trace — useful for plumbing tests.
"""

from __future__ import annotations

import json
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from gitm.tracer.schema import Trace


@contextmanager
def capture(
    out_path: str | Path,
    *,
    workload_id: str = "unknown",
    fingerprint: str = "unknown",
    run_id: str | None = None,
) -> Iterator[Trace]:
    """Capture a CUPTI/rocprof trace into ``out_path`` as JSONL.

    The yielded ``Trace`` is updated in-place as events arrive; the file is
    flushed on context exit. Capture overhead target: <5% of workload runtime
    (W2). The W1 target is <10%.
    """
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    backend = _backend()
    started_ns = time.time_ns()

    trace = Trace(
        workload_id=workload_id,
        fingerprint=fingerprint,
        run_id=run_id or uuid.uuid4().hex,
        device_count=backend.device_count() if backend else 0,
        vendor=backend.vendor if backend else "none",
        captured_at_ns=started_ns,
        duration_ns=0,
    )

    if backend is not None:
        backend.start()
    try:
        yield trace
    finally:
        ended_ns = time.time_ns()
        if backend is not None:
            events = backend.stop()
            trace.events = events
        trace.duration_ns = ended_ns - started_ns
        _write_jsonl(out_path, trace)


def _write_jsonl(path: Path, trace: Trace) -> None:
    """Stream trace events to JSONL — header line, then one event per line."""
    with path.open("w", encoding="utf-8") as fh:
        header = trace.model_dump(exclude={"events"})
        fh.write(json.dumps({"_header": header}))
        fh.write("\n")
        for ev in trace.events:
            fh.write(ev.model_dump_json())
            fh.write("\n")


def _backend():
    """Return the active CUPTI/rocprof backend, or ``None`` if unavailable.

    Implementation pending: returning ``None`` makes capture a well-formed
    no-op so the rest of the pipeline can be developed without a GPU.
    """
    try:
        from gitm.tracer.cupti import CuptiBackend  # noqa: F401
    except Exception:
        return None
    try:
        return CuptiBackend()
    except Exception:
        return None
