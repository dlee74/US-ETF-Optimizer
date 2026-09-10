import os
import pandas as pd
import requests
import time
from pathlib import Path

# FMP API key comes from the environment, never a committed literal.
# Set it before running, e.g. in PowerShell:  $env:FMP_API_KEY = "your-key"
# (or put FMP_API_KEY in a .env you never commit). When unset it stays the
# PASTE_YOUR_KEY_HERE sentinel below, which disables the FMP call path and
# the script falls back to yfinance.
API_KEY       = os.environ.get("FMP_API_KEY", "PASTE_YOUR_KEY_HERE")
INPUT_FILE    = "US_Final_ETF_Data.csv"           # <-- your file (.csv or .xlsx)
TICKER_COLUMN = "Symbol"                # <-- the column that holds the tickers

BASE_DIR = Path(__file__).resolve().parent.parent.parent
csv_path = BASE_DIR / "US_Final_ETF_Data.csv"

df = pd.read_csv(csv_path)

# yfinance is the backup source; only import if it's installed
try:
    import yfinance as yf
    HAVE_YF = True
except ImportError:
    HAVE_YF = False
    print("(yfinance not installed -> running FMP only. `pip install yfinance` for backup.)")


# --- loop through every ticker in the dataframe ---
expense_ratios = []
sources        = []
seen           = {}      # remember tickers we already looked up (saves API calls)
fmp_dead       = False   # flips True once the FMP daily free limit is hit

for i, raw in enumerate(df[TICKER_COLUMN]):
    ticker = str(raw).strip().upper()

    # already looked this one up? reuse it.
    if ticker in seen:
        er, source = seen[ticker]
        expense_ratios.append(er)
        sources.append(source)
        print(f"{i+1}/{len(df)}  {ticker:8s} -> {er}  (cached)")
        continue

    er, source = None, "not found"

    # 1) try FMP (unless we've already hit today's free limit)
    if API_KEY != "PASTE_YOUR_KEY_HERE" and not fmp_dead:
        try:
            r = requests.get(
                "https://financialmodelingprep.com/stable/etf/info",
                params={"symbol": ticker, "apikey": API_KEY},
                timeout=15,
            )
            if r.status_code == 429:
                # 250/day free limit reached -> stop calling FMP, lean on yfinance
                fmp_dead = True
                print("  >> FMP daily free limit hit. Using yfinance for the rest.")
            else:
                data = r.json()
                if isinstance(data, list) and data and data[0].get("expenseRatio") not in (None, ""):
                    er = float(data[0]["expenseRatio"])
                    source = "fmp"
        except Exception:
            pass

    # 2) fall back to yfinance if FMP gave us nothing
    if er is None and HAVE_YF:
        try:
            t = yf.Ticker(ticker)
            val = None
            try:
                ov = t.funds_data.fund_overview
                if isinstance(ov, dict):
                    for k in ("expense_ratio", "expenseRatio", "annualReportExpenseRatio"):
                        if ov.get(k) not in (None, ""):
                            val = ov[k]
                            break
            except Exception:
                pass
            if val is None:
                info = t.info or {}
                for k in ("annualReportExpenseRatio", "netExpenseRatio", "expenseRatio"):
                    if info.get(k) not in (None, ""):
                        val = info[k]
                        break
            if val is not None:
                er = float(val)
                source = "yfinance"
        except Exception:
            pass

    seen[ticker] = (er, source)
    expense_ratios.append(er)
    sources.append(source)
    print(f"{i+1}/{len(df)}  {ticker:8s} -> {er}  ({source})")
    time.sleep(0.25)   # small pause so we don't hammer the API


# --- attach the results and save ---
df["expense_ratio"] = expense_ratios
df["er_source"]     = sources
df.to_csv("etfs_with_er.csv", index=False)

missing = [t for t, (er, _) in seen.items() if er is None]
print(f"\nDone. Saved -> etfs_with_er.csv")
print(f"{len(missing)} ticker(s) had no expense ratio: {missing}")
