"""Sequential Component Optimization for Sensei Prompts.

This optimizer improves prompt components one at a time:
1. For each component (IDENTITY, CONFIDENCE_LEVELS, etc.)
2. Generate N variants of that component
3. Build full prompts = (frozen components) + (each variant)
4. Evaluate all variants, pick the best
5. Freeze this component with best version
6. Move to next component

Why this approach:
- Preserves modular prompt structure from prompts.py
- Linear search space (components × variants) instead of exponential
- Clear attribution: know which component improved
- Can prioritize which components to optimize first
"""

import asyncio
from dataclasses import dataclass
from typing import Callable

import dspy

from sensei.agent import create_agent
from sensei.build import build_deps


# =============================================================================
# 1. Define Optimizable Components
# =============================================================================

# Each component has a name and its current text from prompts.py
# We import them dynamically to avoid coupling


@dataclass
class PromptComponent:
    """A single optimizable prompt section."""

    name: str
    current_text: str
    description: str  # For the variant generator


def load_components() -> list[PromptComponent]:
    """Load current prompt components from prompts.py."""
    from sensei import prompts

    return [
        PromptComponent(
            name="IDENTITY",
            current_text=prompts.IDENTITY,
            description="Agent identity and audience (AI agents, not humans)",
        ),
        PromptComponent(
            name="CONFIDENCE_LEVELS",
            current_text=prompts.CONFIDENCE_LEVELS,
            description="How to communicate confidence based on source quality",
        ),
        PromptComponent(
            name="QUERY_DECOMPOSITION",
            current_text=prompts.QUERY_DECOMPOSITION,
            description="Breaking complex queries into parts, using cache",
        ),
        PromptComponent(
            name="RESEARCH_METHODOLOGY",
            current_text=prompts.RESEARCH_METHODOLOGY,
            description="Wide-deep exploration strategy",
        ),
        PromptComponent(
            name="ENGINEERING_JUDGMENT",
            current_text=prompts.ENGINEERING_JUDGMENT,
            description="Evaluating solutions - signals and red flags",
        ),
        PromptComponent(
            name="HANDLING_AMBIGUITY",
            current_text=prompts.HANDLING_AMBIGUITY,
            description="Making and stating assumptions",
        ),
        PromptComponent(
            name="REPORTING_RESULTS",
            current_text=prompts.REPORTING_RESULTS,
            description="How to report findings with debugging context",
        ),
        PromptComponent(
            name="CITATIONS",
            current_text=prompts.CITATIONS,
            description="How to cite sources with refs and snippets",
        ),
        PromptComponent(
            name="CHOOSING_SOURCES",
            current_text=prompts.CHOOSING_SOURCES,
            description="Trust hierarchy and matching source to goal",
        ),
    ]


# =============================================================================
# 2. Variant Generation
# =============================================================================


class VariantGenerator(dspy.Signature):
    """Generate improved variants of a prompt component."""

    component_name: str = dspy.InputField(desc="Name of the component")
    component_description: str = dspy.InputField(desc="What this component does")
    current_text: str = dspy.InputField(desc="Current component text")
    failure_examples: str = dspy.InputField(desc="Examples where the agent failed")

    improved_variant: str = dspy.OutputField(desc="Improved version of the component")
    reasoning: str = dspy.OutputField(desc="Why this variant should improve performance")


def generate_variants(
    component: PromptComponent,
    failure_examples: list[str],
    num_variants: int = 5,
) -> list[str]:
    """Generate N improved variants of a component."""
    generator = dspy.ChainOfThought(VariantGenerator)

    variants = [component.current_text]  # Always include current as baseline

    failure_text = "\n---\n".join(failure_examples) if failure_examples else "No failure examples available"

    for _ in range(num_variants - 1):
        result = generator(
            component_name=component.name,
            component_description=component.description,
            current_text=component.current_text,
            failure_examples=failure_text,
        )
        variants.append(result.improved_variant)

    return variants


# =============================================================================
# 3. Prompt Assembly
# =============================================================================


