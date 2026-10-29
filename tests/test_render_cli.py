import io
import json
import os
import re
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout

from agent_trace_viewer.cli import main
from agent_trace_viewer.mock_agent import FakeClock
from agent_trace_viewer.model import parse_trace
from agent_trace_viewer.recorder import Tracer
from agent_trace_viewer.render import build_payload, render_html


def hostile_trace():
    buf = io.StringIO()
    tracer = Tracer(buf, clock=FakeClock())
    with tracer.span("run", "</script><img src=x onerror=alert(1)>", {"q": "</script>&"}):
        pass
    return parse_trace(buf.getvalue().splitlines())


class RenderTests(unittest.TestCase):
    def test_payload_rows_cover_all_spans(self):
        trace = hostile_trace()
        payload = build_payload(trace, "t")
        self.assertEqual(len(payload["spans"]), len(trace.spans))
        self.assertEqual(payload["spans"][0]["depth"], 0)

    def test_embedded_data_cannot_break_out_of_script(self):
        html = render_html(hostile_trace(), title="<b>x</b>")
        self.assertEqual(html.count("</script>"), 2)
        self.assertNotIn("<img src=x", html)
        self.assertIn("&lt;b&gt;x&lt;/b&gt;", html)
        block = re.search(r'id="trace-data">(.*?)</script>', html, re.S).group(1)
        data = json.loads(block)
        self.assertEqual(data["spans"][0]["name"], "</script><img src=x onerror=alert(1)>")


class CliTests(unittest.TestCase):
    def run_cli(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = main(list(argv))
        return code, out.getvalue(), err.getvalue()

    def test_demo_then_render_and_summary(self):
        with tempfile.TemporaryDirectory() as d:
            trace, html = os.path.join(d, "t.jsonl"), os.path.join(d, "t.html")
            code, out, _ = self.run_cli("demo", "--trace", trace, "--out", html)
            self.assertEqual(code, 0)
            self.assertIn("errors     1", out)
            self.assertTrue(os.path.getsize(html) > 1000)
            code, out, _ = self.run_cli("summary", trace)
            self.assertEqual(code, 0)
            self.assertIn("! tool:fetch_status", out)
            html2 = os.path.join(d, "r.html")
            code, _, _ = self.run_cli("render", trace, "--out", html2, "--title", "Custom")
            self.assertEqual(code, 0)
            with open(html2, encoding="utf-8") as fh:
                self.assertIn("<title>Custom</title>", fh.read())

    def test_bad_input_returns_error_code(self):
        with tempfile.TemporaryDirectory() as d:
            bad = os.path.join(d, "bad.jsonl")
            with open(bad, "w") as fh:
                fh.write("nope\n")
            code, _, err = self.run_cli("summary", bad)
            self.assertEqual(code, 1)
            self.assertIn("invalid JSON", err)
            code, _, err = self.run_cli("summary", os.path.join(d, "missing.jsonl"))
            self.assertEqual(code, 1)


if __name__ == "__main__":
    unittest.main()
