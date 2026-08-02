"""Keep a chart's embedded mini-workbook in sync with its chart XML cache.

Every chart in these decks has a matching embeddings/*.xlsx that PowerPoint
shows if the user clicks "Edit Data" — if only the chart's own cache is
updated and this file is left stale, the deck LOOKS right until someone
opens the data editor. This module updates the embedded sheet's ticker
column (by shared-string index) and weight column to match a new
ticker/weight order exactly.
"""

from __future__ import annotations

import io
import zipfile

from lxml import etree

NS = {"s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}

SHEET_PART = "xl/worksheets/sheet1.xml"
STRINGS_PART = "xl/sharedStrings.xml"


def _shared_string_index(shared_strings_root, text: str) -> int:
    for idx, si in enumerate(shared_strings_root.findall("s:si", NS)):
        t = si.find("s:t", NS)
        if t is not None and t.text == text:
            return idx
    raise ValueError(
        f"{text!r} not found in sharedStrings.xml — this patcher only "
        "reweights existing tickers, it never adds new shared strings. "
        "If this is a genuine new holding, that's a composition change, "
        "not a reweight, and needs manual handling."
    )


def update_embedded_workbook(xlsx_bytes: bytes, new_tickers: list[str],
                              new_weights: list[float]) -> bytes:
    """new_tickers must already exist in the workbook's sharedStrings.xml
    (i.e. be the same ticker set as before, just possibly reordered) —
    raises otherwise rather than silently inventing a new string entry."""
    zin = zipfile.ZipFile(io.BytesIO(xlsx_bytes))
    parts = {name: zin.read(name) for name in zin.namelist()}

    strings_root = etree.fromstring(parts[STRINGS_PART])
    ticker_to_idx = {t: _shared_string_index(strings_root, t) for t in new_tickers}

    sheet_root = etree.fromstring(parts[SHEET_PART])
    rows = sheet_root.findall(".//s:sheetData/s:row", NS)
    # Row 1 is the header ("Weight" label cell); data starts at row 2.
    data_rows = [r for r in rows if int(r.get("r")) >= 2]

    if len(data_rows) != len(new_tickers):
        raise ValueError(
            f"Embedded sheet has {len(data_rows)} data rows, got "
            f"{len(new_tickers)} new tickers — holding-count changes aren't "
            "supported by this patcher."
        )

    for row, ticker, weight in zip(data_rows, new_tickers, new_weights):
        cells = row.findall("s:c", NS)
        a_cell, b_cell = cells[0], cells[1]  # column A (ticker), column B (weight)
        a_cell.find("s:v", NS).text = str(ticker_to_idx[ticker])
        b_cell.find("s:v", NS).text = repr(float(weight))

    parts[SHEET_PART] = etree.tostring(
        sheet_root, xml_declaration=True, encoding="UTF-8", standalone=True)

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zout:
        for name, data in parts.items():
            zout.writestr(name, data)
    return buf.getvalue()
