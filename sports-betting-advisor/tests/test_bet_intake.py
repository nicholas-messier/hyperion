#!/usr/bin/env python3
"""Regression tests for scripts/bet_intake.py parser.

Run with: python3 -m unittest tests.test_bet_intake -v
Or:       python3 tests/test_bet_intake.py

The test cases below are pinned to real OCR transcripts saved in
~/.cache/sports-bets/intake/ during normal use, copied inline so the
tests are reproducible without external state.

These tests guard the behaviors that can fail silently in production:
- spread / run-line / puck-line targets are floats and must round-trip
  through the DB writer without crashing
- profit-boosted parlays must report the boosted odds (derived from
  Wager + To Pay), not the original odds shown in OCR
- mixed parlays (player props + spread) must produce one parlay with
  all legs, not lose any leg silently
- player props must NOT inherit the team from a single-team OCR slip
  (otherwise a Maxey leg in a Knicks parlay would get tagged NYK)
"""

import os
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = REPO_ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

# Disable ESPN player-team lookup during tests so we don't make real
# network calls. Empty team strings are fine for parser-level tests.
os.environ.setdefault("BET_INTAKE_DISABLE_ESPN", "1")

import bet_intake as bi  # noqa: E402


def _disabled_lookup(player_name, sports=None):
    return ""


# Patch the ESPN lookup before any test runs.
bi.lookup_player_team = _disabled_lookup


# ── Fixtures (real OCR transcripts) ──────────────────────────

OCR_BOOSTED_SGP = """\
3 Pick Parlay | +500 +750 aa
25+, NY Knicks -12.5, 25+
Wager: $5.00 ! To Pay: $42.50
If the bet is cashed out the boost will be canceled
\u00a9 (8) *: |
re Jalen Brunson Points
O NY Knicks -12.5
Spread Alternate
25+
O Tyrese Maxey Points
"""

OCR_UNBOOSTED_SGP_292 = """\
3 Pick Parlay | +292
25+, 25+, NY Knicks -6.5
Wager: $5.00 ! To Pay: $19.60

| \u2014 25+
O Zz Jalen Brunson Points

@ 25+
O Ba Tyrese Maxey Points
O | _ NY Knicks -6.5

Spread Alternate
"""

OCR_BOOSTED_SPREAD = """\
@ BOS Celtics -8.5 | 5405 +124
Ar Spread
Wager: $2.00 !! To Pay: $4.48

If the bet is cashed out the boost will be canceled
"""

OCR_STRAIGHT_REBOUND = """\
@ 12+ 1-105
ve we Victor Wembanyama Rebounds
Wager: $1.00 ! To Pay: $1.95
"""


# ── Helper functions ─────────────────────────────────────────

class TargetHelpersTest(unittest.TestCase):
    def test_parse_target_int(self):
        self.assertEqual(bi._parse_target("25"), 25)
        self.assertIsInstance(bi._parse_target("25"), int)

    def test_parse_target_float_negative(self):
        # Spread targets can be negative floats — this is the case
        # that crashed the DB writer with int('-12.5').
        self.assertEqual(bi._parse_target("-12.5"), -12.5)
        self.assertIsInstance(bi._parse_target("-12.5"), float)

    def test_parse_target_float_positive(self):
        self.assertEqual(bi._parse_target("8.5"), 8.5)

    def test_derive_odds_positive(self):
        # +750: $5 wager -> $42.50 to pay
        self.assertEqual(bi._derive_odds_from_payout(5.0, 42.50), 750)
        # +292: $5 wager -> $19.60 to pay
        self.assertEqual(bi._derive_odds_from_payout(5.0, 19.60), 292)
        # +124: $2 wager -> $4.48 to pay
        self.assertEqual(bi._derive_odds_from_payout(2.0, 4.48), 124)

    def test_derive_odds_negative(self):
        # -110: $11 wager -> $21 to pay
        self.assertEqual(bi._derive_odds_from_payout(11.0, 21.00), -110)
        # -105: $1 wager -> $1.95 to pay
        self.assertEqual(bi._derive_odds_from_payout(1.0, 1.95), -105)

    def test_derive_odds_invalid(self):
        self.assertIsNone(bi._derive_odds_from_payout(0, 10))
        self.assertIsNone(bi._derive_odds_from_payout(5, 0))
        self.assertIsNone(bi._derive_odds_from_payout(None, 10))
        self.assertIsNone(bi._derive_odds_from_payout(5, 5))  # to_pay <= wager


# ── Parser tests ─────────────────────────────────────────────

