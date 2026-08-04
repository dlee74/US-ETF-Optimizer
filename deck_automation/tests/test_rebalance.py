from deck_automation.position_value import PositionValue
from deck_automation.rebalance import (
    TradeInstruction, compute_full_exit_swap, compute_trades, round_to_board_lot,
)


def _pv(ticker, shares, price, book_cost=0.0):
    return PositionValue(ticker=ticker, shares=shares, book_cost=book_cost,
                          price=price, market_value=shares * price,
                          unrealized_gain=shares * price - book_cost)


def test_compute_trades_balances_to_zero_net_change():
    current = {
        "A": _pv("A", 100, 10),   # $1000
        "B": _pv("B", 50, 10),    # $500
    }
    target = {"A": 0.5, "B": 0.5}  # currently 66.7%/33.3%, target 50/50
    trades = compute_trades(current, target)

    by_ticker = {t.ticker: t for t in trades}
    assert by_ticker["A"].action == "SELL"
    assert by_ticker["B"].action == "BUY"
    # total portfolio value unchanged by a rebalance -- dollar amounts must
    # net to zero (what's sold from A funds what's bought in B)
    net = sum(t.dollar_amount if t.action == "BUY" else -t.dollar_amount for t in trades)
    assert abs(net) < 1e-9


def test_compute_trades_raises_on_ticker_mismatch():
    current = {"A": _pv("A", 100, 10)}
    target = {"B": 1.0}
    try:
        compute_trades(current, target)
        assert False, "expected ValueError"
    except ValueError as e:
        assert "A" in str(e) and "B" in str(e)


def test_compute_full_exit_swap_buy_matches_sell_proceeds_exactly():
    """The defining property of a standing "dispose entirely, then buy the
    replacement with those proceeds" order — matches the real reference
    document's QHY SELL $73,082.63 -> ZCS BUY $73,082.63 (identical
    amounts), not an independently-sized buy."""
    sell_position = _pv("QHY", 904.6, 80.42)  # ~$72,747.93
    portfolio_total = 500_000.0

    sell_trade, buy_trade = compute_full_exit_swap(
        sell_position, "ZCS", buy_price=13.94, portfolio_total_value=portfolio_total)

    assert sell_trade.action == "SELL"
    assert sell_trade.new_weight == 0.0
    assert sell_trade.shares_delta == -904.6

    assert buy_trade.action == "BUY"
    assert buy_trade.dollar_amount == sell_trade.dollar_amount
    assert abs(buy_trade.shares_delta - sell_trade.dollar_amount / 13.94) < 1e-9
    assert abs(buy_trade.new_weight - sell_trade.dollar_amount / portfolio_total) < 1e-9


def test_compute_full_exit_swap_other_holdings_unaffected():
    """This is a targeted swap, not a full rebalance -- the function only
    ever returns the sell/buy pair, nothing about any other ticker."""
    sell_position = _pv("QHY", 100, 80)
    sell_trade, buy_trade = compute_full_exit_swap(
        sell_position, "ZCS", buy_price=14.0, portfolio_total_value=100_000.0)
    assert {sell_trade.ticker, buy_trade.ticker} == {"QHY", "ZCS"}


def test_round_to_board_lot_floors_shares_and_recomputes_amount():
    # 5,218.9 shares at an implied price of $13.9394/sh
    trade = TradeInstruction(ticker="ZCS", action="BUY", dollar_amount=72750.81,
                              shares_delta=5218.9, current_market_value=0.0,
                              target_market_value=72750.81, new_weight=0.147)
    rounded = round_to_board_lot(trade, portfolio_total=494903.0, lot_size=100)
    assert rounded.shares_delta == 5200.0
    price_used = 72750.81 / 5218.9
    assert abs(rounded.dollar_amount - 5200 * price_used) < 1e-6
    assert abs(rounded.target_market_value - 5200 * price_used) < 1e-6


def test_round_to_board_lot_leaves_full_exit_sell_untouched():
    """A full-position exit disposes of the whole position, including any
    odd lot from DRIP reinvestment -- rounding it down would leave shares
    unsold, contradicting "dispose in entirety"."""
    trade = TradeInstruction(ticker="QHY", action="SELL", dollar_amount=72750.81,
                              shares_delta=-904.6, current_market_value=72750.81,
                              target_market_value=0.0, new_weight=0.0)
    rounded = round_to_board_lot(trade, portfolio_total=494903.0, lot_size=100)
    assert rounded is trade


def test_round_to_board_lot_raises_when_trade_too_small():
    trade = TradeInstruction(ticker="X", action="BUY", dollar_amount=500.0,
                              shares_delta=50.0, current_market_value=0.0,
                              target_market_value=500.0, new_weight=0.01)
    try:
        round_to_board_lot(trade, portfolio_total=50000.0, lot_size=100)
        assert False, "expected ValueError"
    except ValueError as e:
        assert "50.0" in str(e)
