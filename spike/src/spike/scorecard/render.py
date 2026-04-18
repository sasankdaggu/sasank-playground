from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path

from spike.models import FieldPresence
from spike.scorecard.analyze import quality_tier


def render_csv_matrix(rows: list[FieldPresence], out: Path) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["field", "retailer", "present", "sample_count", "presence_ratio"])
        for r in rows:
            w.writerow([
                r.field_name, r.retailer_slug, r.present_count,
                r.sample_count, f"{r.presence_ratio:.2f}",
            ])


def render_scorecard_md(rows: list[FieldPresence], out: Path) -> None:
    by_field: dict[str, list[FieldPresence]] = defaultdict(list)
    for r in rows:
        by_field[r.field_name].append(r)
    out.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = ["# Field-Quality Scorecard", ""]
    for field in sorted(by_field):
        lines.append(f"## {field}")
        lines.append("")
        lines.append("| Retailer | Present | Samples | Ratio | Tier |")
        lines.append("|---|---:|---:|---:|---|")
        for r in sorted(by_field[field], key=lambda x: -x.presence_ratio):
            lines.append(
                f"| {r.retailer_slug} | {r.present_count} | {r.sample_count} | "
                f"{r.presence_ratio:.2f} | {quality_tier(r.presence_ratio)} |"
            )
        lines.append("")
    out.write_text("\n".join(lines))
