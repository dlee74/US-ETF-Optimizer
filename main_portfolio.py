"""Evaluate fixed ETF baskets.

For each basket of tickers and each optimization style (SLSQP, CVXPY, HRP),
compute the allocation per ETF plus the full portfolio metrics.

Run:  python main_portfolio.py

Note on method choice: a basket is only ~4 names, but the profile-level full
SLSQP / CVXPY runs enforce an HHI cap (~0.2) that forces >=5 effective names —
so they're infeasible on 4 ETFs. The correct analog for a concentrated k-ETF
sleeve is the core-k optimizer (same objective, no HHI cap), which is what a
4-ETF basket actually is. HRP has no such constraint and allocates directly.
"""
from pathlib import Path

import numpy as np
import pandas as pd

from scoring.metrics import fetch_prices, returns_matrix
from Optimizer_Class.optimizer2 import portfolio_optimizer, shrink_covariance
from Optimizer_Class.optimizer_weights import OPTIMIZER_CONFIG
from Optimizer_Class.hrp_optimization import hrp_allocate
from Optimizer_Class.get_portfolio_metrics import get_portfolio_metrics


BASE_DIR = Path(__file__).resolve().parent
csv_path = BASE_DIR / "data_sourcing" / "US_Final_ETF_Data.csv"

# Fixed baskets. The profile name (key) selects the optimizer config — SLSQP
# objective weights and CVXPY risk aversion — applied when allocating the basket.
# NOTE: "FRLN" has no Yahoo price data (delisted/invalid) — it's FLRN, the SPDR
# Bloomberg Investment Grade Floating Rate ETF. Metadata for any ticker not in
# the CSV is fetched from yfinance, so CSV membership is optional.
feb_conservative = ["ICSH", "FLRN", "PULS", "MINT"]
feb_enhanced     = ["FLRN", "PULS", "ICSH", "SJNK"]
feb_strategic    = ["PULS", "FLRN", "SJNK", "SPHY"]

jul_conservative = ["SHV", "BIL", "ICSH", "JPST"]
jul_enhanced = ["JAAA", "FLDR", "ICSH", "MINT"]
july_strategic = ["JAAA", "JBBB", "FLDR", "FLOT"]

FEB_BASKETS = {
    "conservative": feb_conservative,
    "enhanced":     feb_enhanced,
    "strategic":    feb_strategic,
}

JUL_BASKETS = {
    "conservative": jul_conservative,
    "enhanced":     jul_enhanced,
    "strategic":    july_strategic,
}


def fetch_etf_metadata(ticker):
    """Pull YIELD / ER / AUM from yfinance for a ticker not in the CSV.

    Returned in the CSV's conventions so downstream code is unchanged:
      YIELD : decimal fraction (0.0457 = 4.57%)
      ER    : percent          (0.15  = 0.15%, later divided by 100)
      AUM   : dollars
    Any field Yahoo doesn't supply falls back to a neutral default.
    """
    import yfinance as yf
    try:
        info = yf.Ticker(ticker).info
    except Exception:
        info = {}

    y = info.get("yield") or info.get("dividendYield") or info.get("trailingAnnualDividendYield")
    if y is None:
        y = 0.04                 # default to the yield floor so it isn't penalized
    elif y > 1:                  # some yfinance fields report % (4.57) not 0.0457
        y = y / 100

    ner = info.get("netExpenseRatio")          # already a percent (0.15 = 0.15%)
    arer = info.get("annualReportExpenseRatio")  # a decimal (0.0015 = 0.15%)
    if ner is not None:
        er = ner
    elif arer is not None:
        er = arer * 100
    else:
        er = 0.20                # typical ETF expense, 0.20%

    aum = info.get("totalAssets") or 1e9
    return {"Symbol": ticker, "YIELD": float(y), "ER": float(er), "AUM": float(aum)}


def _basket_metadata(survivors, csv_df):
    """Build a YIELD/ER/AUM frame for the surviving tickers, using the CSV where
    available and yfinance for anything that isn't in it."""
    cols = ["Symbol", "YIELD", "ER", "AUM"]
    rows, from_yf = [], []
    for t in survivors:
        hit = csv_df[csv_df["Symbol"] == t]
        if len(hit):
            rows.append(hit.iloc[0][cols])
        else:
            rows.append(pd.Series(fetch_etf_metadata(t)))
            from_yf.append(t)
    if from_yf:
        print(f"  [info] metadata pulled from yfinance (not in CSV): {from_yf}")
    return pd.DataFrame(rows)[cols].reset_index(drop=True)


def _hrp_weights_df(returns_df):
    """HRP allocation over every name in the basket as an ETF/Weight frame."""
    hrp_w = hrp_allocate(shrink_covariance(returns_df), method="ward", plot=False)
    return (
        hrp_w.rename("Weight")
        .rename_axis("ETF")
        .reset_index()
        .sort_values("Weight", ascending=False)
        .reset_index(drop=True)
    )


def _load_returns(tickers, period):
    """Fetch prices for every ticker and return (returns_df, dropped). Returns
    are over the COMMON overlapping window of the surviving tickers."""
    price_df = fetch_prices(tickers, period)
    returns_df = (
        returns_matrix(price_df)
        .replace([np.inf, -np.inf], np.nan)
        .dropna(axis=1)
    )
    dropped = [t for t in tickers if t not in returns_df.columns]
    if dropped:
        print(f"  [warn] no usable price history, dropped: {dropped}")
    if not len(returns_df.index):
        raise ValueError("no overlapping price history across the tickers")
    idx = returns_df.index
    print(f"  [window] {idx[0].date()} -> {idx[-1].date()}  "
          f"({len(idx)} trading days, {len(idx)/252:.1f}y)")
    return returns_df, dropped


