"""Autonomous decision policy — selects interventions, drives rollback.

The agent layer is intentionally thin: rank candidates by predicted delta
returned from counterfactual replay, pre-filter by safety gate, apply with
rollback, observe live delta, persist the chain into the provenance trail.
"""

from __future__ import annotations

from gitm.agents.policy import Policy, RankedCandidate, select_interventions

__all__ = ["Policy", "RankedCandidate", "select_interventions"]
