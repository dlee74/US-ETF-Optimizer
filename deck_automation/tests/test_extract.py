from deck_automation.extract import extract_portfolio_holdings
from deck_automation.clients.wiley_group import WILEY_GROUP


def test_matches_known_ground_truth(fixtures_dir):
    """Ground truth confirmed by direct inspection of the raw chart XML
    (ppt/charts/chart1.xml / chart2.xml) during implementation — see plan."""
    path = str(fixtures_dir / "wiley_group_july_2026.pptx")
    results = extract_portfolio_holdings(path, WILEY_GROUP)

    by_name = {r.name: r for r in results}

    cc = by_name["corporate_cash"]
    assert cc.tickers == ["CMR", "HFR", "PFL", "QHY"]
    assert cc.weights == [0.399, 0.252, 0.201, 0.148]
    assert cc.target_weights == {"CMR": 0.40, "HFR": 0.25, "PFL": 0.20, "QHY": 0.15}

    to = by_name["tax_optimized"]
    assert to.tickers == ["HDIV", "ZCS", "XFR", "RPF"]
    assert to.weights == [0.317, 0.284, 0.24, 0.16]
    assert to.target_weights == {"HDIV": 0.30, "ZCS": 0.30, "RPF": 0.15, "XFR": 0.25}


def test_chart_and_table_cross_validation_passes_on_real_deck(fixtures_dir):
    """If extraction returns without raising, chart/table agreed within
    tolerance — this test exists so a future deck edit that breaks that
    agreement fails loudly here instead of silently in production."""
    path = str(fixtures_dir / "wiley_group_july_2026.pptx")
    extract_portfolio_holdings(path, WILEY_GROUP)  # must not raise


def test_raises_on_unmapped_ticker(fixtures_dir):
    path = str(fixtures_dir / "wiley_group_july_2026.pptx")
    stripped_config = {**WILEY_GROUP, "ticker_map": {"HDIV": "HDIV.TO"}}  # missing the rest
    try:
        extract_portfolio_holdings(path, stripped_config)
        assert False, "expected ValueError"
    except ValueError as e:
        assert "ticker_map" in str(e)
