"""Two independent things this pipeline can do with a portfolio block's
holdings, matching the two CLI modes:

  refresh_metrics_at_target() — the routine cycle. The deck's metrics table
    is computed AT THE STATIC TARGET weights (confirmed from its own
    subtitle text, e.g. "...at its 30/30/15/25 target allocation"), not the
    current drifted weights. This just re-evaluates that same fixed target
    allocation with fresh price data — no optimization happens.

  optimize_holdings() — the occasional strategic-review case. Finds NEW
  optimal weights among the same tickers via the SLSQP core-k optimizer
  (main_portfolio.evaluate_basket(), "SLSQP" result) — matches the one-off
  "Re-Optimized Allocation" work done by hand previously. Note
  evaluate_custom_weights() alone does NOT do this: its own docstring says
  "no optimization", it only evaluates a fixed allocation (confirmed
  empirically: feeding it the current weights back returns ~the same
  weights, just normalized) — it's step 2 below, not step 1.

Both funnel through evaluate_custom_weights() as their last step to get
metrics + chart figures in a consistent shape (both paths use the same
get_portfolio_metrics() under the hood).
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from build_portfolios import evaluate_custom_weights  # noqa: E402
from main_portfolio import evaluate_basket  # noqa: E402


@dataclass
class OptimizedPortfolio:
    name: str
    tickers: list[str]        # bare tickers, ranked by descending weight
    weights: list[float]
    metrics: "pandas.DataFrame"   # noqa: F821 — same shape as evaluate_custom_weights()
    figs: dict
    dropped: list[str]
    window: tuple


def _evaluate(name: str, fetchable_weights: dict, client_config: dict) -> OptimizedPortfolio:
    """Shared tail: evaluate_custom_weights() + map fetchable tickers back
    to bare deck tickers."""
    ticker_map = client_config["ticker_map"]
    result = evaluate_custom_weights(
        fetchable_weights,
        period=client_config["period"],
        rf=client_config["rf"],
    )
    if result["dropped"]:
        raise ValueError(
            f"{name}: evaluate_custom_weights dropped {result['dropped']} — "
            "investigate before patching the deck."
        )

    reverse_map = {v: k for k, v in ticker_map.items()}
    weights_df = result["weights"]
    bare_tickers = [reverse_map[t] for t in weights_df["ETF"]]
    weights = list(weights_df["Weight"])

    return OptimizedPortfolio(
        name=name,
        tickers=bare_tickers,
        weights=weights,
        metrics=result["metrics"],
        figs=result["figs"],
        dropped=result["dropped"],
        window=result["window"],
    )


def refresh_metrics_at_target(holdings, client_config) -> OptimizedPortfolio:
    """holdings: an extract.PortfolioHoldings with a parsed target_weights.
    Re-evaluates that SAME static target allocation with fresh price data —
    this is what the deck's metrics table is supposed to reflect."""
    if holdings.target_weights is None:
        raise ValueError(
            f"{holdings.name}: no 'Target Weights: ...' text found on this "
            "deck's slide — can't refresh metrics without a target allocation."
        )
    ticker_map = client_config["ticker_map"]
    fetchable = {ticker_map[t]: w for t, w in holdings.target_weights.items()}
    return _evaluate(holdings.name, fetchable, client_config)


def optimize_holdings(holdings, client_config) -> OptimizedPortfolio:
    """holdings: an extract.PortfolioHoldings. Finds NEW re-optimized weights
    among the same tickers it currently holds, using fresh price history."""
    ticker_map = client_config["ticker_map"]
    fetchable_tickers = [ticker_map[t] for t in holdings.tickers]

    basket_results = evaluate_basket(
        fetchable_tickers,
        client_config["optimizer_profile"],
        period=client_config["period"],
        rf=client_config["rf"],
        w_min=client_config["w_min"],
        max_etf_weight=client_config["max_etf_weight"],
    )
    slsqp = basket_results.get("SLSQP")
    if slsqp is None or "error" in slsqp:
        raise ValueError(
            f"{holdings.name}: SLSQP core-k optimization failed: "
            f"{slsqp.get('error') if slsqp else 'no SLSQP result returned'}"
        )
    new_weights = dict(zip(slsqp["weights"]["ETF"], slsqp["weights"]["Weight"]))
    return _evaluate(holdings.name, new_weights, client_config)