def build_prompt_from_components(
    components: dict[str, str],
    context: str = "full_mcp",
) -> str:
    """Build a full prompt from component texts.

    This mirrors the logic in prompts.build_prompt() but uses provided
    component texts instead of the module constants.
    """
    # Core components that are always included
    parts = [
        components.get("IDENTITY", ""),
        components.get("CONFIDENCE_LEVELS", ""),
    ]

    # Query decomposition for coordinators
    if context in ("full_mcp", "claude_code"):
        parts.append(components.get("QUERY_DECOMPOSITION", ""))

    # Core methodology
    parts.extend(
        [
            components.get("RESEARCH_METHODOLOGY", ""),
            components.get("ENGINEERING_JUDGMENT", ""),
            components.get("HANDLING_AMBIGUITY", ""),
            components.get("REPORTING_RESULTS", ""),
            components.get("CITATIONS", ""),
        ]
    )

    # Sources
    parts.append(components.get("CHOOSING_SOURCES", ""))

    return "\n".join(p for p in parts if p)


# =============================================================================
# 4. Agent Runner
# =============================================================================


async def run_agent_with_prompt(query: str, system_prompt: str) -> str:
    """Run the agent with a custom system prompt."""
    agent = create_agent(
        include_spawn=True,
        include_exec_plan=False,
        system_prompt_override=system_prompt,  # Would need to add this param
    )

    deps = await build_deps(query, parent_ctx=None)
    result = await agent.run(query, deps=deps)
    return result.output


def run_agent_sync(query: str, system_prompt: str) -> str:
    """Synchronous wrapper for DSPy compatibility."""
    return asyncio.run(run_agent_with_prompt(query, system_prompt))


# =============================================================================
# 5. Evaluation
# =============================================================================


@dataclass
class EvaluationResult:
    """Result of evaluating a prompt variant."""

    variant_index: int
    variant_text: str
    scores: dict[str, float]  # evaluator_name -> score
    total_score: float


def evaluate_variant(
    query: str,
    system_prompt: str,
    evaluators: list[Callable],
) -> dict[str, float]:
    """Run all evaluators on a single query+prompt combination."""
    output = run_agent_sync(query, system_prompt)

    scores = {}
    for evaluator in evaluators:
        # Each evaluator returns a 0-1 score
        # Higher is better
        score = evaluator(query, output)
        scores[evaluator.__name__] = score

    return scores


def evaluate_all_variants(
    queries: list[str],
    variants: list[str],
    frozen_components: dict[str, str],
    component_name: str,
    evaluators: list[Callable],
) -> list[EvaluationResult]:
    """Evaluate all variants of a component across all queries."""
    results = []

    for i, variant_text in enumerate(variants):
        # Build full prompt with this variant
        components = frozen_components.copy()
        components[component_name] = variant_text
        system_prompt = build_prompt_from_components(components)

        # Evaluate on all queries
        all_scores: dict[str, list[float]] = {}
        for query in queries:
            scores = evaluate_variant(query, system_prompt, evaluators)
            for name, score in scores.items():
                all_scores.setdefault(name, []).append(score)

        # Average scores across queries
        avg_scores = {name: sum(s) / len(s) for name, s in all_scores.items()}
        total_score = sum(avg_scores.values()) / len(avg_scores)

        results.append(
            EvaluationResult(
                variant_index=i,
                variant_text=variant_text,
                scores=avg_scores,
                total_score=total_score,
            )
        )

    return results


# =============================================================================
# 6. Sequential Optimizer
# =============================================================================


@dataclass
class OptimizationResult:
    """Result of optimizing all components."""

    original_components: dict[str, str]
    optimized_components: dict[str, str]
    component_improvements: dict[str, float]  # component -> score delta
    total_improvement: float


