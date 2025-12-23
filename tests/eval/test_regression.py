"""Regression tests for Sensei response quality (pydantic-evals)."""

from pathlib import Path

import pytest
from pydantic_evals import Dataset

from sensei.eval.datasets import dataset_paths
from sensei.eval.task import run_agent


@pytest.mark.parametrize("dataset_path", dataset_paths(), ids=lambda p: p.stem)
def test_response_quality(dataset_path: Path) -> None:
    dataset: Dataset[str, str] = Dataset.from_file(dataset_path)
    report = dataset.evaluate_sync(
        run_agent,
        max_concurrency=1,
        progress=False,
    )
    report.print(include_input=False, include_output=False, include_durations=False)

    assert not report.failures
    assert all(isinstance(c.output, str) and c.output.strip() for c in report.cases)
