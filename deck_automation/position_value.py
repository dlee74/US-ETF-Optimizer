"""Current $ value and unrealized gain/loss per ticker, computed from static
verified cost basis (deck_automation/clients/wiley_group_private.py) and a
live price pulled via the same scoring.metrics.fetch_prices() used
everywhere else in this repo.

Matches the exact formula each TD statement itself uses:
    Unrealized Gain/Loss = Market Value - Book Cost
    Market Value = Price * Quantity

No live custody/brokerage access is needed — a purchase is a discrete,
infrequent event, so shares/book_cost are static config, verified once
against a real statement (see wiley_group_private.py.example) and updated
by hand on the rare occasion a real trade executes.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import pandas as pd  # noqa: E402

from scoring.metrics import fetch_prices  # noqa: E402


@dataclass
class PositionValue:
    ticker: str
    shares: float
    book_cost: float
    price: float
    market_value: float
    unrealized_gain: float


def current_values(cost_basis: dict, ticker_map: dict) -> dict[str, PositionValue]:
    """cost_basis: {bare_ticker: {"shares", "book_cost", ...}} — e.g.
    client_config["cost_basis"]. ticker_map: bare -> yfinance-fetchable,
    e.g. client_config["ticker_map"]. One fetch_prices() call for all
    tickers in cost_basis."""
    bare_tickers = list(cost_basis)
    fetchable = [ticker_map[t] for t in bare_tickers]

    prices_df = fetch_prices(fetchable, period="5d")
    if prices_df.empty:
        raise ValueError("fetch_prices returned no data for any ticker")

    results = {}
    for ticker in bare_tickers:
        fetchable_ticker = ticker_map[ticker]
        if fetchable_ticker not in prices_df.columns:
            raise ValueError(f"No current price available for {ticker} ({fetchable_ticker})")
        # Each ticker's OWN most recent non-NaN close, not the DataFrame's
        # last row — thinner ETFs can lag a day behind more liquid ones in
        # having their latest bar populated, so requiring one shared "most
        # recent" date across all tickers fails on those lagging names.
        col = prices_df[fetchable_ticker].dropna()
        if col.empty:
            raise ValueError(f"No current price available for {ticker} ({fetchable_ticker})")
        price = float(col.iloc[-1])
        shares = cost_basis[ticker]["shares"]
        book_cost = cost_basis[ticker]["book_cost"]
        market_value = price * shares
        results[ticker] = PositionValue(
            ticker=ticker,
            shares=shares,
            book_cost=book_cost,
            price=price,
            market_value=market_value,
            unrealized_gain=market_value - book_cost,
        )
    return results
