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
import os
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from deck_automation.clients import CLIENTS  # noqa: E402
from deck_automation.extract import extract_portfolio_holdings  # noqa: E402
from deck_automation.optimize import optimize_holdings, refresh_metrics_at_target  # noqa: E402
from deck_automation.patch.package import patch_metrics_refresh  # noqa: E402
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
        current = dict(zip(h.tickers, h.weights))
        proposed = dict(zip(optimized.tickers, optimized.weights))

        lines.append(f"\n## {h.slide_title}\n")
        lines.append("| Ticker | Current | Proposed |")
        lines.append("|---|---|---|")
        for ticker in optimized.tickers:
            lines.append(f"| {ticker} | {current.get(ticker, 0):.1%} | {proposed[ticker]:.1%} |")
        lines.append(f"\nWindow: {optimized.window[0]} to {optimized.window[1]}\n")
        lines.append("| Metric | Value |")
        lines.append("|---|---|")
        for metric, value in optimized.metrics["Value"].items():
            lines.append(f"| {metric} | {value} |")

    out_path = out_dir / f"{Path(args.template).stem} - proposal.md"
    out_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"\nStandalone comparison written to: {out_path}")
    print("This does NOT modify the deck — insert into a new slide by hand if approved,")
    print("or ask for slide-cloning automation as a separate follow-up.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                      formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="mode", required=True)

    for name, fn in (("refresh", cmd_refresh), ("propose", cmd_propose)):
        p = sub.add_parser(name)
        p.add_argument("--client", required=True, choices=list(CLIENTS))
        p.add_argument("--template", required=True, help="Explicit path to the deck to start from")
        p.add_argument("--out-subdir", default=_default_out_subdir(),
                        help="Relative to the client's folder, e.g. '2026/Aug 2, 2026'")
        p.add_argument("--dry-run", action="store_true",
                        help="Write to a scratch dir instead of the client's real folder")
        p.add_argument("--force", action="store_true",
                        help="Allow writing into a non-empty --out-subdir")
        p.set_defaults(func=fn)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
