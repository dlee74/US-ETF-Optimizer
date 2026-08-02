"""Patch the metrics table's Value column (slide 6/7's "Metric"/"Value"
table) with freshly computed values.

The metrics DataFrame from evaluate_custom_weights() already stores
pre-formatted display strings in its "Value" column (e.g. "11.62%", "1.41")
— matched 1:1 against the table's own "Metric" row labels — so this just
copies that string straight into the matching cell's text run. Only the
Value cell's <a:t> text changes; formatting (rPr, alignment, row height,
extLst row IDs) is untouched.

Only 1 run per cell exists in every table inspected in this deck — a
multi-run cell (e.g. from manual mid-cell formatting) would silently only
update the first run, so this raises loudly instead if a cell doesn't have
exactly one run, rather than guessing which run holds "the" value.
"""

from __future__ import annotations

from lxml import etree

NS = {"a": "http://schemas.openxmlformats.org/drawingml/2006/main"}

# The deck displays a friendlier label than the metrics DataFrame's own index
# for this one row; deck label -> DataFrame label.
LABEL_ALIASES = {
    "Avg Pairwise Correlation": "Avg Pairwise Corr",
}


def _cell_text_run(tc):
    runs = tc.findall(".//a:p/a:r", NS)
    if len(runs) != 1:
        raise ValueError(
            f"Expected exactly 1 text run in table cell, found {len(runs)} — "
            "refusing to guess which one holds the value."
        )
    return runs[0].find("a:t", NS)


def update_metrics_table(slide_xml_bytes: bytes, metrics_df) -> bytes:
    """metrics_df: the "metrics" DataFrame from evaluate_custom_weights()
    (index = metric label, column "Value" = pre-formatted display string).

    The deck is allowed to display a SUBSET of metrics_df's rows (it does —
    12 computed vs. 10 shown) under possibly-aliased labels (LABEL_ALIASES).
    What must NOT happen is a table row whose label can't be resolved to any
    metric at all — that means the deck's structure changed and this
    function no longer knows what to write there."""
    root = etree.fromstring(slide_xml_bytes)
    rows = root.findall(".//a:tbl/a:tr", NS)
    if not rows:
        raise ValueError("No table found on this slide")

    updated = 0
    for row in rows[1:]:  # skip header row ("Metric" / "Value")
        cells = row.findall("a:tc", NS)
        if len(cells) != 2:
            continue
        label_run = _cell_text_run(cells[0])
        label = label_run.text.strip() if label_run.text else ""
        metric_key = LABEL_ALIASES.get(label, label)
        if metric_key not in metrics_df.index:
            raise ValueError(
                f"Table row {label!r} doesn't match any metric in "
                f"{list(metrics_df.index)} (or LABEL_ALIASES) — deck "
                "structure may have changed."
            )
        value_t = _cell_text_run(cells[1])
        value_t.text = str(metrics_df.loc[metric_key, "Value"])
        updated += 1

    if updated == 0:
        raise ValueError("Found a table but updated 0 rows — check table structure.")

    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)
