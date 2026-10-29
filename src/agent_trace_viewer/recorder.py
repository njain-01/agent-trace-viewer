"""Append-only JSONL recorder for agent runs."""

from __future__ import annotations

import json
import time
from contextlib import contextmanager
from typing import Any, Callable, Iterator, Optional, TextIO

FORMAT_VERSION = 1
KINDS = ("run", "llm", "tool", "event")


class Tracer:
    """Writes span start/end lines to a text stream.

    Lines are flushed as they are written, so a crashed run still leaves a
    readable trace with its open spans visible.
    """

    def __init__(self, stream: TextIO, clock: Optional[Callable[[], float]] = None):
        self._stream = stream
        self._clock = clock or time.monotonic
        self._t0 = self._clock()
        self._next_id = 1
        self._stack: list[int] = []

    def _now(self) -> float:
        return round(self._clock() - self._t0, 6)

    def _write(self, record: dict[str, Any]) -> None:
        record["v"] = FORMAT_VERSION
        self._stream.write(json.dumps(record, sort_keys=True, default=str) + "\n")
        self._stream.flush()

    def start(self, kind: str, name: str, data: Any = None) -> int:
        if kind not in KINDS:
            raise ValueError(f"unknown span kind {kind!r}, expected one of {KINDS}")
        span_id = self._next_id
        self._next_id += 1
        parent = self._stack[-1] if self._stack else None
        self._write({"ev": "start", "id": span_id, "parent": parent,
                     "kind": kind, "name": name, "ts": self._now(), "data": data})
        self._stack.append(span_id)
        return span_id

    def end(self, span_id: int, data: Any = None, error: Optional[str] = None) -> None:
        if not self._stack or self._stack[-1] != span_id:
            raise RuntimeError(f"span {span_id} is not the innermost open span")
        self._stack.pop()
        payload = {"ev": "end", "id": span_id, "ts": self._now(), "data": data}
        if error is not None:
            payload["error"] = error
        self._write(payload)

    def point(self, name: str, data: Any = None) -> int:
        """Record an instantaneous event under the current span."""
        span_id = self._next_id
        self._next_id += 1
        parent = self._stack[-1] if self._stack else None
        self._write({"ev": "point", "id": span_id, "parent": parent,
                     "kind": "event", "name": name, "ts": self._now(), "data": data})
        return span_id

    @contextmanager
    def span(self, kind: str, name: str, data: Any = None) -> Iterator["SpanHandle"]:
        span_id = self.start(kind, name, data)
        handle = SpanHandle()
        try:
            yield handle
        except BaseException as exc:
            self.end(span_id, handle.result, error=f"{type(exc).__name__}: {exc}")
            raise
        else:
            self.end(span_id, handle.result)


class SpanHandle:
    """Lets the body of a ``with tracer.span(...)`` block attach its output."""

    def __init__(self) -> None:
        self.result: Any = None

    def set_result(self, value: Any) -> None:
        self.result = value
