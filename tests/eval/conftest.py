"""Pytest fixtures for pydantic-evals regression tests."""

import logfire
import pytest
from pydantic_evals import Dataset

from sensei.eval.datasets import dataset_paths


@pytest.fixture(scope="session", autouse=True)
def _configure_logfire() -> None:
    logfire.configure(send_to_logfire=False)


@pytest.fixture(scope="session")
def eval_datasets() -> list[Dataset]:
    datasets: list[Dataset] = []
    for path in dataset_paths():
        datasets.append(Dataset.from_file(path))
    return datasets
