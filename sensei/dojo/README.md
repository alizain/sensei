# Sensei Dojo

DSPy-based prompt optimization using user feedback ratings.

## Objective

Use the [DSPy framework](https://github.com/stanfordnlp/dspy) with MIPROv2 optimizer to automatically improve Sensei's prompts based on collected user feedback.

## How It Works

1. **Input**: User feedback ratings from the `ratings` table
   - Filter to 4-5 star examples (correctness, relevance, usefulness)
   - Need 50-100 diverse, high-quality examples

2. **Optimizer**: MIPROv2 (Multi-Instruction Proposal Optimizer v2)
   - Joint optimization of instructions + few-shot examples
   - Generates multiple candidate prompts and evaluates them

3. **Output**:
   - Optimized system prompts for the Sensei agent
   - Curated few-shot examples that improve response quality

## Integration Plan

```python
from sensei.dojo import optimize_prompts

# Run optimization when sufficient new feedback has accumulated
result = await optimize_prompts(
    min_examples=50,
    min_rating=4,
)

# Result contains optimized prompts ready for production
print(result.optimized_system_prompt)
print(result.few_shot_examples)
```

## Why DSPy?

- **Data-driven**: Uses actual user feedback, not intuition
- **Automatic**: No manual prompt engineering required
- **Measurable**: Can track improvement via held-out validation set
- **Iterative**: Re-run as more feedback accumulates

## Status

**Stub** - Implementation planned after Tome is complete.

## References

- [DSPy Documentation](https://dspy.ai)
- [MIPROv2 Paper](https://arxiv.org/abs/2406.11695)
