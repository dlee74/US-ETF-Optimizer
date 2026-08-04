"""Compute the buy/sell trades needed to bring a portfolio block from its
current $ values back to a target weight allocation — the same computation
slide 9's "Rebalancing Plan" table performs by hand.

Operates on ONE portfolio block at a time (e.g. just the 4 tax_optimized
tickers' PositionValues) — pass position_value.current_values()'s result
filtered/subset to the relevant tickers, not the whole client's cost basis.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class TradeInstruction:
    ticker: str
    action: str          # "BUY" or "SELL"
    dollar_amount: float  # always positive; action indicates direction
    shares_delta: float   # signed: positive = shares added, negative = shares removed
    current_market_value: float
    target_market_value: float
    new_weight: float


def compute_trades(current_values: dict, target_weights: dict) -> list[TradeInstruction]:
    """current_values: {ticker: position_value.PositionValue}, target_weights:
    {ticker: fraction}. Both must cover exactly the same ticker set — a
    ticker present in one but not the other is a real error (a rebalance
    plan that silently ignores a holding, or targets one not actually held,
    is worse than failing loudly)."""
    if set(current_values) != set(target_weights):
        raise ValueError(
            f"current_values tickers {sorted(current_values)} != "
            f"target_weights tickers {sorted(target_weights)}"
        )

    total_value = sum(pv.market_value for pv in current_values.values())
    if total_value <= 0:
        raise ValueError(f"Total portfolio value must be positive, got {total_value}")

    trades = []
    for ticker, pv in current_values.items():
        target_value = total_value * target_weights[ticker]
        delta_dollar = target_value - pv.market_value
        shares_delta = delta_dollar / pv.price

        trades.append(TradeInstruction(
            ticker=ticker,
            action="BUY" if delta_dollar >= 0 else "SELL",
            dollar_amount=abs(delta_dollar),
            shares_delta=shares_delta,
            current_market_value=pv.market_value,
            target_market_value=target_value,
            new_weight=target_weights[ticker],
        ))
    return trades


def compute_full_exit_swap(sell_position, buy_ticker: str, buy_price: float,
                            portfolio_total_value: float) -> tuple[TradeInstruction, TradeInstruction]:
    """A standing order: dispose of sell_position entirely, then buy
    buy_ticker with the exact proceeds once that's done (matches slide 7's
    real precedent — QHY sold for $73,082.63, ZCS bought with that exact
    $73,082.63, not an independently-sized amount). Every other holding in
    the portfolio is untouched — this is NOT a full rebalance, just a
    targeted swap of one position for another.

    sell_position: a position_value.PositionValue for the ticker being
    exited. buy_price: buy_ticker's current price (it may not have an
    existing position/cost-basis entry in this portfolio at all — that's
    the point). portfolio_total_value: the WHOLE portfolio's current value
    (all holdings, not just this pair) — used only to compute the buy
    trade's resulting weight for display."""
    proceeds = sell_position.market_value

    sell_trade = TradeInstruction(
        ticker=sell_position.ticker, action="SELL", dollar_amount=proceeds,
        shares_delta=-sell_position.shares, current_market_value=sell_position.market_value,
        target_market_value=0.0, new_weight=0.0,
    )
    buy_trade = TradeInstruction(
        ticker=buy_ticker, action="BUY", dollar_amount=proceeds,
        shares_delta=proceeds / buy_price, current_market_value=0.0,
        target_market_value=proceeds, new_weight=proceeds / portfolio_total_value,
    )
    return sell_trade, buy_trade