def optimize_sequentially(
    training_queries: list[str],
    failure_examples: dict[str, list[str]],  # component_name -> failure examples
    evaluators: list[Callable],
    num_variants: int = 5,
    components_to_optimize: list[str] | None = None,
) -> OptimizationResult:
    """Optimize prompt components one at a time.

    Args:
        training_queries: Queries to evaluate on
        failure_examples: Per-component examples of failures
        evaluators: List of evaluator functions (query, output) -> float
        num_variants: Number of variants to generate per component
        components_to_optimize: Which components to optimize (None = all)

    Returns:
        OptimizationResult with original and optimized components
    """
    # Load current components
    all_components = load_components()

    # Build initial frozen state
    frozen: dict[str, str] = {c.name: c.current_text for c in all_components}
    original: dict[str, str] = frozen.copy()

    # Track improvements
    improvements: dict[str, float] = {}

    # Which components to optimize
    if components_to_optimize is None:
        components_to_optimize = [c.name for c in all_components]

    # Optimize each component sequentially
    for component in all_components:
        if component.name not in components_to_optimize:
            continue

        print(f"\n{'=' * 60}")
        print(f"Optimizing: {component.name}")
        print(f"{'=' * 60}")

        # Generate variants
        failures = failure_examples.get(component.name, [])
        variants = generate_variants(component, failures, num_variants)

        print(f"Generated {len(variants)} variants")

        # Evaluate all variants
        results = evaluate_all_variants(
            queries=training_queries,
            variants=variants,
            frozen_components=frozen,
            component_name=component.name,
            evaluators=evaluators,
        )

        # Find best variant
        best = max(results, key=lambda r: r.total_score)
        baseline = results[0]  # First variant is always the current text

        improvement = best.total_score - baseline.total_score
        improvements[component.name] = improvement

        print(f"Baseline score: {baseline.total_score:.3f}")
        print(f"Best score: {best.total_score:.3f}")
        print(f"Improvement: {improvement:+.3f}")

        # Freeze the best variant
        frozen[component.name] = best.variant_text

        if best.variant_index != 0:
            print(f"✓ Adopted new variant (index {best.variant_index})")
        else:
            print("→ Kept original (no improvement found)")

    return OptimizationResult(
        original_components=original,
        optimized_components=frozen,
        component_improvements=improvements,
        total_improvement=sum(improvements.values()),
    )


# =============================================================================
# 7. MVP Evaluators (LLM-as-Judge)
# =============================================================================

# These are the 3 MVP evaluators from the design doc.
# They use DSPy signatures to run LLM-as-judge evaluation.


class ToolSelectionJudge(dspy.Signature):
    """Evaluate whether the agent used appropriate tools for the query."""

    query: str = dspy.InputField(desc="The user's query")
    agent_output: str = dspy.InputField(desc="The agent's response including tool calls")

    used_appropriate_tools: bool = dspy.OutputField(desc="Did agent use the right tools?")
    missed_tools: str = dspy.OutputField(desc="Tools that should have been used but weren't")
    unnecessary_tools: str = dspy.OutputField(desc="Tools used but not needed")
    reasoning: str = dspy.OutputField(desc="Explanation of the evaluation")
    score: float = dspy.OutputField(desc="Score from 0.0 (poor) to 1.0 (perfect)")


class HallucinationJudge(dspy.Signature):
    """Evaluate whether the agent made claims not supported by tool results."""

    query: str = dspy.InputField(desc="The user's query")
    agent_output: str = dspy.InputField(desc="The agent's response")

    has_hallucinations: bool = dspy.OutputField(desc="Does response contain unsupported claims?")
    hallucinated_claims: str = dspy.OutputField(desc="Claims not supported by evidence")
    severity: str = dspy.OutputField(desc="minor, major, or critical")
    reasoning: str = dspy.OutputField(desc="Explanation of the evaluation")
    score: float = dspy.OutputField(desc="Score from 0.0 (severe hallucination) to 1.0 (no hallucination)")


class CompletenessJudge(dspy.Signature):
    """Evaluate whether the agent addressed all parts of the query."""

    query: str = dspy.InputField(desc="The user's query")
    agent_output: str = dspy.InputField(desc="The agent's response")

    fully_addressed: bool = dspy.OutputField(desc="Did agent address all parts?")
    missed_aspects: str = dspy.OutputField(desc="Parts of the query not addressed")
    reasoning: str = dspy.OutputField(desc="Explanation of the evaluation")
    score: float = dspy.OutputField(desc="Score from 0.0 (incomplete) to 1.0 (complete)")


def create_evaluator(judge_signature: type) -> Callable[[str, str], float]:
    """Create an evaluator function from a DSPy judge signature."""
    judge = dspy.ChainOfThought(judge_signature)

    def evaluator(query: str, output: str) -> float:
        result = judge(query=query, agent_output=output)
        # Clamp score to [0, 1]
        return max(0.0, min(1.0, float(result.score)))

    evaluator.__name__ = judge_signature.__name__
    return evaluator


