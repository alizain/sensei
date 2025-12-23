"""Smoke-test Pydantic Evals span-based capture with Sensei.

This script:
1. Loads a small YAML dataset from `sensei/eval/datasets/`.
2. Runs the Sensei PydanticAI agent for each case via Pydantic Evals.
3. Prints the full OpenTelemetry span tree per case.

No quality evaluators/metrics are defined yet; this is only to verify that
spans are captured and accessible to span-based evaluators.
"""

from __future__ import annotations

# import logging
import json
import time
from dataclasses import asdict, dataclass
from typing import Any

try:
    import logfire
except ImportError:  # pragma: no cover
    logfire = None

from pydantic_evals import Dataset
from pydantic_evals.evaluators import Evaluator, EvaluatorContext

from sensei.eval.datasets import load_dataset
from sensei.eval.task import run_agent

# LOG_LEVEL = logging.INFO
# logging.basicConfig(
#     level=LOG_LEVEL,
#     format="%(asctime)s %(levelname)s %(name)s: %(message)s",
# )

DATASET_NAME = "general"


def process_ctx(obj: Any) -> Any:
    """Recursively parse JSON strings in specific keys that contain JSON-encoded values."""
    JSON_STRING_KEYS = {
        "gen_ai.input.messages",
        "gen_ai.output.messages",
        "logfire.json_schema",
        "logfire.metrics",
        "model_request_parameters",
        "pydantic_ai.all_messages",
        "tool_arguments",
        "tool_response",
    }

    if isinstance(obj, dict):
        result = {}
        for key, value in obj.items():
            if key in JSON_STRING_KEYS and isinstance(value, str):
                try:
                    result[key] = json.loads(value)
                except (json.JSONDecodeError, TypeError):
                    result[key] = value
            else:
                result[key] = process_ctx(value)
        return result
    elif isinstance(obj, list):
        return [process_ctx(item) for item in obj]
    else:
        return obj


@dataclass
class PrintSpans(Evaluator[str, str, Any]):
    """Span-based evaluator that prints the full span tree.

    Always returns True; used only for debugging span capture.
    """

    def evaluate(self, ctx: EvaluatorContext[str, str, Any]) -> bool:
        ctx_dict = asdict(ctx)

        # Parse JSON strings in specific keys
        ctx_dict = process_ctx(ctx_dict)

        # Write to file
        output_file = f"eval_context_{int(time.time())}.json"
        with open(output_file, "w") as f:
            json.dump(ctx_dict, f, indent=2, default=str)

        print(f"Context written to {output_file}")
        span_tree = ctx.span_tree
        if span_tree is None:
            print("\n=== No spans captured for case ===")
            return True

        print(f"\n=== Spans for case: {ctx.case.name or 'unnamed'} ===")

        for node in span_tree:
            indent = "  " * len(node.ancestors)
            duration = node.duration
            attrs = dict(node.attributes or {})
            print(f"{indent}- {node.name} ({duration})")
            if attrs:
                print(f"{indent}  attributes: {attrs}")

        return True


def main() -> None:
    # if logfire is not None:
    #     # Configure local tracing capture without sending to Logfire.
    #     logfire.configure(send_to_logfire=False)

    base_dataset = load_dataset(DATASET_NAME)
    dataset = Dataset(cases=base_dataset.cases[:2], evaluators=[PrintSpans()])

    report = dataset.evaluate_sync(run_agent)
    report.print(include_input=True, include_output=False, include_durations=False)


if __name__ == "__main__":
    main()
