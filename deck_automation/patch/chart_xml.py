"""Surgical edit of a chartN.xml's cached category/value data.

Only the <c:v> text nodes inside <c:cat>...<c:strCache> and
<c:val>...<c:numCache> are touched — every other node (dLbls, legend,
c16:uniqueId, extLst GUIDs, formatting) is left byte-identical, preserving
the branded template's exact fidelity.
"""

from __future__ import annotations

from lxml import etree

NS = {
    "c": "http://schemas.openxmlformats.org/drawingml/2006/chart",
}


def _format_weight(w: float) -> str:
    """Match the float-repr style already used in these charts (plain
    Python repr, e.g. 0.317, 0.28399999999999997) — not a fixed decimal
    format, so re-patched files look the same "shape" as hand-edited ones."""
    return repr(float(w))


def update_chart_cache(chart_xml_bytes: bytes, new_tickers: list[str],
                        new_weights: list[float]) -> bytes:
    """new_tickers/new_weights must be the same length as the chart's
    existing <c:pt> count; raises if they don't match (refuses to grow or
    shrink the series — a genuine holding-count change is out of scope for
    this in-place refresh pipeline)."""
    root = etree.fromstring(chart_xml_bytes)

    cat_pts = root.findall(".//c:cat//c:strCache/c:pt", NS)
    val_pts = root.findall(".//c:val//c:numCache/c:pt", NS)

    if len(cat_pts) != len(new_tickers):
        raise ValueError(
            f"Chart has {len(cat_pts)} category points, got {len(new_tickers)} "
            "new tickers — holding-count changes aren't supported by this patcher."
        )
    if len(val_pts) != len(new_weights):
        raise ValueError(
            f"Chart has {len(val_pts)} value points, got {len(new_weights)} "
            "new weights."
        )

    # <c:pt idx="N"> order in the XML need not match array order in theory,
    # but in every fixture inspected idx is already 0..N-1 in document order.
    # Sort by idx explicitly rather than assuming, so this holds even if not.
    def by_idx(pts):
        return sorted(pts, key=lambda pt: int(pt.get("idx")))

    for pt, ticker in zip(by_idx(cat_pts), new_tickers):
        v = pt.find("c:v", NS)
        v.text = ticker

    for pt, weight in zip(by_idx(val_pts), new_weights):
        v = pt.find("c:v", NS)
        v.text = _format_weight(weight)

    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)
