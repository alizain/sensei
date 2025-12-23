"""Option 1: DSPy Wrapper Approach

Wrap the entire PydanticAI agent. DSPy optimizes the system prompt
while agent execution stays unchanged.

Pros:
- Minimal code changes to existing agent
- Full prompt optimization (all sections)
- Simple to understand

Cons:
- Coarse-grained (whole prompt, not specific decisions)
- Slower optimization (must run full agent each iteration)
- Harder to attribute improvements to specific changes
"""

import asyncio

import dspy

from sensei.agent import create_agent
from sensei.build import build_deps
from sensei.prompts import build_prompt


# =============================================================================
# 1. DSPy Module Wrapping the Agent
# =============================================================================


class SenseiWrapper(dspy.Module):
    """Wrap PydanticAI agent for DSPy optimization.

    DSPy optimizes the system_prompt string. The agent runs unchanged.
    """

    def __init__(self, initial_prompt: str):
        super().__init__()
        # This is the optimizable parameter
        self.system_prompt = initial_prompt

    def forward(self, query: str) -> str:
        """Run agent with current (possibly optimized) prompt."""
        # Create agent with current prompt
        agent = create_agent(
            include_spawn=True,
            include_exec_plan=False,
            system_prompt_override=self.system_prompt,  # Would need to add this param
        )

        # Build deps and run
        deps = asyncio.run(build_deps(query, parent_ctx=None))
        result = asyncio.run(agent.run(query, deps=deps))

        return result.output


# =============================================================================
# 2. Evaluator → DSPy Metric
# =============================================================================


def create_metric_from_evaluators(evaluator_classes: list, weights: dict[str, float]):
    """Convert pydantic-evals evaluators to a DSPy metric function."""

    def metric(example: dspy.Example, prediction: dspy.Prediction, trace=None) -> float:
        total_score = 0.0
        total_weight = 0.0

        for evaluator_cls in evaluator_classes:
            name = evaluator_cls.__name__
            weight = weights.get(name, 1.0)

            # Run evaluator (simplified - real impl would pass span tree)
            evaluator = evaluator_cls()
            issues = evaluator.evaluate(example.query, prediction.answer)

            # Convert issues to score (fewer issues = higher score)
            if not issues:
                score = 1.0
            else:
                severity_sum = sum(i.severity for i in issues)
                score = max(0.0, 1.0 - severity_sum / len(issues))

            total_score += score * weight
            total_weight += weight

        return total_score / total_weight if total_weight > 0 else 0.0

    return metric


# =============================================================================
# 3. Optimization Loop
# =============================================================================


def optimize_prompt(
    training_queries: list[str],
    evaluator_classes: list,
    weights: dict[str, float],
) -> str:
    """Run DSPy optimization on the system prompt."""

    # Setup DSPy
    dspy.configure(lm=dspy.LM("openai/gpt-4o"))

    # Create module with initial prompt
    initial_prompt = build_prompt("full_mcp")
    module = SenseiWrapper(initial_prompt)

    # Create metric
    metric = create_metric_from_evaluators(evaluator_classes, weights)

    # Create examples
    examples = [dspy.Example(query=q).with_inputs("query") for q in training_queries]

    # Optimize with MIPRO (better for instruction tuning)
    optimizer = dspy.MIPROv2(
        metric=metric,
        num_candidates=5,
    )

    optimized = optimizer.compile(module, trainset=examples)

    return optimized.system_prompt


# =============================================================================
# 4. Validation
# =============================================================================


def validate_improvement(
    old_prompt: str,
    new_prompt: str,
    test_queries: list[str],
    evaluator_classes: list,
) -> dict:
    """Compare old vs new prompt on test queries."""

    results = {"old": [], "new": []}

    for query in test_queries:
        # Run with old prompt
        old_module = SenseiWrapper(old_prompt)
        old_output = old_module.forward(query)

        # Run with new prompt
        new_module = SenseiWrapper(new_prompt)
        new_output = new_module.forward(query)

        # Score both
        for evaluator_cls in evaluator_classes:
            evaluator = evaluator_cls()
            old_issues = evaluator.evaluate(query, old_output)
            new_issues = evaluator.evaluate(query, new_output)

            results["old"].append(len(old_issues))
            results["new"].append(len(new_issues))

    return {
        "old_avg_issues": sum(results["old"]) / len(results["old"]),
        "new_avg_issues": sum(results["new"]) / len(results["new"]),
        "improvement": sum(results["old"]) - sum(results["new"]),
    }
