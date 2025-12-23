# Sensei Evaluation & Improvement Loop

**Status:** Living document - design in progress
**Last updated:** 2025-12-18

## Overview

A three-layer system for evaluating sensei query quality and improving prompts based on patterns in failures.

## Goals

1. **Catch quality issues** - LLM-as-judge evaluates query runs against defined failure modes
2. **Improve prompts** - DSPy optimization loop uses evaluation signals to improve prompts
3. **Validate improvements** - Before/after comparison ensures changes actually help
4. **Reusable evaluators** - Same evaluators work with pydantic-evals, DSPy, and future production sampling

## Non-Goals (Phase 1)

- Production sampling (deferred to Phase 2)
- Real-time retry during sessions
- Automatic prompt deployment

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         On-Demand Trigger                        │
│                    (Human selects queries to evaluate)           │
└─────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────┐
│                      Layer 1: Evaluator                          │
│                                                                   │
│  Input: Query + message history + agent rating                   │
│  Engine: pydantic-evals with LLM-as-judge                        │
│  Output: Structured issue reports per query                      │
│                                                                   │
│  Failure modes detected:                                         │
│  - tool_selection: Didn't use obvious tool                       │
│  - tool_parameters: Wrong library name, missed version           │
│  - source_quality: Used outdated docs when newer available       │
│  - synthesis_quality: Answer doesn't match tool results          │
│  - completeness: Missed part of the question                     │
│  - hallucination: Claims something tools didn't support          │
└─────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────┐
│                      Layer 2: Optimizer                          │
│                                                                   │
│  Input: Collection of issue reports                              │
│  Engine: DSPy (BootstrapFewShot, MIPRO, etc.)                   │
│  Output: Prompt improvement suggestions                          │
│                                                                   │
│  Process:                                                        │
│  - Identify patterns across failures                             │
│  - Generate candidate prompt modifications                       │
│  - Human reviews suggestions before applying                     │
└─────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────┐
│                      Layer 3: Validator                          │
│                                                                   │
│  Input: Old prompt + New prompt + Test queries                   │
│  Engine: pydantic-evals (same evaluators as Layer 1)            │
│  Output: Before/after comparison metrics                         │
│                                                                   │
│  Process:                                                        │
│  - Run same queries with old prompt                              │
│  - Run same queries with new prompt                              │
│  - Compare evaluation scores                                     │
│  - Report improvement/regression per failure mode                │
└─────────────────────────────────────────────────────────────────┘
```

## Feedback Flow

```
Calling Agent (Claude Code, etc.)
         │
         │ Uses sensei
         ▼
    ┌─────────┐
    │ Sensei  │ ──► Response + Query ID
    └─────────┘
         │
         │ Agent provides rating (when appropriate)
         ▼
    ┌─────────┐
    │ /rate   │ ──► Stored with full message history
    └─────────┘
         │
         │ Human triggers evaluation (on-demand)
         ▼
    ┌─────────┐
    │ Eval    │ ──► Structured issue reports
    └─────────┘
```

## Failure Modes (Layer 1 Evaluators)

Each evaluator is an LLM-as-judge that reviews the message history.

### 1. Tool Selection (`tool_selection`)

**Question:** Did the agent use the right tools for this query?

**Signals:**
- Query mentions a library → should have used Context7
- Query asks for code examples → should have used Scout/Grep
- Query is about current events/releases → should have used Tavily

**Output:**
```python
class ToolSelectionIssue(BaseModel):
    missed_tools: list[str]  # Tools that should have been used
    unnecessary_tools: list[str]  # Tools used but not needed
    reasoning: str
```

### 2. Tool Parameters (`tool_parameters`)

**Question:** Were tools called with correct parameters?

**Signals:**
- Library name typos or wrong casing
- Version not passed when query specified version
- Search queries too broad or too narrow

**Output:**
```python
class ToolParameterIssue(BaseModel):
    tool_name: str
    parameter: str
    actual_value: str
    suggested_value: str
    reasoning: str
