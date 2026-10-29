"""A scripted, deterministic tool-calling agent used for demos, tests and CI.

It needs no network and no API key. A fake clock makes timings reproducible
without sleeping.
"""

from __future__ import annotations

import ast
import operator
from typing import Any, Callable, Optional, TextIO

from .recorder import Tracer


class FakeClock:
    """Monotonic clock that only moves when told to."""

    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


_OPS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
        ast.Div: operator.truediv, ast.Pow: operator.pow, ast.USub: operator.neg}


def safe_eval(expr: str) -> float:
    """Evaluate plain arithmetic without exec/eval."""
    def ev(node: ast.AST) -> float:
        if isinstance(node, ast.Expression):
            return ev(node.body)
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return node.value
        if isinstance(node, ast.BinOp) and type(node.op) in _OPS:
            return _OPS[type(node.op)](ev(node.left), ev(node.right))
        if isinstance(node, ast.UnaryOp) and type(node.op) in _OPS:
            return _OPS[type(node.op)](ev(node.operand))
        raise ValueError(f"unsupported expression: {expr!r}")
    return ev(ast.parse(expr, mode="eval"))


DOCS = {
    "retry": "Retries with exponential backoff should add jitter to avoid thundering herds.",
    "timeout": "Every outbound call needs a deadline; propagate it down the call chain.",
}


class MockTools:
    """Tools the scripted agent can call. Each charges simulated latency."""

    def __init__(self, clock: FakeClock):
        self._clock = clock
        self._flaky_calls = 0

    def search_docs(self, query: str) -> str:
        self._clock.advance(0.35)
        hits = [text for key, text in DOCS.items() if key in query.lower()]
        return " ".join(hits) or "no results"

    def calculate(self, expression: str) -> float:
        self._clock.advance(0.01)
        return safe_eval(expression)

    def fetch_status(self, service: str) -> str:
        """Fails on the first call to show how errors appear in the timeline."""
        self._clock.advance(1.2)
        self._flaky_calls += 1
        if self._flaky_calls == 1:
            raise TimeoutError(f"{service} did not respond within 1.2s")
        self._clock.advance(0.4)
        return f"{service}: healthy"


# Each step is (simulated LLM latency, action). An action is either
# ("tool", name, kwargs) or ("final", text).
Step = tuple[float, tuple]

DEFAULT_SCRIPT: list[Step] = [
    (0.8, ("tool", "search_docs", {"query": "retry timeout guidance"})),
    (0.6, ("tool", "fetch_status", {"service": "billing-api"})),
    (0.5, ("tool", "fetch_status", {"service": "billing-api"})),
    (0.4, ("tool", "calculate", {"expression": "3 * (2 ** 4) + 1"})),
    (1.1, ("final", "Add jitter to retries, set deadlines on calls; billing-api is healthy; budget is 49.")),
]


def run_mock_agent(stream: TextIO, task: str = "Check billing-api and summarise retry guidance",
                   script: Optional[list[Step]] = None) -> str:
    """Run the scripted agent, writing its trace to ``stream``. Returns the answer."""
    clock = FakeClock()
    tracer = Tracer(stream, clock=clock)
    tools = MockTools(clock)
    registry: dict[str, Callable[..., Any]] = {
        "search_docs": tools.search_docs,
        "calculate": tools.calculate,
        "fetch_status": tools.fetch_status,
    }
    answer = ""
    with tracer.span("run", "mock-agent", {"task": task}) as run:
        for latency, action in (script or DEFAULT_SCRIPT):
            with tracer.span("llm", "mock-model", {"messages": 1}) as llm:
                clock.advance(latency)
                llm.set_result({"action": action[0], "detail": action[1] if action[0] == "tool" else None})
            if action[0] == "final":
                answer = action[1]
                tracer.point("final-answer", {"text": answer})
                break
            _, name, kwargs = action
            try:
                with tracer.span("tool", name, kwargs) as tool:
                    tool.set_result(registry[name](**kwargs))
            except Exception:
                # the failure is already recorded on the span; the script retries
                continue
        run.set_result({"answer": answer})
    return answer
