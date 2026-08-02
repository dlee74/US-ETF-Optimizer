import re

import pandas as pd

from deck_automation.patch.table_text import update_metrics_table


def _texts(xml_bytes):
    return re.findall(r"<a:t>([^<]*)</a:t>", xml_bytes.decode())


# All 10 rows the real fixture deck actually displays (see slide7.xml) — a
# complete metrics_df, since update_metrics_table requires every deck row
# resolve to a metric (it allows metrics_df to have EXTRA rows the deck
# doesn't show, not the reverse).
_FULL_METRICS = pd.DataFrame(
    {"Value": ["99.99%", "1.00%", "1.111", "1.32", "2.12", "5.49%",
               "0.528%", "0.760%", "1.27", "0.128"]},
    index=["Annual Return", "Annual Volatility", "Sharpe Ratio", "Sortino Ratio",
           "Calmar Ratio", "Max Drawdown", "VaR 95% (daily)", "CVaR 95% (daily)",
           "Diversification Ratio", "Avg Pairwise Corr"],
)


def test_updates_matching_rows_only(fixtures_dir):
    original = (fixtures_dir / "metrics_slide7.xml").read_bytes()
    patched = update_metrics_table(original, _FULL_METRICS)
    texts = _texts(patched)

    assert "99.99%" in texts       # Annual Return, updated
    assert "1.111" in texts        # Sharpe Ratio, updated
    assert "1.32" in texts         # Sortino Ratio, unchanged from input (matches original too)
    # row labels themselves are untouched
    assert "Annual Return" in texts
    assert "Sharpe Ratio" in texts


def test_handles_label_alias(fixtures_dir):
    """Deck shows "Avg Pairwise Correlation"; metrics_df indexes it as
    "Avg Pairwise Corr" — LABEL_ALIASES must bridge that."""
    original = (fixtures_dir / "metrics_slide7.xml").read_bytes()
    metrics = _FULL_METRICS.copy()
    metrics.loc["Avg Pairwise Corr", "Value"] = "0.9999"
    patched = update_metrics_table(original, metrics)
    assert "0.9999" in _texts(patched)
    assert "Avg Pairwise Correlation" in _texts(patched)  # deck's own label untouched


def test_raises_on_unrecognized_table_row(fixtures_dir):
    """If a metrics_df doesn't cover a real row in the deck's table (here,
    "Annual Return", the first data row), that must fail loudly rather than
    silently leaving the old value in place."""
    original = (fixtures_dir / "metrics_slide7.xml").read_bytes()
    metrics = pd.DataFrame({"Value": ["1.0"]}, index=["Totally Made Up Metric"])
    try:
        update_metrics_table(original, metrics)
        assert False, "expected ValueError"
    except ValueError as e:
        assert "Annual Return" in str(e)
