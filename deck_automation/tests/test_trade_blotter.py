"""Exact-match tests against real, independently-verified numbers from the
reference document (Clients/DJ/2026/July 24/Wiley_Trade_Blotter_one_page.docx)
— see plan Phase 3. These hit the network (yfinance), matching this repo's
existing convention of not mocking price data — prices can drift by
fractions of a cent as data providers revise history, so a wider absolute
tolerance is used here than a bit-exact `==` would allow, but still tight
enough that a genuinely wrong formula would fail loudly.
"""

from deck_automation.rebalance import TradeInstruction
from deck_automation.trade_blotter import (
    TBD, build_blotter_row, limit_price_full_exit, limit_price_last_close, recent_range,
)

TOL = 0.01  # $0.01 — real formulas reproduce this closely; a wrong one won't


def test_qhy_full_exit_limit_price():
    price, pct = limit_price_full_exit("QHY.TO", "2026-02-06", "2026-07-24")
    assert abs(price - 80.79) < TOL
    assert abs(pct - 0.6724) < 0.001


def test_zcs_last_close_limit_price():
    price = limit_price_last_close("ZCS.TO", "2026-07-24")
    assert abs(price - 13.94) < TOL


def test_qhy_recent_range():
    min_p, min_d, max_p, max_d = recent_range("QHY.TO", "2026-07-24")
    assert abs(min_p - 79.46) < TOL
    assert min_d == "Mar 27"
    assert abs(max_p - 83.62) < TOL
    assert max_d == "Jan 19"


def test_zcs_recent_range():
    min_p, min_d, max_p, max_d = recent_range("ZCS.TO", "2026-07-24")
    assert abs(min_p - 13.88) < TOL
    assert min_d == "Mar 20"
    assert abs(max_p - 14.21) < TOL
    assert max_d == "Oct 28"


def test_limit_price_override_takes_precedence_over_method():
    """An advisor-supplied price is more authoritative than any formula --
    passing both must use the override, not silently compute instead."""
    trade = TradeInstruction(ticker="RPF", action="SELL", dollar_amount=1000.0,
                              shares_delta=-40.0, current_market_value=5000.0,
                              target_market_value=4000.0, new_weight=0.15)
    row = build_blotter_row(trade, "RPF.TO", "2026-08-04",
                             limit_price_method="full_exit",  # would raise: no purchase_date given
                             limit_price_override="26.00")
    assert row["Limit Price"] == "$26.00"


def test_order_type_defaults_to_day():
    trade = TradeInstruction(ticker="RPF", action="SELL", dollar_amount=1000.0,
                              shares_delta=-40.0, current_market_value=5000.0,
                              target_market_value=4000.0, new_weight=0.15)
    row = build_blotter_row(trade, "RPF.TO", "2026-08-04")
    assert row["Order Type"] == "Day"
    assert row["Limit Price"] == TBD


def test_order_type_override():
    trade = TradeInstruction(ticker="QHY", action="SELL", dollar_amount=1000.0,
                              shares_delta=-40.0, current_market_value=5000.0,
                              target_market_value=0.0, new_weight=0.0)
    row = build_blotter_row(trade, "QHY.TO", "2026-08-04",
                             limit_price_override="80.70", order_type="Standing (1 month)")
    assert row["Order Type"] == "Standing (1 month)"
