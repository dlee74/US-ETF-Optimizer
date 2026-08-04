"""CLI entry point for the Wiley Group deck pipeline.

Two modes:
  refresh  — routine cycle. Recomputes the metrics table at the deck's
             existing static target weights with fresh price data, patches
             the deck, runs QA, writes a NEW file under a NEW dated
             subfolder (never overwrites --template or any existing cycle).
  propose  — occasional strategic review. Finds new SLSQP-optimized weights
             among the currently-held tickers and writes a standalone
             comparison report (current vs. proposed) — does NOT touch the
             deck itself; inserting a new slide into the branded template is
             out of scope for this pipeline (see plan's scope cut).

Never guesses which template to use — always requires --template explicitly,
since a client's folder can hold multiple deck variants per cycle.

Usage:
    python -m deck_automation.produce_update refresh \\
        --client wiley_group \\
        --template "G:\\...\\Clients\\DJ\\2026\\July 24\\Wiley Group - Portfolio Update - July 2026.pptx" \\
        --out-subdir "2026\\Aug 2, 2026" \\
        [--dry-run] [--force]

    python -m deck_automation.produce_update propose \\
        --client wiley_group \\
        --template "...\\Wiley Group - Portfolio Update - July 2026.pptx" \\
        --out-subdir "2026\\Aug 2, 2026" \\
        [--dry-run]
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from deck_automation.blotter_docx import build_blotter  # noqa: E402
from deck_automation.clients import CLIENTS  # noqa: E402
from deck_automation.extract import extract_portfolio_holdings  # noqa: E402
from deck_automation.optimize import (  # noqa: E402
    build_reoptimization_table, optimize_holdings, refresh_metrics_at_target,
)
from deck_automation.patch.package import patch_metrics_refresh  # noqa: E402
from deck_automation.position_value import current_price, current_values  # noqa: E402
from deck_automation.rebalance import compute_full_exit_swap, compute_trades  # noqa: E402
from deck_automation.trade_blotter import TBD, build_blotter_row  # noqa: E402
from deck_automation.render_qa import run_qa  # noqa: E402


def _default_out_subdir() -> str:
    today = datetime.date.today()
    # %-d (no leading zero) is a glibc extension, not portable to Windows'
    # strftime — build the "Mon D, YYYY" form manually instead.
    return os.path.join(str(today.year), f"{today.strftime('%b')} {today.day}, {today.year}")


def _resolve_out_dir(client_config: dict, out_subdir: str, dry_run: bool, force: bool) -> Path:
    if dry_run:
        scratch = Path(os.environ.get("TEMP", "/tmp")) / "deck_automation_dry_run" / out_subdir
        scratch.mkdir(parents=True, exist_ok=True)
        return scratch

    out_dir = Path(client_config["client_dir"]) / out_subdir
    if out_dir.exists() and any(out_dir.iterdir()) and not force:
        raise SystemExit(
            f"{out_dir} already exists and is non-empty. Pass --force to write "
            "into it anyway, or pick a different --out-subdir."
        )
    out_dir.mkdir(parents=True, exist_ok=True)
    return out_dir


def cmd_refresh(args) -> None:
    client_config = CLIENTS[args.client]
    out_dir = _resolve_out_dir(client_config, args.out_subdir, args.dry_run, args.force)

    print(f"Extracting holdings from {args.template} ...")
    holdings = extract_portfolio_holdings(args.template, client_config)

    print("Refreshing metrics at each portfolio's static target weights ...")
    refreshed = [refresh_metrics_at_target(h, client_config) for h in holdings]
    for h, r in zip(holdings, refreshed):
        print(f"  {h.name}: target {h.target_weights}")

    template_name = Path(args.template).stem
    out_path = out_dir / f"{template_name} (refreshed).pptx"
    print(f"Patching metrics table -> {out_path}")
    patch_metrics_refresh(args.template, str(out_path), client_config, refreshed)

    png_dir = out_dir / "qa_render"
    print(f"Running QA (structural, semantic, text-length, PowerPoint render to {png_dir}) ...")
    report = run_qa(args.template, str(out_path), client_config, refreshed, str(png_dir))

    print(f"\nstructural_ok={report.structural_ok}  semantic_ok={report.semantic_ok}")
    if report.structural_errors:
        print("STRUCTURAL ERRORS:", *report.structural_errors, sep="\n  ")
    if report.semantic_errors:
        print("SEMANTIC ERRORS:", *report.semantic_errors, sep="\n  ")
    if report.length_warnings:
        print("Length warnings (review the render for wrapping):")
        for w in report.length_warnings:
            print(" ", w)
    if report.rendered_pngs:
        print("Rendered for review:", *report.rendered_pngs, sep="\n  ")

    if not report.passed_automated_checks:
        raise SystemExit("Automated checks failed — output NOT finalized. See errors above.")

    print(f"\nOutput at: {out_path}")
    print("This is NOT final until the rendered PNGs above have been visually reviewed.")


def cmd_propose(args) -> None:
    client_config = CLIENTS[args.client]
    out_dir = _resolve_out_dir(client_config, args.out_subdir, args.dry_run, args.force)

    print(f"Extracting holdings from {args.template} ...")
    holdings = extract_portfolio_holdings(args.template, client_config)

    lines = ["# Wiley Group — Re-optimization Proposal\n",
             f"Template: {args.template}\n",
             f"Profile: {client_config['optimizer_profile']}\n"]

    for h in holdings:
        print(f"Re-optimizing {h.name} ...")
        optimized = optimize_holdings(h, client_config)

        reopt_table = build_reoptimization_table(h, optimized, client_config)

        lines.append(f"\n## {h.slide_title}\n")
        lines.append("### Re-Optimized Allocation (proposed new target — not yet executed)\n")
        lines.append("| " + " | ".join(reopt_table[0].keys()) + " |")
        lines.append("|" + "---|" * 8)
        for row in reopt_table:
            lines.append("| " + " | ".join(str(v) for v in row.values()) + " |")

        lines.append(f"\nWindow: {optimized.window[0]} to {optimized.window[1]}\n")
        lines.append("| Metric | Value |")
        lines.append("|---|---|")
        for metric, value in optimized.metrics["Value"].items():
            lines.append(f"| {metric} | {value} |")

        if h.target_weights is not None:
            print(f"Computing rebalance-to-target trades for {h.name} ...")
            portfolio_cost_basis = {t: client_config["cost_basis"][t] for t in h.tickers}
            values = current_values(portfolio_cost_basis, client_config["ticker_map"])
            trades = compute_trades(values, h.target_weights)

            lines.append("\n### Rebalance to Existing Target (routine maintenance, "
                         f"back to {h.target_weights_text.split(':', 1)[1].strip()})\n")
            lines.append("| Ticker | Action | $ Amount | Shares Δ | Current $ Value | Target $ Value | Target Weight |")
            lines.append("|---|---|---|---|---|---|---|")
            for t in trades:
                lines.append(
                    f"| {t.ticker} | {t.action} | {t.dollar_amount:,.2f} | {t.shares_delta:+.1f} | "
                    f"{t.current_market_value:,.2f} | {t.target_market_value:,.2f} | {t.new_weight:.1%} |"
                )

    out_path = out_dir / f"{Path(args.template).stem} - proposal.md"
    out_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"\nStandalone comparison written to: {out_path}")
    print("This does NOT modify the deck — insert into a new slide by hand if approved,")
    print("or ask for slide-cloning automation as a separate follow-up.")


def cmd_blotter(args) -> None:
    client_config = CLIENTS[args.client]
    out_dir = _resolve_out_dir(client_config, args.out_subdir, args.dry_run, args.force)

    print(f"Extracting holdings from {args.template} ...")
    holdings = extract_portfolio_holdings(args.template, client_config)

    manual_trades = None
    if args.trades_from != "rebalance-to-target":
        manual_trades = json.loads(Path(args.trades_from).read_text(encoding="utf-8"))

    portfolios_docx = []
    for h in holdings:
        spec = None if manual_trades is None else manual_trades.get(h.name)
        if manual_trades is not None and spec is None:
            continue

        portfolio_cost_basis = {t: client_config["cost_basis"][t] for t in h.tickers}
        print(f"Computing trades for {h.name} ...")

        if isinstance(spec, dict) and spec.get("type") == "swap":
            # A standing order to dispose of one holding entirely and buy a
            # replacement with the exact proceeds — NOT a full rebalance;
            # every other ticker in the portfolio is left untouched.
            sell_ticker, buy_ticker = spec["sell"], spec["buy"]
            all_values = current_values(portfolio_cost_basis, client_config["ticker_map"])
            portfolio_total = sum(pv.market_value for pv in all_values.values())
            buy_price = current_price(client_config["ticker_map"][buy_ticker])
            sell_trade, buy_trade = compute_full_exit_swap(
                all_values[sell_ticker], buy_ticker, buy_price, portfolio_total)
            trades = [sell_trade, buy_trade]
        else:
            target_weights = h.target_weights if spec is None else spec
            if target_weights is None:
                print(f"Skipping {h.name}: no 'Target Weights: ...' text found on this deck")
                continue
            values = current_values(portfolio_cost_basis, client_config["ticker_map"])
            trades = compute_trades(values, target_weights)

        rows = []
        for t in trades:
            # Only apply a confirmed limit-price convention: full_exit for a
            # complete exit (new_weight == 0), "last_close" for a fresh buy
            # into a swap's replacement ticker (confirmed exact for ZCS
            # specifically — see plan Phase 3), never a guessed formula for
            # a partial trim/buy — those come back TBD.
            is_swap = isinstance(spec, dict) and spec.get("type") == "swap"
            if t.new_weight == 0:
                method, purchase_date = "full_exit", client_config["cost_basis"][t.ticker].get("purchase_date")
            elif is_swap and t.action == "BUY":
                method, purchase_date = "last_close", None
            else:
                method, purchase_date = None, None
            rows.append(build_blotter_row(
                t, client_config["ticker_map"][t.ticker], args.as_of_date,
                limit_price_method=method, purchase_date=purchase_date,
            ))

        portfolio_label = next(p["slide_title"] for p in client_config["portfolios"] if p["name"] == h.name)
        portfolios_docx.append({"heading": portfolio_label, "rows": rows, "watchpoints": []})

    if not portfolios_docx:
        raise SystemExit("No portfolios had trades to blotter — nothing to write.")

    client_display_name = args.client.replace("_", " ").title()
    out_path = out_dir / f"{client_display_name}_Trade_Blotter.docx"
    build_blotter(client_display_name, args.as_of_date, portfolios_docx, str(out_path))

    print(f"\nBlotter written to: {out_path}")
    tbd_count = sum(1 for p in portfolios_docx for r in p["rows"] if r["Limit Price"] == TBD)
    if tbd_count:
        print(f"{tbd_count} row(s) have a TBD limit price — no confirmed formula for a "
              "partial trim/buy (see plan Phase 3). Advisor must set these manually.")
    print("Ticker-Specific Watchpoints section is empty — add narrative notes by hand "
          "after reviewing the computed trades (not auto-generated, by design).")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                      formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="mode", required=True)

    for name, fn in (("refresh", cmd_refresh), ("propose", cmd_propose), ("blotter", cmd_blotter)):
        p = sub.add_parser(name)
        p.add_argument("--client", required=True, choices=list(CLIENTS))
        p.add_argument("--template", required=True, help="Explicit path to the deck to start from")
        p.add_argument("--out-subdir", default=_default_out_subdir(),
                        help="Relative to the client's folder, e.g. '2026/Aug 2, 2026'")
        p.add_argument("--dry-run", action="store_true",
                        help="Write to a scratch dir instead of the client's real folder")
        p.add_argument("--force", action="store_true",
                        help="Allow writing into a non-empty --out-subdir")
        if name == "blotter":
            p.add_argument("--as-of-date", default=datetime.date.today().strftime("%Y-%m-%d"),
                            help="YYYY-MM-DD; drives limit-price/range lookback windows")
            p.add_argument("--trades-from", default="rebalance-to-target",
                            help="'rebalance-to-target' (routine, uses the deck's own target "
                                 "weights) or a path to a JSON file {portfolio_name: {ticker: "
                                 "weight}} for a manually-specified trade set (e.g. a strategic "
                                 "swap like Portfolio 1's QHY->ZCS)")
        p.set_defaults(func=fn)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