```

### 3. Source Quality (`source_quality`)

**Question:** Did the agent use the best available sources?

**Signals:**
- Used old Stack Overflow when official docs available
- Cited deprecated APIs
- Missed newer version documentation

**Output:**
```python
class SourceQualityIssue(BaseModel):
    source_used: str
    better_source: str
    why_better: str
```

### 4. Synthesis Quality (`synthesis_quality`)

**Question:** Does the answer accurately reflect what the tools returned?

**Signals:**
- Answer contradicts tool output
- Key information from tools omitted
- Misinterpretation of code examples

**Output:**
```python
class SynthesisIssue(BaseModel):
    claim_in_answer: str
    tool_output_reality: str
    discrepancy: str
```

### 5. Completeness (`completeness`)

**Question:** Did the answer address all parts of the query?

**Signals:**
- Multi-part questions with missing parts
- Follow-up context ignored
- Edge cases not addressed

**Output:**
```python
class CompletenessIssue(BaseModel):
    missed_aspects: list[str]
    reasoning: str
```

### 6. Hallucination (`hallucination`)

**Question:** Did the agent claim things not supported by tool results?

**Signals:**
- API methods that don't exist
- Configuration options not in docs
- Version features not actually available

**Output:**
```python
class HallucinationIssue(BaseModel):
    hallucinated_claim: str
    what_tools_actually_said: str
    severity: Literal["minor", "major", "critical"]
```

---

## Prompt-Derived Evaluators

These evaluators check whether the agent followed the methodology defined in `sensei/prompts.py`.

### 7. Agent Format (`agent_format`)

**Prompt section:** IDENTITY

**Instruction:** "Your audience is other AI agents, not humans... Structured and parseable over conversational... No pleasantries, greetings, or filler"

**Question:** Is the response formatted for agent consumption?

**Signals:**
- Contains greetings ("Hello!", "I'd be happy to help")
- Conversational filler ("Let me think about this...")
- Unstructured prose when structure would help
- Missing code blocks or formatting

**Output:**
```python
class AgentFormatIssue(BaseModel):
    problem_type: Literal["greeting", "filler", "unstructured", "missing_formatting"]
    example_text: str
    suggested_fix: str
```

### 8. Confidence Communication (`confidence_communication`)

**Prompt section:** CONFIDENCE_LEVELS

**Instruction:** "Always communicate your confidence level based on source quality"

**Question:** Did the agent communicate confidence appropriately?

**Signals:**
- High confidence claim from low-trust source (blog cited as authoritative)
- Low confidence hedging on official docs
- No confidence indication at all
- Mismatch between stated confidence and source type

**Output:**
```python
class ConfidenceIssue(BaseModel):
    claim: str
    source_type: Literal["official_docs", "source_code", "github", "community", "training_data"]
    stated_confidence: Literal["high", "medium", "low", "uncertain", "none"]
    expected_confidence: Literal["high", "medium", "low", "uncertain"]
    reasoning: str
```

### 9. Query Decomposition (`query_decomposition`)

**Prompt section:** QUERY_DECOMPOSITION

**Instruction:** "Complex queries often combine multiple independent topics — recognizing this unlocks powerful strategies"

**Question:** Did the agent decompose complex queries appropriately?

**Signals:**
- Multi-part question answered monolithically
- No cache search before research
- Missed opportunity for parallel subagent research
- Independent topics not identified

**Output:**
```python
class DecompositionIssue(BaseModel):
    query_complexity: Literal["simple", "compound", "complex"]
    identified_parts: list[str]
    missed_parts: list[str]
    cache_searched: bool
    subagents_used: bool
    should_have_used_subagents: bool
    reasoning: str
```

### 10. Research Depth (`research_depth`)

**Prompt section:** RESEARCH_METHODOLOGY

**Instruction:** "Iterative Wide-Deep Exploration... Go wide first, go deep on promising paths, zoom out when needed"

**Question:** Did the agent explore sufficiently before settling on an answer?

**Signals:**
- Single query phrasing when multiple would help
- Latched onto first result without verification
- Didn't explore adjacent topics
- No deep investigation of promising paths

**Output:**
```python
class ResearchDepthIssue(BaseModel):
    query_phrasings_tried: int
    sources_consulted: int
    depth_of_investigation: Literal["shallow", "moderate", "deep"]
    missed_exploration: list[str]  # Topics/phrasings that should have been tried
    premature_conclusion: bool
    reasoning: str
