import io
import zipfile

from deck_automation.patch.embedded_workbook import update_embedded_workbook


def _read(fixtures_dir, name):
    return (fixtures_dir / "chart2" / name).read_bytes()


def test_reorders_shared_string_indices_to_match_new_order(fixtures_dir):
    original = _read(fixtures_dir, "embedded_workbook.xlsx")
    patched = update_embedded_workbook(original, ["ZCS", "RPF", "HDIV", "XFR"],
                                        [0.3732, 0.2466, 0.2006, 0.1797])

    z = zipfile.ZipFile(io.BytesIO(patched))
    strings_z = zipfile.ZipFile(io.BytesIO(original))  # shared strings unchanged
    from lxml import etree
    NS = {"s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}

    strings_root = etree.fromstring(strings_z.read("xl/sharedStrings.xml"))
    idx_to_ticker = {i: si.find("s:t", NS).text
                      for i, si in enumerate(strings_root.findall("s:si", NS))}

    sheet_root = etree.fromstring(z.read("xl/worksheets/sheet1.xml"))
    rows = [r for r in sheet_root.findall(".//s:sheetData/s:row", NS) if int(r.get("r")) >= 2]

    tickers, weights = [], []
    for row in rows:
        cells = row.findall("s:c", NS)
        tickers.append(idx_to_ticker[int(cells[0].find("s:v", NS).text)])
        weights.append(float(cells[1].find("s:v", NS).text))

    assert tickers == ["ZCS", "RPF", "HDIV", "XFR"]
    assert weights == [0.3732, 0.2466, 0.2006, 0.1797]


def test_raises_on_unknown_ticker(fixtures_dir):
    original = _read(fixtures_dir, "embedded_workbook.xlsx")
    try:
        update_embedded_workbook(original, ["ZCS", "RPF", "HDIV", "NOTAREALTICKER"],
                                  [0.3, 0.3, 0.3, 0.1])
        assert False, "expected ValueError"
    except ValueError as e:
        assert "NOTAREALTICKER" in str(e)


def test_raises_on_holding_count_mismatch(fixtures_dir):
    original = _read(fixtures_dir, "embedded_workbook.xlsx")
    try:
        update_embedded_workbook(original, ["ZCS", "RPF"], [0.5, 0.5])
        assert False, "expected ValueError"
    except ValueError as e:
        assert "2" in str(e)
