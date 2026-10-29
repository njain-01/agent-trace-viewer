"""Record tool-calling agent runs as JSONL and render them as an HTML timeline."""

from .recorder import Tracer
from .model import Trace, Span, load_trace, parse_trace

__all__ = ["Tracer", "Trace", "Span", "load_trace", "parse_trace"]
__version__ = "0.1.0"