```

### 11. Solution Evaluation (`solution_evaluation`)

**Prompt section:** ENGINEERING_JUDGMENT

**Instruction:** "When you find multiple approaches, apply engineering judgment — don't just pick the first one that works"

**Question:** Did the agent evaluate multiple approaches with engineering judgment?

**Signals:**
- Only one approach considered
- No evaluation against signals (authority, alignment, simplicity, recency)
- Red flags ignored (hacky, workaround, fighting the framework)
- First solution taken without comparison

**Output:**
```python
class SolutionEvaluationIssue(BaseModel):
    approaches_considered: int
    signals_evaluated: list[Literal["authority", "alignment", "simplicity", "recency"]]
    red_flags_present: list[str]
    red_flags_acknowledged: bool
    reasoning: str
```

### 12. Ambiguity Handling (`ambiguity_handling`)

**Prompt section:** HANDLING_AMBIGUITY

**Instruction:** "If a question is under-specified, make reasonable assumptions and state them explicitly"

**Question:** Did the agent handle ambiguity appropriately?

**Signals:**
- Made assumptions but didn't state them
- Stated assumptions that don't match the answer
- Should have asked for clarification but didn't
- Gave overly generic answer to avoid assumptions

**Output:**
```python
class AmbiguityIssue(BaseModel):
    query_ambiguity: Literal["clear", "slightly_ambiguous", "highly_ambiguous"]
    assumptions_made: list[str]
    assumptions_stated: list[str]
    should_have_clarified: bool
    reasoning: str
```

### 13. Reporting Quality (`reporting_quality`)

**Prompt section:** REPORTING_RESULTS

**Instruction:** "Saying 'I couldn't find a good answer' is not a failure... When you do find an answer, include enough context that the caller can troubleshoot"

**Question:** Did the agent report results with appropriate context?

**Signals:**
- Said "not found" without explaining what was searched
- Found answer but no debugging context
- No explanation of underlying model/concept
- Missing edge cases or assumptions

**Output:**
```python
class ReportingIssue(BaseModel):
    result_type: Literal["found", "not_found", "partial"]
    search_explained: bool  # For "not found" - did it say what was searched?
    debugging_context: bool  # For "found" - can caller troubleshoot?
    underlying_concepts: bool  # Did it explain the "why"?
    edge_cases_noted: bool
    reasoning: str
```

### 14. Citation Quality (`citation_quality`)

**Prompt section:** CITATIONS

**Instruction:** "Cite sources with exact references and snippets... Use `<source>` tags to cite sources inline"

**Question:** Did the agent cite sources properly?

**Signals:**
- Key claims without citations
- Citations without snippets
- Broken or vague refs
- Over-citation (every sentence) or under-citation

**Output:**
```python
class CitationIssue(BaseModel):
    uncited_claims: list[str]
    citations_without_snippets: int
    citations_with_snippets: int
    vague_refs: list[str]  # e.g., "the docs say" without ref
    citation_balance: Literal["under", "appropriate", "over"]
    reasoning: str
```

### 15. Source Selection (`source_selection`)

**Prompt section:** CHOOSING_SOURCES

**Instruction:** "Consider two dimensions: trust and goal... Exhaust trusted sources for that goal before falling back to less trusted ones"

**Question:** Did the agent follow the trust hierarchy and match source to goal?

**Signals:**
- Used blog post when official docs available
- Source type doesn't match goal (API reference from Stack Overflow)
- Didn't try official docs before community sources
- Training data used when tools should have been

**Output:**
```python
class SourceSelectionIssue(BaseModel):
    goal_type: Literal["api_reference", "conceptual", "usage_patterns", "troubleshooting", "migration"]
    sources_used: list[str]
    trust_levels_used: list[Literal["official_docs", "source_code", "official_examples", "community", "training_data"]]
    better_sources_available: list[str]
    trust_hierarchy_violated: bool
    reasoning: str
