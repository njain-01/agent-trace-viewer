"""Command-line interface: demo, render and summary."""

from __future__ import annotations

import argparse
import sys
from typing import Optional, Sequence

from .mock_agent import run_mock_agent
from .model import TraceError, load_trace
from .render import render_html


def format_summary(trace) -> str:
    s = trace.stats()
    lines = [
        f"duration   {s['duration']:.2f}s",
        f"spans      {s['span_count']}",
        f"errors     {s['errors']}",
        f"unfinished {s['unfinished']}",
    ]
    for kind in sorted(s["per_kind"]):
        k = s["per_kind"][kind]
        lines.append(f"  {kind:<6} {int(k['count']):>3} spans  {k['seconds']:.2f}s")
    if s["slowest"]:
        sl = s["slowest"]
        lines.append(f"slowest    {sl['kind']}:{sl['name']} ({sl['seconds']:.2f}s)")
    bad = [sp for _, sp in trace.walk() if sp.status != "ok"]
    for sp in bad:
        detail = sp.error or "never finished"
        lines.append(f"! {sp.kind}:{sp.name} at {sp.start:.2f}s - {detail}")
    return "\n".join(lines)


def _write_html(trace_path: str, out: str, title: str) -> None:
    html = render_html(load_trace(trace_path), title=title)
    with open(out, "w", encoding="utf-8") as fh:
        fh.write(html)


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="agent-trace-viewer", description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    demo = sub.add_parser("demo", help="run the offline mock agent and render its trace")
    demo.add_argument("--trace", default="demo.jsonl", help="where to write the JSONL trace")
    demo.add_argument("--out", default="demo.html", help="where to write the HTML report")

    render = sub.add_parser("render", help="render a JSONL trace to HTML")
    render.add_argument("trace")
    render.add_argument("--out", default="trace.html")
    render.add_argument("--title", default="Agent trace")

    summary = sub.add_parser("summary", help="print run statistics for a JSONL trace")
    summary.add_argument("trace")

    args = parser.parse_args(argv)
    try:
        if args.cmd == "demo":
            with open(args.trace, "w", encoding="utf-8") as fh:
                answer = run_mock_agent(fh)
            _write_html(args.trace, args.out, "Mock agent run")
            print(f"agent answer: {answer}")
            print(f"trace: {args.trace}")
            print(f"report: {args.out}")
            print(format_summary(load_trace(args.trace)))
        elif args.cmd == "render":
            _write_html(args.trace, args.out, args.title)
            print(f"report: {args.out}")
        else:
            print(format_summary(load_trace(args.trace)))
    except (TraceError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
