"""Limit-price and recent-range computation for the trade-blotter one-pager.

Deliberately uses RAW (unadjusted) closing prices, not the dividend-adjusted
closes scoring.metrics.fetch_prices() returns for the rest of this repo
(correct there, for return/optimization math) — confirmed empirically that
adjusted closes do NOT reproduce the real document's numbers, raw ones do
exactly (see plan Phase 3).

Two limit-price conventions are confirmed exact against real examples:
  - full-exit SELL: the price level the security traded at-or-above on
    ~67% of days since the original purchase date (QHY: $80.79, 67.24%).
  - tight-range BUY: simply the last raw close as of the "as of" date
    (ZCS: $13.94, exact).
A third case (partial-trim SELL/BUY) has NO confirmed formula — callers
must not invent one; build_blotter_row() returns None for limit_price
unless the caller explicitly names a confirmed method.
"""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import yfinance as yf  # noqa: E402
from utils.logger import logger  # noqa: E402

TBD = "TBD — advisor to set"


def fetch_raw_prices(symbols: list, start: str = None, end: str = None) -> pd.DataFrame:
    """Mirrors scoring.metrics.fetch_prices()'s shape, but with
    auto_adjust=False — raw traded closes, not dividend-adjusted.

    `end` is treated as INCLUSIVE (matching how every date in this module
    is talked about — "as of July 24" means July 24's close is in range),
    unlike yfinance's own `end`, which is exclusive."""
    inclusive_end = (pd.Timestamp(end) + pd.Timedelta(days=1)).strftime("%Y-%m-%d") if end else None
    prices = pd.DataFrame()
    for ticker in symbols:
        try:
            logger.info(f"Fetching raw prices for {ticker}")
            hist = yf.Ticker(ticker).history(start=start, end=inclusive_end, auto_adjust=False)
            if hist.empty:
                logger.warning(f"No historical data for {ticker}, skipping")
                continue
            hist = hist[["Close"]].rename(columns={"Close": ticker})
            prices = pd.concat([prices, hist], axis=1)
        except Exception as e:
            logger.error(f"Error fetching raw prices for {ticker}: {e}")
            continue
    return prices


def limit_price_full_exit(ticker: str, purchase_date: str, as_of_date: str,
                           target_pct: float = 0.67) -> tuple[float, float]:
    """Price level where the security traded at-or-above it on
    `target_pct` of raw-close trading days since purchase_date, EXCLUDING
    as_of_date itself — you can't know today's close when setting today's
    order, so the percentile is calibrated on all history strictly before
    it (confirmed: including as_of_date shifts the exact-match result).
    Returns (price, actual_pct achieved)."""
    day_before = (pd.Timestamp(as_of_date) - pd.Timedelta(days=1)).strftime("%Y-%m-%d")
    prices = fetch_raw_prices([ticker], start=purchase_date, end=day_before)
    if prices.empty or ticker not in prices.columns:
        raise ValueError(f"No raw price data for {ticker} from {purchase_date} to {as_of_date}")
    s = prices[ticker].dropna()
    threshold = float(np.percentile(s, (1 - target_pct) * 100))
    actual_pct = float((s >= threshold).mean())
    return threshold, actual_pct


def limit_price_last_close(ticker: str, as_of_date: str) -> float:
    """Simply the last raw close on or before as_of_date."""
    prices = fetch_raw_prices([ticker], end=as_of_date)
    if prices.empty or ticker not in prices.columns:
        raise ValueError(f"No raw price data for {ticker} through {as_of_date}")
    s = prices[ticker].dropna()
    return float(s.iloc[-1])


def recent_range(ticker: str, as_of_date: str, months: int = 9) -> tuple[float, str, float, str]:
    """Min/max raw close over a trailing `months`-month window ending at
    as_of_date, with the dates they occurred on."""
    start = (pd.Timestamp(as_of_date) - pd.DateOffset(months=months)).strftime("%Y-%m-%d")
    prices = fetch_raw_prices([ticker], start=start, end=as_of_date)
    if prices.empty or ticker not in prices.columns:
        raise ValueError(f"No raw price data for {ticker} in the {months}-month window ending {as_of_date}")
    s = prices[ticker].dropna()
    min_price, max_price = float(s.min()), float(s.max())
    # %-d (no leading zero) is a glibc extension, not portable to Windows'
    # strftime — build "Mon D" manually instead (see produce_update.py's
    # _default_out_subdir() for the same fix).
    def _fmt(ts):
        return f"{ts.strftime('%b')} {ts.day}"
    min_date, max_date = _fmt(s.idxmin()), _fmt(s.idxmax())
    return min_price, min_date, max_price, max_date


def build_blotter_row(trade, fetchable_ticker: str, as_of_date: str,
                       limit_price_method: str | None = None,
                       purchase_date: str | None = None) -> dict:
    """trade: a rebalance.TradeInstruction (holds the BARE display ticker,
    e.g. "HDIV"). fetchable_ticker: the yfinance-fetchable form (e.g.
    "HDIV.TO", from client_config["ticker_map"]) — trade.ticker itself is
    never passed to yfinance. limit_price_method: None (TBD), "full_exit"
    (needs purchase_date), or "last_close". Never guesses — an
    unrecognized/unsupported method raises rather than silently falling
    back to TBD, so a typo doesn't quietly produce a placeholder."""
    if limit_price_method is None:
        limit_price = TBD
    elif limit_price_method == "full_exit":
        if purchase_date is None:
            raise ValueError("full_exit method requires purchase_date")
        limit_price, _ = limit_price_full_exit(fetchable_ticker, purchase_date, as_of_date)
        limit_price = f"{limit_price:.2f}"
    elif limit_price_method == "last_close":
        limit_price = f"{limit_price_last_close(fetchable_ticker, as_of_date):.2f}"
    else:
        raise ValueError(f"Unrecognized limit_price_method {limit_price_method!r}")

    min_p, min_d, max_p, max_d = recent_range(fetchable_ticker, as_of_date)

    shares_display = (
        f"{abs(trade.shares_delta):.1f} (full position)" if trade.action == "SELL" and trade.new_weight == 0
        else f"{trade.shares_delta:+.1f}"
    )

    return {
        "Ticker": trade.ticker,
        "Action": trade.action,
        "Shares": shares_display,
        "Amount": f"${trade.dollar_amount:,.2f}",
        "Limit Price": f"${limit_price}" if limit_price != TBD else TBD,
        "Recent Range (~9 mo)": f"${min_p:.2f} ({min_d}) - ${max_p:.2f} ({max_d})",
        "New Weight": f"{trade.new_weight:.1%}",
    }
