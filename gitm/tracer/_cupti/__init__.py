"""CUPTI native shim package.

Exposes :func:`load_shim`, which imports the compiled ``_cupti_shim`` extension
if it was built (see :mod:`gitm.tracer._cupti.build`). Returns ``None`` when the
extension is absent — a CPU-only host, or a GPU box where the build hasn't been
run — so callers degrade gracefully instead of raising on import.
"""

from __future__ import annotations

from types import ModuleType


def load_shim() -> ModuleType | None:
    """Return the compiled CUPTI shim module, or ``None`` if unavailable."""
    try:
        from gitm.tracer._cupti import _cupti_shim  # type: ignore[attr-defined]
    except Exception:
        return None
    return _cupti_shim


def available() -> bool:
    return load_shim() is not None
