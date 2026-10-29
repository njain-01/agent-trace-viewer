import io
import json
import unittest

from agent_trace_viewer.mock_agent import FakeClock
from agent_trace_viewer.recorder import Tracer


def lines(buf):
    return [json.loads(x) for x in buf.getvalue().splitlines()]


class TracerTests(unittest.TestCase):
    def setUp(self):
        self.buf = io.StringIO()
        self.clock = FakeClock()
        self.tracer = Tracer(self.buf, clock=self.clock)

    def test_nested_spans_record_parents_and_times(self):
        with self.tracer.span("run", "r"):
            self.clock.advance(1)
            with self.tracer.span("tool", "t", {"x": 1}) as h:
                self.clock.advance(2)
                h.set_result("done")
        recs = lines(self.buf)
        self.assertEqual([r["ev"] for r in recs], ["start", "start", "end", "end"])
        self.assertIsNone(recs[0]["parent"])
        self.assertEqual(recs[1]["parent"], recs[0]["id"])
        self.assertEqual(recs[1]["ts"], 1.0)
        self.assertEqual(recs[2]["ts"], 3.0)
        self.assertEqual(recs[2]["data"], "done")

    def test_exception_is_recorded_and_reraised(self):
        with self.assertRaises(KeyError):
            with self.tracer.span("tool", "boom"):
                raise KeyError("missing")
        end = lines(self.buf)[-1]
        self.assertEqual(end["ev"], "end")
        self.assertIn("KeyError", end["error"])

    def test_unknown_kind_rejected(self):
        with self.assertRaises(ValueError):
            self.tracer.start("bogus", "x")

    def test_out_of_order_end_rejected(self):
        outer = self.tracer.start("run", "r")
        self.tracer.start("tool", "t")
        with self.assertRaises(RuntimeError):
            self.tracer.end(outer)

    def test_point_events_attach_to_current_span(self):
        with self.tracer.span("run", "r"):
            self.tracer.point("note", {"a": 1})
        recs = lines(self.buf)
        point = [r for r in recs if r["ev"] == "point"][0]
        self.assertEqual(point["parent"], recs[0]["id"])

    def test_non_json_values_do_not_crash(self):
        with self.tracer.span("tool", "t", {"obj": object()}):
            pass
        self.assertEqual(len(lines(self.buf)), 2)


if __name__ == "__main__":
    unittest.main()
