try:
    from .wiley_group_private import COST_BASIS
except ImportError as e:
    raise ImportError(
        "deck_automation/clients/wiley_group_private.py is missing (gitignored, "
        "contains real client cost-basis data — never committed). Copy "
        "wiley_group_private.py.example to wiley_group_private.py and fill in "
        "verified numbers from the client's real TD Direct Investing statement "
        "(Clients/DJ/Investment Account Statements/*.pdf) before using "
        "position_value.py or rebalance.py."
    ) from e


WILEY_GROUP = {

    "client_dir": r"G:\Shared drives\InvestMint Corporate Drive\Old InvestMint Corporate\Clients\DJ",

    # Each portfolio block that appears in the deck: which slide has the
    # holdings table, which chart part backs it, and which slide has its
    # metrics table.
    "portfolios": [
        {
            "name":         "corporate_cash",
            "slide_title":  "Wiley Group Corporate Cash Portfolio",
            "table_slide":  3,             # 1-indexed, matches how humans talk about slides
            "chart_part":   "chart1.xml",
            "metrics_slide": 6,
        },
        {
            "name":         "tax_optimized",
            "slide_title":  "Tax-Optimized Corporate Cash Portfolio",
            "table_slide":  4,
            "chart_part":   "chart2.xml",
            "metrics_slide": 7,
        },
    ],

    # Bare ticker (as it appears in the deck's chart/table XML) -> the
    # yfinance-fetchable ticker (TSX-listed names need the .TO suffix, which
    # is never present in the deck itself). Extend this if/when holdings change;
    # extraction hard-fails on any ticker not listed here rather than guessing.
    "ticker_map": {
        "HDIV": "HDIV.TO",
        "ZCS":  "ZCS.TO",
        "XFR":  "XFR.TO",
        "RPF":  "RPF.TO",
        "CMR":  "CMR.TO",
        "HFR":  "HFR.TO",
        "PFL":  "PFL.TO",
        "QHY":  "QHY.TO",
    },

    # Asset-class description shown in the "Type" column — public fund info,
    # verified against the deck's own holdings tables (slide3/slide4 of the
    # July 2026 update).
    "ticker_types": {
        "HDIV": "Enhanced Dividend (Covered Call)",
        "ZCS":  "Short Corporate Bond",
        "XFR":  "Floating Rate Bond",
        "RPF":  "Canadian Preferred Shares",
        "CMR":  "Premium Money Market",
        "HFR":  "Ultra-Short Investment Grade Bond",
        "PFL":  "Government Floating Rate",
        "QHY":  "US High Yield Bond (CAD-Hedged)",
    },

    # Matches what was actually used by hand for this client, not
    # evaluate_custom_weights()'s own 5y default.
    "period": "3y",
    "rf": 0.04,

    # Risk tier for the SLSQP core-k objective (Optimizer_Class/optimizer_weights.py)
    # -- "enhanced" matches the primary recommendation used historically for this
    # client. w_min/max_etf_weight match main_portfolio.evaluate_basket()'s own
    # defaults, sized for a concentrated 4-name sleeve.
    "optimizer_profile": "enhanced",
    "w_min": 0.05,
    "max_etf_weight": 0.40,

    # Verified against the client's real TD Direct Investing statements —
    # see wiley_group_private.py.example for how to regenerate/update.
    "cost_basis": COST_BASIS,
}
