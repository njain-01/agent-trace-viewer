# Design: agent-trace-viewer

## Problem

Tool-calling agents run loops: the model thinks, calls a tool, reads the result,
calls another tool. When a run goes wrong or slow, plain logs make it hard to see
the order of steps, which step took the time, and which tool call failed. Hosted
tracing products solve this but need accounts, network access and often API keys.

## Approach

1. **Record**: a tiny `Tracer` writes one JSON object per line (JSONL) while the
   agent runs. Spans are written as a `start` line and an `end` line.
2. **Load**: `model.py` pairs start/end lines into a span tree and computes
   run-level statistics (duration, error count, slowest span, per-kind totals).
3. **Render**: `render.py` turns the tree into one self-contained HTML file with
   inline CSS and JS. No server, no network, no external assets.
4. **Mock agent**: `mock_agent.py` is a scripted, deterministic tool-calling
   agent used for the demo, tests and CI.

## Trace format

Each line is a JSON object:

| field    | meaning                                                        |
|----------|----------------------------------------------------------------|
| `v`      | format version (currently `1`)                                 |
| `ev`     | `start`, `end` or `point`                                      |
| `id`     | span id (unique within a trace)                                |
| `parent` | parent span id or `null`                                       |
| `kind`   | `run`, `llm`, `tool` or `event`                                |
| `name`   | human label, e.g. the tool name                                |
| `ts`     | seconds since the start of the run (float)                     |
| `data`   | free-form JSON: inputs on `start`, outputs/error on `end`      |

## Key decisions and trade-offs

- **JSONL, start/end lines.** Appending lines is crash-safe: if the agent dies,
  the open spans are still in the file and the viewer marks them as unfinished.
  The cost is that a reader must pair lines, which is cheap.
- **Standard library only.** No install friction, nothing to audit, runs in CI
  with no network. The cost is hand-written HTML instead of a UI framework.
- **Static HTML output.** One file can be attached to a ticket or opened offline.
  The cost is that very large traces (tens of thousands of spans) are not
  virtualised; the viewer is aimed at single agent runs.
- **Injectable clock.** The tracer takes a `clock` callable so tests and the demo
  are deterministic and need no sleeping.
- **Escaping.** All trace content is escaped and embedded as JSON in a
  `<script type="application/json">` block, with `<` escaped, so a trace cannot
  inject markup into the report.

## Out of scope

- Live streaming UI or a server.
- Real LLM provider integrations (the recorder is provider-agnostic).
- Cost accounting, token pricing and sampling.
- OpenTelemetry export.
