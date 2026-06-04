"""S3-backed sink — buffers JSONL and uploads in rolling objects.

Requires ``pip install gitm[s3]``.
"""

from __future__ import annotations

import threading
import time
from io import BytesIO
from urllib.parse import urlparse

from gitm.telemetry.schema import Sample


class S3Sink:
    """Buffer samples in memory; flush as gzipped JSONL objects to S3."""

    def __init__(self, url: str, flush_interval_s: int = 30) -> None:
        parsed = urlparse(url)
        if parsed.scheme != "s3":
            raise ValueError(f"S3Sink expects s3:// URL, got: {url}")
        self._bucket = parsed.netloc
        self._prefix = parsed.path.lstrip("/")
        self._flush_interval_s = flush_interval_s

        import boto3  # type: ignore[import-not-found]

        self._client = boto3.client("s3")
        self._buf: list[str] = []
        self._lock = threading.Lock()
        self._last_flush = time.monotonic()

    def emit(self, sample: Sample) -> None:
        line = sample.model_dump_json()
        with self._lock:
            self._buf.append(line)
            if time.monotonic() - self._last_flush >= self._flush_interval_s:
                self._flush_locked()

    def _flush_locked(self) -> None:
        if not self._buf:
            return
        body = ("\n".join(self._buf) + "\n").encode("utf-8")
        key = f"{self._prefix}/{int(time.time_ns())}.jsonl"
        self._client.upload_fileobj(BytesIO(body), self._bucket, key)
        self._buf.clear()
        self._last_flush = time.monotonic()

    def close(self) -> None:
        with self._lock:
            self._flush_locked()
