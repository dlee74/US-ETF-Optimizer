"""Test fixtures for deck_automation live under fixtures/ and contain real
Wiley Group client data (account numbers, dollar figures, actual target
allocation) — they are gitignored and NEVER committed to this public repo.
Tests that need them skip cleanly if they're absent, rather than failing.

To regenerate fixtures/ locally:
  1. Copy the client's current deck (e.g. the latest
     "Wiley Group - Portfolio Update - *.pptx" under
     G:\\Shared drives\\InvestMint Corporate Drive\\Old InvestMint Corporate\\
     Clients\\DJ\\) to fixtures/wiley_group_july_2026.pptx (or update the
     filename references in tests/ if using a newer cycle).
  2. Unzip it and copy ppt/charts/chart{1,2}.xml, their _rels, and their
     paired ppt/embeddings/*.xlsx into fixtures/chart1/ and fixtures/chart2/
     (see deck_automation/patch/chart_xml.py and embedded_workbook.py for
     the exact chart<->embedding mapping via chartN.xml.rels).
  3. Copy ppt/slides/slide7.xml (or whichever slide has the tax_optimized
     metrics table) to fixtures/metrics_slide7.xml.
"""

import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

FIXTURES = Path(__file__).resolve().parent / "fixtures"

REQUIRED_FIXTURE_FILES = [
    "wiley_group_july_2026.pptx",
    "metrics_slide7.xml",
    "chart1/chart1.xml", "chart1/chart1.xml.rels", "chart1/embedded_workbook.xlsx",
    "chart2/chart2.xml", "chart2/chart2.xml.rels", "chart2/embedded_workbook.xlsx",
]


def _fixtures_present() -> bool:
    return all((FIXTURES / f).exists() for f in REQUIRED_FIXTURE_FILES)


@pytest.fixture
def fixtures_dir():
    if not _fixtures_present():
        pytest.skip(
            "deck_automation/tests/fixtures/ not present (gitignored, contains "
            "real client data) — see this file's module docstring to regenerate "
            "locally from a real Wiley Group deck."
        )
    return FIXTURES
