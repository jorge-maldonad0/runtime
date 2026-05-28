"""Resolve the external data root.

Datasets, traces, runs, and telemetry samples never live inside the repo.
"""

from __future__ import annotations

import os
from pathlib import Path


DEFAULT_DATA_ROOT = "~/gitm-data"


def data_root(override: str | None = None) -> Path:
    """Return the data root as an absolute Path.

    Resolution order: explicit ``override`` argument, then ``$GITM_DATA_ROOT``,
    then ``~/gitm-data``. The directory is created if it does not exist.
    """
    raw = override or os.environ.get("GITM_DATA_ROOT") or DEFAULT_DATA_ROOT
    root = Path(raw).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    for sub in ("datasets", "traces", "runs", "telemetry"):
        (root / sub).mkdir(parents=True, exist_ok=True)
    return root


def traces_dir(override: str | None = None) -> Path:
    return data_root(override) / "traces"


def runs_dir(override: str | None = None) -> Path:
    return data_root(override) / "runs"


def telemetry_dir(override: str | None = None) -> Path:
    return data_root(override) / "telemetry"


def datasets_dir(override: str | None = None) -> Path:
    return data_root(override) / "datasets"
