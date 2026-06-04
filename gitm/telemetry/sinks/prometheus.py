"""Prometheus sink — exposes ``/metrics`` on a port.

Requires the ``prometheus`` extra: ``pip install gitm[prometheus]``.
"""

from __future__ import annotations

from gitm.telemetry.schema import Sample


class PrometheusSink:
    def __init__(self, port: int) -> None:
        from prometheus_client import Gauge, start_http_server  # type: ignore[import-not-found]

        self._port = port
        start_http_server(port)
        labels = ["node", "gpu_uuid", "gpu_index", "vendor", "workload_id"]
        self._util = Gauge("gitm_gpu_util_pct", "GPU utilization percent", labels)
        self._mem = Gauge("gitm_gpu_mem_used_bytes", "GPU memory used bytes", labels)
        self._power = Gauge("gitm_gpu_power_w", "GPU power draw watts", labels)
        self._temp = Gauge("gitm_gpu_temp_c", "GPU temperature celsius", labels)
        self._sm = Gauge("gitm_gpu_sm_clock_mhz", "GPU SM clock MHz", labels)

    def _labels(self, s: Sample) -> dict[str, str]:
        wl = s.labels.workload_id if s.labels else "unknown"
        return {
            "node": s.node,
            "gpu_uuid": s.gpu_uuid,
            "gpu_index": str(s.gpu_index),
            "vendor": s.vendor,
            "workload_id": wl,
        }

    def emit(self, sample: Sample) -> None:
        labels = self._labels(sample)
        if sample.util_pct is not None:
            self._util.labels(**labels).set(sample.util_pct)
        if sample.mem_used_bytes is not None:
            self._mem.labels(**labels).set(sample.mem_used_bytes)
        if sample.power_w is not None:
            self._power.labels(**labels).set(sample.power_w)
        if sample.temp_c is not None:
            self._temp.labels(**labels).set(sample.temp_c)
        if sample.sm_clock_mhz is not None:
            self._sm.labels(**labels).set(sample.sm_clock_mhz)

    def close(self) -> None:
        return None
