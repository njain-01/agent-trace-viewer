"""Parse JSONL traces into a span tree and compute run statistics."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Iterable, Optional


class TraceError(ValueError):
    """Raised when a trace file is malformed."""


@dataclass
class Span:
    id: int
    parent: Optional[int]
    kind: str
    name: str
    start: float
    end: Optional[float] = None
    input: Any = None
    output: Any = None
    error: Optional[str] = None
    point: bool = False
    children: list["Span"] = field(default_factory=list)

    @property
    def status(self) -> str:
        if self.error is not None:
            return "error"
        if self.end is None and not self.point:
            return "unfinished"
        return "ok"

    def duration(self, trace_end: float) -> float:
        """Duration in seconds; unfinished spans run to the end of the trace."""
        if self.point:
            return 0.0
        return (self.end if self.end is not None else trace_end) - self.start


@dataclass
class Trace:
    roots: list[Span]
    spans: dict[int, Span]
    duration: float

    def walk(self) -> Iterable[tuple[int, Span]]:
        """Depth-first (depth, span) pairs in start order."""
        def rec(span: Span, depth: int) -> Iterable[tuple[int, Span]]:
            yield depth, span
            for child in span.children:
                yield from rec(child, depth + 1)
        for root in self.roots:
            yield from rec(root, 0)

    def stats(self) -> dict[str, Any]:
        per_kind: dict[str, dict[str, float]] = {}
        errors = unfinished = 0
        slowest: Optional[Span] = None
        slowest_d = -1.0
        for span in self.spans.values():
            d = span.duration(self.duration)
            bucket = per_kind.setdefault(span.kind, {"count": 0, "seconds": 0.0})
            bucket["count"] += 1
            bucket["seconds"] += d
            if span.status == "error":
                errors += 1
            elif span.status == "unfinished":
                unfinished += 1
            if span.kind != "run" and not span.point and d > slowest_d:
                slowest, slowest_d = span, d
        for bucket in per_kind.values():
            bucket["seconds"] = round(bucket["seconds"], 6)
        return {
            "duration": round(self.duration, 6),
            "span_count": len(self.spans),
            "errors": errors,
            "unfinished": unfinished,
            "per_kind": per_kind,
            "slowest": None if slowest is None else
            {"id": slowest.id, "name": slowest.name, "kind": slowest.kind,
             "seconds": round(slowest_d, 6)},
        }


def parse_trace(lines: Iterable[str]) -> Trace:
    spans: dict[int, Span] = {}
    roots: list[Span] = []
    max_ts = 0.0
    seen_any = False

    for lineno, raw in enumerate(lines, start=1):
        raw = raw.strip()
        if not raw:
            continue
        try:
            rec = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise TraceError(f"line {lineno}: invalid JSON ({exc.msg})") from exc
        if not isinstance(rec, dict) or "ev" not in rec or "id" not in rec:
            raise TraceError(f"line {lineno}: expected an object with 'ev' and 'id'")
        seen_any = True
        ev, sid = rec["ev"], rec["id"]
        ts = float(rec.get("ts", 0.0))
        max_ts = max(max_ts, ts)

        if ev in ("start", "point"):
            if sid in spans:
                raise TraceError(f"line {lineno}: duplicate span id {sid}")
            parent = rec.get("parent")
            span = Span(id=sid, parent=parent, kind=rec.get("kind", "event"),
                        name=str(rec.get("name", "")), start=ts,
                        input=rec.get("data"), point=(ev == "point"))
            spans[sid] = span
            if parent is None:
                roots.append(span)
            elif parent in spans:
                spans[parent].children.append(span)
            else:
                raise TraceError(f"line {lineno}: span {sid} has unknown parent {parent}")
        elif ev == "end":
            span = spans.get(sid)
            if span is None:
                raise TraceError(f"line {lineno}: end for unknown span {sid}")
            if span.end is not None:
                raise TraceError(f"line {lineno}: span {sid} ended twice")
            span.end = ts
            span.output = rec.get("data")
            span.error = rec.get("error")
        else:
            raise TraceError(f"line {lineno}: unknown event type {ev!r}")

    if not seen_any:
        raise TraceError("trace is empty")
    return Trace(roots=roots, spans=spans, duration=max_ts)


def load_trace(path: str) -> Trace:
    with open(path, encoding="utf-8") as fh:
        return parse_trace(fh)
