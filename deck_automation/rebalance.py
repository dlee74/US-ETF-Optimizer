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
