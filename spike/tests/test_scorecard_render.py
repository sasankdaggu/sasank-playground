from __future__ import annotations

from pathlib import Path

from spike.models import FieldPresence
from spike.scorecard.render import render_csv_matrix, render_scorecard_md


def test_render_csv_contains_header_and_rows(tmp_path: Path) -> None:
    rows = [
        FieldPresence(field_name="current_price", retailer_slug="nykaa",
                      present_count=7, sample_count=8),
        FieldPresence(field_name="ingredients", retailer_slug="nykaa",
                      present_count=2, sample_count=8),
    ]
    out = tmp_path / "matrix.csv"
    render_csv_matrix(rows, out)
    lines = out.read_text().splitlines()
    assert lines[0] == "field,retailer,present,sample_count,presence_ratio"
    assert any("ingredients,nykaa,2,8,0.25" in ln for ln in lines)


def test_render_scorecard_md_groups_by_field(tmp_path: Path) -> None:
    rows = [
        FieldPresence(field_name="current_price", retailer_slug="nykaa",
                      present_count=8, sample_count=8),
        FieldPresence(field_name="current_price", retailer_slug="minimalist",
                      present_count=8, sample_count=8),
        FieldPresence(field_name="ingredients", retailer_slug="nykaa",
                      present_count=2, sample_count=8),
        FieldPresence(field_name="ingredients", retailer_slug="minimalist",
                      present_count=0, sample_count=8),
    ]
    out = tmp_path / "scorecard.md"
    render_scorecard_md(rows, out)
    text = out.read_text()
    assert "## current_price" in text
    assert "## ingredients" in text
    assert "reliable" in text
    assert "absent" in text or "unreliable" in text
