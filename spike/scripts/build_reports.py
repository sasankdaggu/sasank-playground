"""Read all ParsedSamples in data/parsed/*/*.json and emit the reports."""
from __future__ import annotations

import json
from pathlib import Path

from spike.models import ParsedSample
from spike.scorecard.analyze import build_field_matrix
from spike.scorecard.render import render_csv_matrix, render_scorecard_md

SPIKE_ROOT = Path(__file__).resolve().parent.parent


def load_samples() -> list[ParsedSample]:
    parsed_dir = SPIKE_ROOT / "data" / "parsed"
    samples: list[ParsedSample] = []
    for p in parsed_dir.glob("*/*.json"):
        samples.append(ParsedSample.model_validate_json(p.read_text()))
    return samples


def main() -> None:
    samples = load_samples()
    if not samples:
        raise SystemExit("No samples found. Run scripts/run_sample_crawl.py first.")
    matrix = build_field_matrix(samples)
    reports = SPIKE_ROOT / "data" / "reports"
    render_csv_matrix(matrix, reports / "field-matrix.csv")
    render_scorecard_md(matrix, reports / "scorecard.md")
    print(f"Wrote {reports/'field-matrix.csv'} and {reports/'scorecard.md'} "
          f"({len(samples)} samples across {len({s.retailer_slug for s in samples})} retailers)")


if __name__ == "__main__":
    main()
