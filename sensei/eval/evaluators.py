"""Custom pydantic-evals evaluators for Sensei.

Span-based evaluators can inspect the full OpenTelemetry span tree, including
tool calls and tool outputs, via `EvaluatorContext.span_tree`.
"""

from dataclasses import dataclass
from typing import Any

from pydantic_evals.evaluators import Evaluator, EvaluatorContext


@dataclass
class ExampleEvaluator(Evaluator[str, str, Any]):
    """Example placeholder evaluator (always passes)."""

    def evaluate(self, ctx: EvaluatorContext[str, str, Any]) -> bool:
        _ = ctx.span_tree
        return True
