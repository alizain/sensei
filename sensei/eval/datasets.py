"""Dataset helpers for Sensei eval runs (pydantic-evals)."""

from pathlib import Path
from typing import Any

from pydantic_evals import Dataset

from sensei.types import BrokenInvariant

DATASETS_DIR = Path(__file__).parent / "datasets"


def dataset_paths(datasets_dir: Path | None = None) -> list[Path]:
    """List all eval dataset YAML files."""
    dir_path = datasets_dir or DATASETS_DIR
    if not dir_path.exists():
        raise BrokenInvariant(f"Eval datasets directory not found: {dir_path}")
    return sorted(p for p in dir_path.glob("*.yaml") if not p.name.startswith("_"))


def load_dataset(name: str, datasets_dir: Path | None = None) -> Dataset[str, str, Any]:
    """Load a single dataset from `sensei/eval/datasets/` by filename stem."""
    dir_path = datasets_dir or DATASETS_DIR
    path = dir_path / f"{name}.yaml"
    if not path.exists():
        raise BrokenInvariant(f"Eval dataset not found: {path}")
    return Dataset[str, str, Any].from_file(path)


def load_datasets(datasets_dir: Path | None = None) -> list[Dataset[str, str, Any]]:
    """Load all available datasets from `sensei/eval/datasets/`."""
    return [Dataset[str, str, Any].from_file(p) for p in dataset_paths(datasets_dir)]