def get_mvp_evaluators() -> list[Callable[[str, str], float]]:
    """Get the 3 MVP evaluators from the design doc."""
    return [
        create_evaluator(ToolSelectionJudge),
        create_evaluator(HallucinationJudge),
        create_evaluator(CompletenessJudge),
    ]


# =============================================================================
# 8. CLI Entry Point
# =============================================================================


def main():
    """Run the sequential optimizer."""
    import argparse
    import json

    parser = argparse.ArgumentParser(description="Optimize Sensei prompts")
    parser.add_argument("--queries", type=str, required=True, help="JSON file with training queries")
    parser.add_argument("--failures", type=str, help="JSON file with failure examples per component")
    parser.add_argument("--variants", type=int, default=5, help="Variants per component")
    parser.add_argument("--components", type=str, nargs="*", help="Components to optimize (default: all)")
    parser.add_argument("--output", type=str, default="optimized_prompts.json", help="Output file")
    parser.add_argument("--model", type=str, default="anthropic/claude-sonnet-4-20250514", help="DSPy LM")

    args = parser.parse_args()

    # Configure DSPy
    dspy.configure(lm=dspy.LM(args.model))

    # Load training queries
    with open(args.queries) as f:
        training_queries = json.load(f)

    # Load failure examples (optional)
    failure_examples: dict[str, list[str]] = {}
    if args.failures:
        with open(args.failures) as f:
            failure_examples = json.load(f)

    # Get MVP evaluators
    evaluators = get_mvp_evaluators()

    print(f"Loaded {len(training_queries)} training queries")
    print(f"Using {len(evaluators)} evaluators: {[e.__name__ for e in evaluators]}")

    # Run optimization
    result = optimize_sequentially(
        training_queries=training_queries,
        failure_examples=failure_examples,
        evaluators=evaluators,
        num_variants=args.variants,
        components_to_optimize=args.components,
    )

    # Save results
    output_data = {
        "original": result.original_components,
        "optimized": result.optimized_components,
        "improvements": result.component_improvements,
        "total_improvement": result.total_improvement,
    }

    with open(args.output, "w") as f:
        json.dump(output_data, f, indent=2)

    print(f"\n{'=' * 60}")
    print("Optimization complete!")
    print(f"Total improvement: {result.total_improvement:+.3f}")
    print("\nPer-component improvements:")
    for comp, delta in sorted(result.component_improvements.items(), key=lambda x: -x[1]):
        print(f"  {comp}: {delta:+.3f}")
    print(f"\nResults saved to: {args.output}")


if __name__ == "__main__":
    main()


# =============================================================================
# Integration Notes
# =============================================================================
#
# To make this work with the actual sensei agent, we need:
#
# 1. Add `system_prompt_override` parameter to `create_agent()` in agent.py:
#
#    def create_agent(
#        include_spawn: bool = True,
#        include_exec_plan: bool = True,
#        system_prompt_override: str | None = None,  # ADD THIS
#    ) -> Agent:
#        system_prompt = system_prompt_override or build_prompt("full_mcp")
#        ...
#
# 2. The evaluators need access to the full message history, not just the
#    final output. We'd need to capture tool calls and intermediate steps.
#    Options:
#    a) Return structured result from agent (messages, tool_calls, output)
#    b) Use Logfire spans to reconstruct the trace
#    c) Wrap the agent to capture messages
#
# 3. Training queries should come from the rating system - queries where
#    agents gave low ratings are prime candidates for the training set.
#
# 4. Failure examples per component can be generated by:
#    a) Running the current evaluators on low-rated queries
#    b) Mapping evaluator failures to relevant components:
#       - ToolSelectionJudge failures → CHOOSING_SOURCES, AVAILABLE_TOOLS
#       - HallucinationJudge failures → CONFIDENCE_LEVELS, CITATIONS
#       - CompletenessJudge failures → QUERY_DECOMPOSITION, REPORTING_RESULTS
#
# Example usage:
#
#   python -m docs.plans.2025-12-18-dspy-sequential-optimizer \
#       --queries training_queries.json \
#       --failures failure_examples.json \
#       --variants 5 \
#       --components IDENTITY CONFIDENCE_LEVELS \
#       --output optimized_prompts.json
#
