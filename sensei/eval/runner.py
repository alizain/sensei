"""Standalone pydantic-evals runner for Sensei."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Iterable

from pydantic_evals import Dataset
from pydantic_evals.reporting import EvaluationReportAdapter

from sensei.eval.datasets import load_dataset, load_datasets
from sensei.eval.task import run_agent
from sensei.types import BrokenInvariant


def _filter_cases_by_tag(dataset: Dataset, tag: str) -> Dataset:
    cases = []
    for case in dataset.cases:
        metadata = case.metadata if isinstance(case.metadata, dict) else {}
        tags = metadata.get("tags", [])
        if tag in tags:
            cases.append(case)

    return Dataset(
        name=dataset.name,
        cases=cases,
        evaluators=dataset.evaluators,
    )


def _write_reports_json(path: Path, reports: list[Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(reports, indent=2) + "\n")


def _parse_args(argv: Iterable[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="python -m sensei.eval", description="Run Sensei eval datasets.")
    parser.add_argument("--dataset", help="Dataset name (e.g., fastapi, react). Defaults to all datasets.")
    parser.add_argument("--filter", dest="filter_tag", help="Filter cases by metadata.tags value.")
    parser.add_argument("--output", type=Path, help="Write JSON report to this file.")
    return parser.parse_args(list(argv) if argv is not None else None)


def main(argv: Iterable[str] | None = None) -> int:
    args = _parse_args(argv)

    if args.dataset:
        datasets = [load_dataset(args.dataset)]
    else:
        datasets = load_datasets()

    if args.filter_tag:
        datasets = [_filter_cases_by_tag(d, args.filter_tag) for d in datasets]
        datasets = [d for d in datasets if d.cases]
        if not datasets:
            raise BrokenInvariant(f"No cases matched tag: {args.filter_tag}")

    reports = []
    for dataset in datasets:
        report = dataset.evaluate_sync(
            run_agent,
            max_concurrency=1,
            progress=True,
        )
        report.print(include_input=False, include_output=False, include_durations=True)
        reports.append(EvaluationReportAdapter.dump_python(report))

    if args.output:
        _write_reports_json(args.output, reports if len(reports) != 1 else reports[0])

    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
