"""Render a Trace as one self-contained HTML file (inline CSS and JS)."""

from __future__ import annotations

import json
from typing import Any

from .model import Trace


def build_payload(trace: Trace, title: str) -> dict[str, Any]:
    rows = []
    for depth, span in trace.walk():
        rows.append({
            "id": span.id, "parent": span.parent, "depth": depth,
            "kind": span.kind, "name": span.name, "status": span.status,
            "start": span.start, "duration": round(span.duration(trace.duration), 6),
            "input": span.input, "output": span.output, "error": span.error,
            "point": span.point,
        })
    return {"title": title, "stats": trace.stats(), "spans": rows}


def safe_json(payload: Any) -> str:
    """JSON safe to embed inside a <script> element."""
    text = json.dumps(payload, ensure_ascii=False, default=str)
    return (text.replace("<", "\\u003c").replace(">", "\\u003e")
                .replace("&", "\\u0026").replace("\u2028", "\\u2028").replace("\u2029", "\\u2029"))


def render_html(trace: Trace, title: str = "Agent trace") -> str:
    data = safe_json(build_payload(trace, title))
    safe_title = (title.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))
    return _TEMPLATE.replace("__TITLE__", safe_title).replace("__DATA__", data)


_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITLE__</title>
<style>
:root { --bg:#fff; --fg:#1b1f24; --muted:#656d76; --line:#d8dee4; --panel:#f6f8fa;
  --run:#6e7781; --llm:#8250df; --tool:#0969da; --event:#bf8700; --err:#cf222e; }
@media (prefers-color-scheme: dark) { :root { --bg:#0d1117; --fg:#e6edf3; --muted:#8b949e;
  --line:#30363d; --panel:#161b22; --run:#8b949e; --llm:#a371f7; --tool:#58a6ff; --event:#d29922; --err:#ff7b72; } }
* { box-sizing: border-box; }
body { margin:0; padding:16px; background:var(--bg); color:var(--fg);
  font:14px/1.45 system-ui, -apple-system, Segoe UI, sans-serif; }
h1 { font-size:18px; margin:0 0 12px; }
.stats { display:flex; flex-wrap:wrap; gap:8px; margin-bottom:12px; }
.stat { background:var(--panel); border:1px solid var(--line); border-radius:6px; padding:6px 10px; }
.stat b { display:block; font-size:16px; }
.stat span { color:var(--muted); font-size:12px; }
.controls { display:flex; flex-wrap:wrap; gap:12px; align-items:center; margin-bottom:12px; }
.controls label { cursor:pointer; user-select:none; }
.row { display:grid; grid-template-columns: minmax(140px, 32%) 1fr 70px; gap:8px; align-items:center;
  padding:3px 4px; border-bottom:1px solid var(--line); cursor:pointer; }
.row:hover, .row.sel { background:var(--panel); }
.label { white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
.kind { font-size:11px; color:var(--muted); margin-right:6px; text-transform:uppercase; }
.track { position:relative; height:14px; background:var(--panel); border-radius:3px; }
.bar { position:absolute; top:2px; height:10px; min-width:3px; border-radius:2px; background:var(--run); }
.bar.llm { background:var(--llm); } .bar.tool { background:var(--tool); }
.bar.event { background:var(--event); } .bar.error { background:var(--err); }
.bar.unfinished { background-image:repeating-linear-gradient(45deg,transparent 0 4px,rgba(255,255,255,.5) 4px 8px); }
.dur { text-align:right; color:var(--muted); font-variant-numeric:tabular-nums; }
.err { color:var(--err); }
#detail { margin-top:16px; background:var(--panel); border:1px solid var(--line); border-radius:6px; padding:12px; }
#detail h2 { font-size:15px; margin:0 0 8px; }
#detail h3 { font-size:12px; text-transform:uppercase; color:var(--muted); margin:10px 0 4px; }
pre { margin:0; white-space:pre-wrap; word-break:break-word; font:12px/1.4 ui-monospace, Menlo, Consolas, monospace; }
@media (max-width:600px) { .row { grid-template-columns: 1fr 60px; } .track { display:none; } }
</style>
</head>
<body>
<h1 id="title"></h1>
<div class="stats" id="stats"></div>
<div class="controls">
  <label><input type="checkbox" id="errors-only"> errors and unfinished only</label>
  <label><input type="checkbox" id="hide-llm"> hide llm spans</label>
</div>
<div id="rows"></div>
<div id="detail" hidden></div>
<script type="application/json" id="trace-data">__DATA__</script>
<script>
(function () {
  var data = JSON.parse(document.getElementById('trace-data').textContent);
  var total = data.stats.duration || 1;
  var selected = null;

  function el(tag, cls, text) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text !== undefined) e.textContent = text;
    return e;
  }
  function fmt(s) { return s >= 1 ? s.toFixed(2) + ' s' : Math.round(s * 1000) + ' ms'; }
  function pretty(v) { return v === null || v === undefined ? '' : JSON.stringify(v, null, 2); }

  document.getElementById('title').textContent = data.title;
  var st = data.stats, statsEl = document.getElementById('stats');
  function stat(label, value, cls) {
    var d = el('div', 'stat'); var b = el('b', cls, value); d.appendChild(b); d.appendChild(el('span', '', label));
    statsEl.appendChild(d);
  }
  stat('total time', fmt(st.duration));
  stat('spans', String(st.span_count));
  stat('errors', String(st.errors), st.errors ? 'err' : '');
  stat('unfinished', String(st.unfinished), st.unfinished ? 'err' : '');
  if (st.slowest) stat('slowest step', st.slowest.name + ' (' + fmt(st.slowest.seconds) + ')');
  Object.keys(st.per_kind).sort().forEach(function (k) {
    stat(k + ' time (' + st.per_kind[k].count + ')', fmt(st.per_kind[k].seconds));
  });

  function showDetail(s) {
    var d = document.getElementById('detail');
    d.hidden = false; d.textContent = '';
    d.appendChild(el('h2', '', s.kind + ': ' + s.name));
    d.appendChild(el('div', '', 'status ' + s.status + ' | start ' + fmt(s.start) + ' | duration ' + fmt(s.duration)));
    if (s.error) { d.appendChild(el('h3', '', 'error')); d.appendChild(el('pre', 'err', s.error)); }
    if (s.input !== null && s.input !== undefined) { d.appendChild(el('h3', '', 'input')); d.appendChild(el('pre', '', pretty(s.input))); }
    if (s.output !== null && s.output !== undefined) { d.appendChild(el('h3', '', 'output')); d.appendChild(el('pre', '', pretty(s.output))); }
  }

  function render() {
    var onlyBad = document.getElementById('errors-only').checked;
    var hideLlm = document.getElementById('hide-llm').checked;
    var rows = document.getElementById('rows'); rows.textContent = '';
    data.spans.forEach(function (s) {
      if (onlyBad && s.status === 'ok') return;
      if (hideLlm && s.kind === 'llm') return;
      var row = el('div', 'row' + (selected === s.id ? ' sel' : ''));
      var label = el('div', 'label'); label.style.paddingLeft = (s.depth * 14) + 'px';
      label.appendChild(el('span', 'kind', s.kind));
      label.appendChild(el('span', s.status === 'ok' ? '' : 'err', s.name + (s.status === 'ok' ? '' : ' [' + s.status + ']')));
      var track = el('div', 'track');
      var cls = 'bar ' + s.kind + (s.status === 'error' ? ' error' : '') + (s.status === 'unfinished' ? ' unfinished' : '');
      var bar = el('div', cls);
      bar.style.left = (100 * s.start / total) + '%';
      bar.style.width = Math.max(0, 100 * s.duration / total) + '%';
      track.appendChild(bar);
      row.appendChild(label); row.appendChild(track); row.appendChild(el('div', 'dur', s.point ? 'event' : fmt(s.duration)));
      row.addEventListener('click', function () { selected = s.id; showDetail(s); render(); });
      rows.appendChild(row);
    });
  }
  document.getElementById('errors-only').addEventListener('change', render);
  document.getElementById('hide-llm').addEventListener('change', render);
  render();
})();
</script>
</body>
</html>
"""