```

---

## Evaluator Summary

| # | Evaluator | Category | Checks |
|---|-----------|----------|--------|
| 1 | `tool_selection` | Tool Usage | Right tools for query |
| 2 | `tool_parameters` | Tool Usage | Correct parameters |
| 3 | `source_quality` | Sources | Best available sources |
| 4 | `synthesis_quality` | Output | Answer matches tools |
| 5 | `completeness` | Output | All parts addressed |
| 6 | `hallucination` | Output | No unsupported claims |
| 7 | `agent_format` | Format | Structured for agents |
| 8 | `confidence_communication` | Methodology | Confidence stated correctly |
| 9 | `query_decomposition` | Methodology | Complex queries decomposed |
| 10 | `research_depth` | Methodology | Wide-deep exploration |
| 11 | `solution_evaluation` | Methodology | Multiple approaches evaluated |
| 12 | `ambiguity_handling` | Methodology | Assumptions stated |
| 13 | `reporting_quality` | Output | Debugging context included |
| 14 | `citation_quality` | Output | Proper source citations |
| 15 | `source_selection` | Sources | Trust hierarchy followed |

## Integration Points

### pydantic-evals

Evaluators implemented as `LLMJudge` evaluators:

```python
from pydantic_evals import Case, Dataset
from pydantic_evals.evaluators import LLMJudge

tool_selection_judge = LLMJudge(
    rubric="...",
    model="...",
)

dataset = Dataset(cases=[...])
report = dataset.evaluate_sync(run_agent, evaluators=[tool_selection_judge])
```

### DSPy

Evaluators wrapped as DSPy metrics:

```python
import dspy

def tool_selection_metric(example, prediction, trace=None):
    # Run our LLM-as-judge evaluator
    issues = evaluate_tool_selection(example.query, prediction.messages)
    # Return score (higher = better)
    return 1.0 if not issues else 0.0

# Use in DSPy optimizer
optimizer = dspy.BootstrapFewShot(metric=tool_selection_metric)
optimized_program = optimizer.compile(program, trainset=trainset)
```

### Logfire (existing)

Message history already captured via OpenTelemetry. Evaluators can access spans.

## Data Model

### Evaluation Report

```python
class EvaluationReport(BaseModel):
    query_id: str
    evaluated_at: datetime

    # Input context
    query: str
    messages: list[dict]  # Full message history
    agent_rating: Rating | None

    # Tool Usage issues
    tool_selection_issues: list[ToolSelectionIssue]
    tool_parameter_issues: list[ToolParameterIssue]

    # Source issues
    source_quality_issues: list[SourceQualityIssue]
    source_selection_issues: list[SourceSelectionIssue]

    # Output issues
    synthesis_issues: list[SynthesisIssue]
    completeness_issues: list[CompletenessIssue]
    hallucination_issues: list[HallucinationIssue]
    reporting_issues: list[ReportingIssue]
    citation_issues: list[CitationIssue]

    # Format issues
    agent_format_issues: list[AgentFormatIssue]

    # Methodology issues
    confidence_issues: list[ConfidenceIssue]
    decomposition_issues: list[DecompositionIssue]
    research_depth_issues: list[ResearchDepthIssue]
    solution_evaluation_issues: list[SolutionEvaluationIssue]
    ambiguity_issues: list[AmbiguityIssue]

    # Summary
    overall_score: float  # 0-1
    category_scores: dict[str, float]  # Per-category scores
    primary_failure_mode: str | None
    failure_modes: list[str]  # All failure modes detected
```

### Optimization Suggestion

```python
class PromptSuggestion(BaseModel):
    failure_pattern: str  # e.g., "Agents often miss version-specific Context7 calls"
    affected_queries: list[str]  # Query IDs showing this pattern
    current_prompt_section: str  # Which part of prompt to modify
    suggested_change: str
    expected_improvement: str
```

## Phase 2: Production Sampling (Deferred)

Future work to add continuous evaluation:

```
Logfire traces
      │
      ▼