class BoostedParlayTest(unittest.TestCase):
    """The slip that triggered this whole investigation.

    DK applied a 50% Profit Boost on a 3-leg SGP, bumping +500 -> +750.
    All 3 legs must end up in the parlay and the parlay odds must be
    the boosted +750 (not the original +500 visible elsewhere).
    """

    @classmethod
    def setUpClass(cls):
        cls.bets, cls.parlays = bi.parse_betslip(OCR_BOOSTED_SGP)

    def test_three_legs_present(self):
        self.assertEqual(len(self.bets), 3)

    def test_one_parlay(self):
        self.assertEqual(len(self.parlays), 1)
        self.assertEqual(len(self.parlays[0]["legs"]), 3)

    def test_wager_extracted(self):
        self.assertEqual(self.parlays[0]["wager"], 5.00)

    def test_boosted_odds_used(self):
        """Parlay container odds must come from To Pay ($42.50), not
        the original +500. The auto-settler reads parlay["odds"] for
        payout math, so this is the field that matters most.
        """
        self.assertEqual(self.parlays[0]["odds"], 750)

    def test_spread_leg_present(self):
        spreads = [b for b in self.bets if b["stat"] == "SPREAD"]
        self.assertEqual(len(spreads), 1)
        self.assertEqual(spreads[0]["target"], -12.5)
        self.assertEqual(spreads[0]["team"], "NYK")

    def test_player_legs_present(self):
        players = sorted(b["player"] for b in self.bets if b["stat"] == "PTS")
        self.assertEqual(players, ["Jalen Brunson", "Tyrese Maxey"])
        for bet in self.bets:
            if bet["stat"] == "PTS":
                self.assertEqual(bet["target"], 25)

    def test_player_props_no_team_inheritance(self):
        """Maxey plays for PHI, not NYK. Player props must NOT inherit
        the team from the only OCR-detected team (NY Knicks). ESPN
        lookup is responsible for filling in the correct team — and
        is mocked off in tests, so player team should be empty."""
        for bet in self.bets:
            if bet["stat"] == "PTS":
                self.assertEqual(bet["team"], "",
                    f"Expected empty team for {bet['player']}, got {bet['team']!r}")


class UnboostedSGPTest(unittest.TestCase):
    """The original slip the user submitted before getting the boost
    applied. Same shape as the boosted slip but at +292 with no boost
    badge. Used to verify the parser still handles the non-boost case.
    """

    @classmethod
    def setUpClass(cls):
        cls.bets, cls.parlays = bi.parse_betslip(OCR_UNBOOSTED_SGP_292)

    def test_three_legs(self):
        self.assertEqual(len(self.bets), 3)
        self.assertEqual(len(self.parlays), 1)

    def test_odds_derived(self):
        self.assertEqual(self.parlays[0]["odds"], 292)

    def test_spread_leg(self):
        spreads = [b for b in self.bets if b["stat"] == "SPREAD"]
        self.assertEqual(len(spreads), 1)
        self.assertEqual(spreads[0]["target"], -6.5)


class StraightSpreadTest(unittest.TestCase):
    """A boosted spread on the Celtics — single bet, not a parlay."""

    @classmethod
    def setUpClass(cls):
        cls.bets, cls.parlays = bi.parse_betslip(OCR_BOOSTED_SPREAD)

    def test_one_bet_no_parlay(self):
        self.assertEqual(len(self.bets), 1)
        self.assertEqual(len(self.parlays), 0)

    def test_spread_value_negative(self):
        self.assertEqual(self.bets[0]["stat"], "SPREAD")
        self.assertEqual(self.bets[0]["target"], -8.5)
        self.assertEqual(self.bets[0]["team"], "BOS")

    def test_odds_derived_from_payout(self):
        # $2 -> $4.48 implies +124
        self.assertEqual(self.bets[0]["odds"], 124)


class StraightProponTest(unittest.TestCase):
    """A plain Wemby rebound prop with no parlay or spread."""

    @classmethod
    def setUpClass(cls):
        cls.bets, cls.parlays = bi.parse_betslip(OCR_STRAIGHT_REBOUND)

    def test_one_bet_no_parlay(self):
        self.assertEqual(len(self.bets), 1)
        self.assertEqual(len(self.parlays), 0)

    def test_player_and_stat(self):
        b = self.bets[0]
        self.assertEqual(b["player"], "Victor Wembanyama")
        self.assertEqual(b["stat"], "REB")
        self.assertEqual(b["target"], 12)


# ── DB writer test ───────────────────────────────────────────

class WriteToDbTest(unittest.TestCase):
    """Make sure _write_to_db doesn't crash on float spread targets,
    which is the regression that lost the original 3-leg SGP upload.

    Uses a temporary DB so we don't touch the user's real bankroll.
    """

    @classmethod
    def setUpClass(cls):
        if not bi._HAS_DB:
            raise unittest.SkipTest("db module not available")

    def setUp(self):
        # Point the db module at a tempfile and force a fresh connection
        import db
        import tempfile
        self._tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self._tmp.close()
        self._orig_path = db.DB_PATH
        db.DB_PATH = Path(self._tmp.name)
        db.close()  # drop any existing connection so we use the new path

    def tearDown(self):
        import db
        db.close()
        Path(self._tmp.name).unlink(missing_ok=True)
        db.DB_PATH = self._orig_path

    def test_mixed_parlay_writes(self):
        """Spread + 2 player props in one parlay should write cleanly."""
        bets, parlays = bi.parse_betslip(OCR_BOOSTED_SGP)
        ok = bi._write_to_db(bets, parlays)
        self.assertTrue(ok, "_write_to_db should succeed; check stderr")

        import db as _db
        conn = _db._get_conn()
        rows = conn.execute("SELECT player, stat, target, parlay_id FROM bets").fetchall()
        self.assertEqual(len(rows), 3, f"Expected 3 leg rows, got {len(rows)}")
        # All rows should belong to the same parlay
        parlay_ids = {r["parlay_id"] for r in rows}
        self.assertEqual(len(parlay_ids), 1)
        # Spread target must round-trip as a float
        spread = [r for r in rows if r["stat"] == "SPREAD"][0]
        self.assertEqual(spread["target"], -12.5)
        # Parlay odds must reflect the boosted value
        parlay_row = conn.execute(
            "SELECT odds, wager FROM parlays WHERE id=?",
            (next(iter(parlay_ids)),),
        ).fetchone()
        self.assertEqual(parlay_row["odds"], 750)
        self.assertEqual(parlay_row["wager"], 5.0)


if __name__ == "__main__":
    unittest.main()