def evaluate_weights(weights, period="5y", rf=0.04, label="portfolio",
                     normalize=True):
    """Metrics for an EXPLICIT allocation — e.g. the weights your boss handed
    you — with NO optimization.

    weights   : {ticker: weight}. Weights need not sum to 1 (normalized by default).
    rf        : risk-free rate for Sharpe/Sortino (set 0 for a raw Sharpe).
    Returns {"weights": DataFrame, "metrics": DataFrame}.
    """
    print(f"\nEvaluating explicit weights: {label} >>>>>>>>>>")
    returns_df, _ = _load_returns(list(weights), period)

    w = pd.Series({t: float(weights[t]) for t in returns_df.columns})
    if normalize and w.sum() != 0:
        w = w / w.sum()
    weights_df = (
        w.rename("Weight").rename_axis("ETF").reset_index()
        .sort_values("Weight", ascending=False).reset_index(drop=True)
    )
    corr = returns_df.corr()
    res = {"weights": weights_df,
           "metrics": get_portfolio_metrics(weights_df, returns_df, corr,
                                            risk_free_rate=rf)}
    print_basket_report(f"{label} (rf={rf:.0%})", list(weights), {"GIVEN": res})
    return res


def evaluate_basket(tickers, profile, period="5y", rf=0.04,
                    yield_floor=0.04, max_etf_weight=0.40, w_min=0.05):
    csv_df = pd.read_csv(csv_path)

    # Fetch prices for EVERY requested ticker (not just CSV members) so basket
    # membership in the dataset is irrelevant. Drop any ticker with no/gappy
    # history — those simply have no Yahoo data (e.g. a delisted/typo symbol).
    returns_df, _ = _load_returns(tickers, period)
    k = len(returns_df.columns)
    if k < 2:
        raise ValueError(
            f"Need >=2 ETFs with clean price history; got {list(returns_df.columns)}"
        )

    # Metadata (YIELD/ER/AUM) from the CSV where present, yfinance otherwise.
    rows = _basket_metadata(list(returns_df.columns), csv_df)

    yield_df   = rows.set_index("Symbol")["YIELD"]
    expense_df = rows.set_index("Symbol")["ER"] / 100
    corr = returns_df.corr()

    optimizer = portfolio_optimizer(
        returns_df, OPTIMIZER_CONFIG, yield_df, expense_df, rows,
        yield_floor=yield_floor, max_etf_weight=max_etf_weight,
    )

    def scored(weights_df):
        return {"weights": weights_df,
                "metrics": get_portfolio_metrics(weights_df, returns_df, corr,
                                                 risk_free_rate=rf)}

    results = {}

    # SLSQP — core-k over all k names (same blended-score objective, no HHI cap)
    try:
        w_df, _ = optimizer.run_slsqp_core_k(
            profile, k=k, w_min=w_min, max_etf_weight=max_etf_weight)
        results["SLSQP"] = scored(w_df)
    except Exception as e:
        results["SLSQP"] = {"error": str(e)}

    # CVXPY — cardinality MIQP (needs SCIP/Gurobi/Mosek; skipped if none installed)
    try:
        w_df, _ = optimizer.run_cvxpy_cardinality(
            profile, k=k, w_min=w_min, max_etf_weight=max_etf_weight)
        results["CVXPY"] = scored(w_df)
    except Exception as e:
        results["CVXPY"] = {"error": str(e)}

    # HRP — clusters + inverse-variance, no constraints
    try:
        results["HRP"] = scored(_hrp_weights_df(returns_df))
    except Exception as e:
        results["HRP"] = {"error": str(e)}

    return results


def print_basket_report(profile, tickers, results):
    """Pretty-print allocations + metrics for one basket."""
    print("\n" + "=" * 72)
    print(f"BASKET: {profile.upper()}   |   {', '.join(tickers)}")
    print("=" * 72)
    for style, res in results.items():
        print(f"\n  -- {style} " + "-" * (66 - len(style)))
        if "error" in res:
            print(f"     skipped: {res['error'].splitlines()[0]}")
            continue
        alloc = res["weights"].copy()
        alloc["Weight"] = (alloc["Weight"] * 100).map(lambda x: f"{x:6.2f}%")
        print("     Allocation:")
        print("       " + alloc.to_string(index=False).replace("\n", "\n       "))
        print("     Metrics:")
        print("       " + res["metrics"].to_string().replace("\n", "\n       "))


def evaluate_all(baskets=FEB_BASKETS, period="5y", rf=0.04, label=""):
    """Run every basket in `baskets` and print a report. Returns {profile: results}."""
    if label:
        print("\n" + "#" * 72 + f"\n# {label} BASKETS\n" + "#" * 72)
    all_results = {}
    for profile, tickers in baskets.items():
        print(f"\nEvaluating '{profile}' basket >>>>>>>>>>")
        results = evaluate_basket(tickers, profile, period=period, rf=rf)
        all_results[profile] = results
        print_basket_report(profile, tickers, results)
    return all_results


# To reconcile against your boss's numbers, evaluate THEIR exact weights here
# (no optimization). Fill in the real allocation per ETF and, if you learn what
# risk-free rate / window they used, set rf= and period= to match.
#   feb_conservative_boss = {"ICSH": 0.25, "FLRN": 0.25, "PULS": 0.25, "MINT": 0.25}
#   evaluate_weights(feb_conservative_boss, rf=0.0, period="5y",
#                    label="FEB conservative (boss weights)")

if __name__ == "__main__":
    evaluate_all(FEB_BASKETS, label="FEBRUARY")
    evaluate_all(JUL_BASKETS, label="JULY")