┌─────────────┐
│  Sampler    │  ◄── Configurable % (e.g., 10%)
└─────────────┘      Signal-based (negative ratings)
      │
      ▼
Same evaluators from Layer 1
      │
      ▼
Alerting on degradation
```

## DSPy Integration

### Approach: Sequential Component Optimization

We preserve the modular prompt structure from `prompts.py` by optimizing one component at a time. This gives us:
- **Attribution**: Know exactly which component improved
- **Linear search space**: `components × variants` instead of exponential
- **Preservation**: Keep the modular structure, don't collapse to monolithic string

**Algorithm:**
```
for each component in [IDENTITY, CONFIDENCE_LEVELS, ...]:
    1. Generate N variants of this component (using LLM + failure examples)
    2. Build full prompts = (frozen components) + (each variant)
    3. Evaluate all variants on training queries
    4. Pick best variant, freeze it
    5. Move to next component
```

**Architecture:**
```
┌─────────────────────────────────────────────────────────────────┐
│                    Variant Generator (DSPy)                      │
│                                                                   │
│  Input: component name, current text, failure examples           │
│  Output: N improved variants of the component                    │
└─────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────┐
│                     Prompt Assembly                              │
│                                                                   │
│  Compose: frozen_components + variant → full system prompt       │
│  Mirrors logic from prompts.build_prompt()                       │
└─────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Agent Evaluation                              │
│                                                                   │
│  Run agent on training queries with composed prompt              │
│  Score with LLM-as-judge evaluators                              │
└─────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Best Variant Selection                        │
│                                                                   │
│  Pick variant with highest average score                         │
│  Freeze this component, move to next                             │
└─────────────────────────────────────────────────────────────────┘
```

**Code:** See `docs/plans/2025-12-18-dspy-sequential-optimizer.py`

### Evaluator → Component Mapping

When evaluators detect failures, we map them to relevant components for targeted improvement:

| Evaluator | Relevant Components |
|-----------|---------------------|
| `tool_selection` | CHOOSING_SOURCES, AVAILABLE_TOOLS |
| `hallucination` | CONFIDENCE_LEVELS, CITATIONS |
| `completeness` | QUERY_DECOMPOSITION, REPORTING_RESULTS |
| `confidence_communication` | CONFIDENCE_LEVELS |
| `research_depth` | RESEARCH_METHODOLOGY |
| `solution_evaluation` | ENGINEERING_JUDGMENT |
| `ambiguity_handling` | HANDLING_AMBIGUITY |
| `citation_quality` | CITATIONS |
| `source_selection` | CHOOSING_SOURCES |

This mapping lets us prioritize which components to optimize based on which evaluators are failing most.

---

## MVP Scope

### What's In

1. **3 evaluators** (highest signal):
   - `tool_selection` - Did it use the right tools?
   - `hallucination` - Did it make stuff up?
   - `completeness` - Did it answer the whole question?

2. **DSPy wrapper module** wrapping PydanticAI agent

3. **CLI for on-demand evaluation:**
   ```bash
   # Evaluate specific queries
   python -m sensei.eval.judge --query-id <id>

   # Run optimization
   python -m sensei.eval.optimize --num-examples 20

   # Validate improvement
   python -m sensei.eval.validate --old-prompt prompts.py --new-prompt optimized.txt
   ```

4. **Simple storage:** Evaluation reports as JSON files (no new DB tables)

### What's Out (Phase 2+)

- All 15 evaluators (start with 3, add incrementally)
- Production sampling
- Automatic prompt deployment
- Fancy dashboards

---

## Open Questions

1. **Evaluator model:** Which model for LLM-as-judge? (Suggest: same as sensei for consistency)
2. **Dataset curation:** How do we select queries for the test set? (Suggest: start with queries that have low ratings)
3. **Prompt diffing:** How do we present before/after prompt changes for review?

## Next Steps

- [ ] Implement 3 MVP evaluators (tool_selection, hallucination, completeness)
- [ ] Build SenseiWrapper DSPy module
- [ ] Create CLI for evaluation and optimization
- [ ] Curate initial dataset from existing queries with ratings
- [ ] Run first optimization cycle and review results
