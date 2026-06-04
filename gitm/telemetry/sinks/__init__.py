"""Pluggable exporters for state-telemetry samples.

The ``Sink`` protocol keeps the collector decoupled from the backend choice:
prometheus, OTLP push, S3 — add a backend without touching the collector.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from gitm.telemetry.schema import Sample


@runtime_checkable
class Sink(Protocol):
    """Where ``Sample`` records go after the collector emits them."""

    def emit(self, sample: Sample) -> None: ...
    def close(self) -> None: ...


def build_sink(spec: str) -> Sink:
    """Construct a sink from a spec string.

    Examples:
        ``"jsonl:/tmp/samples.jsonl"`` — newline-delimited JSON to a file
        ``"prometheus:9400"`` — expose ``/metrics`` on the given port
        ``"otlp:http://collector:4318"`` — push to an OTLP endpoint
        ``"s3://bucket/prefix"`` — buffered append to S3 objects
    """
    if spec.startswith("jsonl:"):
        from gitm.telemetry.sinks.jsonl import JsonlSink

        return JsonlSink(spec[len("jsonl:") :])
    if spec.startswith("prometheus:"):
        from gitm.telemetry.sinks.prometheus import PrometheusSink

        return PrometheusSink(int(spec[len("prometheus:") :]))
    if spec.startswith("otlp:"):
        from gitm.telemetry.sinks.otlp import OtlpSink

        return OtlpSink(spec[len("otlp:") :])
    if spec.startswith("s3://"):
        from gitm.telemetry.sinks.s3 import S3Sink

        return S3Sink(spec)
    raise ValueError(f"unknown sink spec: {spec}")


__all__ = ["Sink", "build_sink"]
