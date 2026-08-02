"""Orchestrates opening a .pptx, applying patches, and re-zipping.

Only the "refresh" mode patches the deck itself (the metrics table's Value
column) — "propose" mode produces a standalone comparison and never touches
the .pptx (see produce_update.py). chart_xml.py / embedded_workbook.py exist
as tested utilities for a possible future extension (patching current-weight
display, which would need real custody/brokerage data this pipeline doesn't
have) but are not called from here.
"""

from __future__ import annotations

import zipfile

from pptx import Presentation

from .table_text import update_metrics_table


def _slide_part_name(pptx_path: str, slide_number: int) -> str:
    """slide_number is 1-indexed, matching how client configs talk about
    slides. Resolved via python-pptx (read-only) rather than assumed to
    equal slideN.xml — PowerPoint doesn't guarantee that correspondence."""
    prs = Presentation(pptx_path)
    return str(prs.slides[slide_number - 1].part.partname).lstrip("/")


def patch_metrics_refresh(pptx_path: str, out_path: str, client_config: dict,
                           refreshed: list) -> None:
    """refreshed: list of optimize.OptimizedPortfolio, one per entry in
    client_config["portfolios"] in the same order, already computed via
    optimize.refresh_metrics_at_target(). Writes a new file at out_path —
    never overwrites pptx_path."""
    if len(refreshed) != len(client_config["portfolios"]):
        raise ValueError(
            f"Got {len(refreshed)} refreshed results for "
            f"{len(client_config['portfolios'])} configured portfolios"
        )

    zin = zipfile.ZipFile(pptx_path)
    parts = {name: zin.read(name) for name in zin.namelist()}
    infos = {info.filename: info for info in zin.infolist()}

    for portfolio, result in zip(client_config["portfolios"], refreshed):
        part_name = _slide_part_name(pptx_path, portfolio["metrics_slide"])
        parts[part_name] = update_metrics_table(parts[part_name], result.metrics)

    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as zout:
        for name, data in parts.items():
            # preserve original per-entry compression type where we have it
            compress_type = infos[name].compress_type if name in infos else zipfile.ZIP_DEFLATED
            zout.writestr(name, data, compress_type=compress_type)
