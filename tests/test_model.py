import io
import unittest

from agent_trace_viewer.mock_agent import FakeClock, run_mock_agent
from agent_trace_viewer.model import TraceError, parse_trace
from agent_trace_viewer.recorder import Tracer


def trace_from_mock():
    buf = io.StringIO()
    run_mock_agent(buf)
    return parse_trace(buf.getvalue().splitlines())


class ModelTests(unittest.TestCase):
    def test_tree_structure_and_stats_from_mock_run(self):
        trace = trace_from_mock()
        self.assertEqual(len(trace.roots), 1)
        stats = trace.stats()
        self.assertEqual(stats["errors"], 1)
        self.assertEqual(stats["unfinished"], 0)
        self.assertEqual(stats["per_kind"]["tool"]["count"], 4)
        self.assertEqual(stats["slowest"]["name"], "fetch_status")
        self.assertAlmostEqual(stats["duration"], 6.56, places=2)

    def test_failed_tool_span_has_error_status(self):
        trace = trace_from_mock()
        failed = [s for s in trace.spans.values() if s.status == "error"]
        self.assertEqual(len(failed), 1)
        self.assertIn("TimeoutError", failed[0].error)

    def test_crashed_run_shows_unfinished_spans(self):
        buf = io.StringIO()
        clock = FakeClock()
        tracer = Tracer(buf, clock=clock)
        tracer.start("run", "r")
        clock.advance(2)
        tracer.start("tool", "hung")
        clock.advance(3)
        trace = parse_trace(buf.getvalue().splitlines())
        self.assertEqual(trace.stats()["unfinished"], 2)
        hung = [s for s in trace.spans.values() if s.name == "hung"][0]
        self.assertEqual(hung.status, "unfinished")
        self.assertAlmostEqual(hung.duration(trace.duration), 0.0)

    def test_walk_is_depth_first_in_start_order(self):
        trace = trace_from_mock()
        depths = [d for d, _ in trace.walk()]
        self.assertEqual(depths[0], 0)
        self.assertEqual(max(depths), 1)
        starts = [s.start for _, s in trace.walk()]
        self.assertEqual(starts, sorted(starts))

    def test_malformed_input_is_rejected_with_line_numbers(self):
        with self.assertRaisesRegex(TraceError, "line 1: invalid JSON"):
            parse_trace(["not json"])
        with self.assertRaisesRegex(TraceError, "unknown span 9"):
            parse_trace(['{"ev":"end","id":9,"ts":1}'])
        with self.assertRaisesRegex(TraceError, "unknown parent"):
            parse_trace(['{"ev":"start","id":1,"parent":5,"ts":0}'])
        with self.assertRaisesRegex(TraceError, "ended twice"):
            parse_trace(['{"ev":"start","id":1,"parent":null,"ts":0}',
                         '{"ev":"end","id":1,"ts":1}', '{"ev":"end","id":1,"ts":2}'])
        with self.assertRaisesRegex(TraceError, "empty"):
            parse_trace(["", "  "])


if __name__ == "__main__":
    unittest.main()
