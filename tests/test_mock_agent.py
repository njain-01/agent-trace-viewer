import io
import unittest

from agent_trace_viewer.mock_agent import FakeClock, MockTools, run_mock_agent, safe_eval


class SafeEvalTests(unittest.TestCase):
    def test_arithmetic(self):
        self.assertEqual(safe_eval("3 * (2 ** 4) + 1"), 49)
        self.assertEqual(safe_eval("-2 + 5"), 3)

    def test_rejects_names_and_calls(self):
        for bad in ("__import__('os')", "a + 1", "len([1])"):
            with self.assertRaises(ValueError):
                safe_eval(bad)


class MockAgentTests(unittest.TestCase):
    def test_is_deterministic(self):
        a, b = io.StringIO(), io.StringIO()
        run_mock_agent(a)
        run_mock_agent(b)
        self.assertEqual(a.getvalue(), b.getvalue())

    def test_returns_final_answer(self):
        self.assertIn("jitter", run_mock_agent(io.StringIO()))

    def test_flaky_tool_fails_once_then_recovers(self):
        tools = MockTools(FakeClock())
        with self.assertRaises(TimeoutError):
            tools.fetch_status("svc")
        self.assertEqual(tools.fetch_status("svc"), "svc: healthy")


if __name__ == "__main__":
    unittest.main()
