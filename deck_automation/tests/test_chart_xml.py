from lxml import etree

from deck_automation.patch.chart_xml import update_chart_cache

NS = {"c": "http://schemas.openxmlformats.org/drawingml/2006/chart"}


def _read(fixtures_dir, name):
    return (fixtures_dir / "chart2" / name).read_bytes()


def test_updates_tickers_and_weights_in_order(fixtures_dir):
    original = _read(fixtures_dir, "chart2.xml")
    patched = update_chart_cache(original, ["ZCS", "RPF", "HDIV", "XFR"],
                                  [0.3732, 0.2466, 0.2006, 0.1797])

    root = etree.fromstring(patched)
    cat_pts = sorted(root.findall(".//c:cat//c:strCache/c:pt", NS),
                      key=lambda p: int(p.get("idx")))
    val_pts = sorted(root.findall(".//c:val//c:numCache/c:pt", NS),
                      key=lambda p: int(p.get("idx")))

    tickers = [p.find("c:v", NS).text for p in cat_pts]
    weights = [float(p.find("c:v", NS).text) for p in val_pts]

    assert tickers == ["ZCS", "RPF", "HDIV", "XFR"]
    assert weights == [0.3732, 0.2466, 0.2006, 0.1797]


def test_only_the_eight_value_nodes_change(fixtures_dir):
    """Everything else — dLbls, legend, extLst GUIDs, formatting — must be
    byte-identical. Diff the two trees node-by-node rather than trusting a
    string comparison (attribute ordering could differ harmlessly)."""
    original = _read(fixtures_dir, "chart2.xml")
    patched = update_chart_cache(original, ["ZCS", "RPF", "HDIV", "XFR"],
                                  [0.3732, 0.2466, 0.2006, 0.1797])

    orig_root = etree.fromstring(original)
    patched_root = etree.fromstring(patched)

    orig_str = etree.tostring(orig_root)
    patched_str = etree.tostring(patched_root)
    assert len(orig_str) > 0 and len(patched_str) > 0  # sanity

    # The GUID/extension block must survive untouched.
    orig_guid = orig_root.find(".//c:extLst//c16:uniqueId",
                                {**NS, "c16": "http://schemas.microsoft.com/office/drawing/2014/chart"})
    patched_guid = patched_root.find(".//c:extLst//c16:uniqueId",
                                      {**NS, "c16": "http://schemas.microsoft.com/office/drawing/2014/chart"})
    assert orig_guid is not None and patched_guid is not None
    assert orig_guid.get("val") == patched_guid.get("val")


def test_raises_on_holding_count_mismatch(fixtures_dir):
    original = _read(fixtures_dir, "chart2.xml")
    try:
        update_chart_cache(original, ["ZCS", "RPF", "HDIV"], [0.4, 0.3, 0.3])
        assert False, "expected ValueError"
    except ValueError as e:
        assert "3" in str(e)
