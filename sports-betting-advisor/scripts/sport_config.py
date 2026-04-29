"""
sport_config.py — Shared sport configuration for all 4 major US sports.

Centralizes ESPN API endpoints, stat labels, team aliases, and
sport-detection logic so that live_tracker, auto_settle, game_monitor,
and the conky dashboard can all handle NBA, NFL, MLB, and NHL.
"""

# ── ESPN API base URL templates ──────────────────────────────
# Use .format(sport_path=...) to fill in the sport path segment.

ESPN_SCOREBOARD = "https://site.api.espn.com/apis/site/v2/sports/{sport_path}/scoreboard"
ESPN_SUMMARY = "https://site.api.espn.com/apis/site/v2/sports/{sport_path}/summary"

# ── Per-sport configuration ──────────────────────────────────

SPORTS = {
    "nba": {
        "name": "NBA",
        "espn_path": "basketball/nba",
        "scoreboard_url": ESPN_SCOREBOARD.format(sport_path="basketball/nba"),
        "summary_url": ESPN_SUMMARY.format(sport_path="basketball/nba"),
        # Which stat group to use from the boxscore (index into statistics[])
        "stat_group": 0,  # NBA has one stat block per team
        "stat_labels": [
            "MIN", "PTS", "FG", "3PT", "FT", "REB", "AST",
            "TO", "STL", "BLK", "OREB", "DREB", "PF", "+/-",
        ],
        # Stats stored in "made-attempted" format (e.g., "7-11")
        "split_stats": {"FG", "3PT", "FT"},
        # Composite stats we can derive
        "composite_stats": {
            "PRA": lambda s: s.get("PTS", 0) + s.get("REB", 0) + s.get("AST", 0),
        },
        "season_type_playoff": "3",
    },
    "nfl": {
        "name": "NFL",
        "espn_path": "football/nfl",
        "scoreboard_url": ESPN_SCOREBOARD.format(sport_path="football/nfl"),
        "summary_url": ESPN_SUMMARY.format(sport_path="football/nfl"),
        "stat_group": None,  # NFL has multiple stat groups (passing/rushing/receiving)
        "stat_labels": [],   # Labels come from the API per group
        "split_stats": set(),
        "composite_stats": {},
        "season_type_playoff": "3",
    },
    "mlb": {
        "name": "MLB",
        "espn_path": "baseball/mlb",
        "scoreboard_url": ESPN_SCOREBOARD.format(sport_path="baseball/mlb"),
        "summary_url": ESPN_SUMMARY.format(sport_path="baseball/mlb"),
        "stat_group": None,  # MLB has batting and pitching groups
        "stat_labels": [],
        "split_stats": set(),
        "composite_stats": {},
        "season_type_playoff": "3",
    },
    "nhl": {
        "name": "NHL",
        "espn_path": "hockey/nhl",
        "scoreboard_url": ESPN_SCOREBOARD.format(sport_path="hockey/nhl"),
        "summary_url": ESPN_SUMMARY.format(sport_path="hockey/nhl"),
        "stat_group": None,
        "stat_labels": [],
        "split_stats": set(),
        "composite_stats": {},
        "season_type_playoff": "3",
    },
}


def get_sport_urls(sport: str) -> tuple[str, str]:
    """Return (scoreboard_url, summary_url) for a sport key."""
    cfg = SPORTS.get(sport, SPORTS["nba"])
    return cfg["scoreboard_url"], cfg["summary_url"]


def get_all_scoreboard_urls() -> dict[str, str]:
    """Return {sport_key: scoreboard_url} for every sport."""
    return {k: v["scoreboard_url"] for k, v in SPORTS.items()}


# ── Team abbreviation aliases (DraftKings → ESPN) ────────────
# Shared across all sports.  Keys are DK/standard abbreviations
# that differ from what ESPN uses.

TEAM_ALIASES = {
    # NBA
    "NYK": "NY", "SAS": "SA", "GSW": "GS", "NOP": "NO", "UTA": "UTAH",
    # MLB (most match already, add any oddballs)
    # NFL
    "JAX": "JAX",  # ESPN uses JAX as well
    # NHL
    "VGK": "VGK",  # Vegas Golden Knights (ESPN uses VGK)
}
TEAM_ALIASES_REV = {v: k for k, v in TEAM_ALIASES.items()}


def espn_abbr(team: str) -> str:
    """Normalize a team abbreviation to ESPN format."""
    return TEAM_ALIASES.get(team, team)


def dk_abbr(team: str) -> str:
    """Convert ESPN abbreviation back to standard/DK format."""
    return TEAM_ALIASES_REV.get(team, team)


# ── Team → sport mapping ────────────────────────────────────
# Used to detect which sport a bet belongs to from its team abbreviation.

NBA_TEAM_ABBRS = {
    "ATL", "BOS", "BKN", "CHA", "CHI", "CLE", "DAL", "DEN",
    "DET", "GS", "GSW", "HOU", "IND", "LAC", "LAL", "MEM",
    "MIA", "MIL", "MIN", "NO", "NOP", "NY", "NYK", "OKC",
    "ORL", "PHI", "PHX", "POR", "SA", "SAS", "SAC", "TOR",
    "UTA", "UTAH", "WAS",
}

MLB_TEAM_ABBRS = {
    "ARI", "BAL", "BOS", "CHC", "CHW", "CIN", "CLE", "COL",
    "DET", "HOU", "KC", "LAA", "LAD", "MIA", "MIL", "MIN",
    "NYM", "NYY", "ATH", "OAK", "PHI", "PIT", "SD", "SF",
    "SEA", "STL", "TB", "TEX", "TOR", "WSH",
}

NFL_TEAM_ABBRS = {
    "ARI", "ATL", "BAL", "BUF", "CAR", "CHI", "CIN", "CLE",
    "DAL", "DEN", "DET", "GB", "HOU", "IND", "JAX", "KC",
    "LAC", "LAR", "LV", "MIA", "MIN", "NE", "NO", "NYG",
    "NYJ", "PHI", "PIT", "SEA", "SF", "TB", "TEN", "WAS",
}

NHL_TEAM_ABBRS = {
    "ANA", "ARI", "BOS", "BUF", "CAR", "CBJ", "CGY", "CHI",
    "COL", "DAL", "DET", "EDM", "FLA", "LA", "MIN", "MTL",
    "NJ", "NSH", "NYI", "NYR", "OTT", "PHI", "PIT", "SEA",
    "SJ", "STL", "TB", "TOR", "UTA", "VAN", "VGK", "WPG", "WSH",
}

# Abbreviations unique to exactly one sport — used for unambiguous detection.
# We build this lazily on first use.
_UNIQUE_SPORT_MAP: dict[str, str] | None = None


def _build_unique_map():
    global _UNIQUE_SPORT_MAP
    all_sets = {
        "nba": NBA_TEAM_ABBRS,
        "mlb": MLB_TEAM_ABBRS,
        "nfl": NFL_TEAM_ABBRS,
        "nhl": NHL_TEAM_ABBRS,
    }
    # Count how many sports each abbreviation appears in
    counts: dict[str, list[str]] = {}
    for sport, abbrs in all_sets.items():
        for a in abbrs:
            counts.setdefault(a, []).append(sport)
    _UNIQUE_SPORT_MAP = {}
    for a, sports in counts.items():
        if len(sports) == 1:
            _UNIQUE_SPORT_MAP[a] = sports[0]


def detect_sport_from_team(team_abbr: str) -> str:
    """Best-effort sport detection from a team abbreviation.

    Returns 'nba', 'mlb', 'nfl', 'nhl', or '' if ambiguous.
    Uses canonical ESPN abbreviation.
    """
    if _UNIQUE_SPORT_MAP is None:
        _build_unique_map()
    canonical = espn_abbr(team_abbr)
    return _UNIQUE_SPORT_MAP.get(canonical, "")


def detect_sport_from_stat(stat: str) -> str:
    """Detect sport from the stat type if possible.

    Returns 'nba', 'mlb', 'nfl', 'nhl', or '' if ambiguous.
    """
    nba_stats = {"PTS", "REB", "AST", "BLK", "STL", "3PT", "PRA", "FG", "FT", "OREB", "DREB"}
    mlb_stats = {"K", "H", "HR", "RBI", "HA", "TB", "ER", "IP", "OUTS", "BB", "R"}
    nfl_stats = {"PASS_YDS", "RUSH_YDS", "REC_YDS", "PASS_TD", "RUSH_TD", "REC_TD",
                 "COMPLETIONS", "RECEPTIONS", "INT"}
    # NHL uses G (goals), A (assists), SOG (shots on goal), S (saves)
    nhl_stats = {"G", "SOG", "S", "SV"}

    stat_upper = stat.upper()
    if stat_upper in nba_stats:
        return "nba"
    if stat_upper in mlb_stats:
        return "mlb"
    if stat_upper in nfl_stats:
        return "nfl"
    if stat_upper in nhl_stats:
        return "nhl"
    return ""


def detect_sport(team: str, stat: str = "") -> str:
    """Detect sport from team and/or stat, returning best guess.

    Priority: unique team match > stat match > empty string.
    """
    sport = detect_sport_from_team(team)
    if sport:
        return sport
    if stat:
        return detect_sport_from_stat(stat)
    return ""


# ── Multi-sport stat extraction ──────────────────────────────

def extract_player_stats_from_summary(summary: dict, sport: str = "nba") -> dict:
    """Extract all player stats from an ESPN game summary.

    Returns {player_name: {stat_key: value, ...}}.
    Works for NBA, MLB, NFL, and NHL by handling each sport's
    box score format.
    """
    all_stats = {}
    cfg = SPORTS.get(sport, SPORTS["nba"])

    for team_block in summary.get("boxscore", {}).get("players", []):
        team_abbr = team_block.get("team", {}).get("abbreviation", "")

        for stat_group in team_block.get("statistics", []):
            group_type = stat_group.get("type", stat_group.get("name", ""))
            labels = stat_group.get("labels", [])
            keys = stat_group.get("keys", [])

            for athlete in stat_group.get("athletes", []):
                name = athlete.get("athlete", {}).get("displayName", "Unknown")
                raw = athlete.get("stats", [])
                if not raw:
                    continue

                if name not in all_stats:
                    all_stats[name] = {"_team": team_abbr}

                parsed = all_stats[name]

                if sport == "nba":
                    _parse_nba_stats(parsed, labels, raw, cfg)
                elif sport == "mlb":
                    _parse_mlb_stats(parsed, labels, keys, raw, group_type)
                elif sport == "nfl":
                    _parse_nfl_stats(parsed, labels, keys, raw, group_type)
                elif sport == "nhl":
                    _parse_nhl_stats(parsed, labels, keys, raw, group_type)

    return all_stats


def _parse_nba_stats(parsed, labels, raw, cfg):
    """Parse NBA box score stats."""
    split_stats = cfg["split_stats"]
    for i, label in enumerate(labels):
        if i >= len(raw):
            break
        val = raw[i]
        if "-" in str(val) and label in split_stats:
            parts = val.split("-")
            try:
                parsed[label] = int(parts[0])
                parsed[f"{label}A"] = int(parts[1])
            except (ValueError, IndexError):
                parsed[label] = val
        elif label == "+/-":
            parsed[label] = int(val.replace("+", "")) if val else 0
        else:
            try:
                parsed[label] = int(val)
            except ValueError:
                parsed[label] = val


def _parse_mlb_stats(parsed, labels, keys, raw, group_type):
    """Parse MLB box score stats (batting + pitching)."""
    # Map ESPN keys/labels to our stat codes
    mlb_key_map = {
        # Pitching
        "strikeouts": "K", "walks": "BB", "earnedRuns": "ER",
        "hits": "H", "runs": "R", "homeRuns": "HR",
        "fullInnings.partInnings": "IP", "pitches": "PC",
        "ERA": "ERA",
        # Batting
        "atBats": "AB", "RBIs": "RBI",
        "avg": "AVG", "onBasePct": "OBP", "slugAvg": "SLG",
    }
    mlb_label_map = {
        "K": "K", "BB": "BB", "ER": "ER", "H": "H", "R": "R",
        "HR": "HR", "IP": "IP", "PC": "PC", "ERA": "ERA",
        "AB": "AB", "RBI": "RBI", "AVG": "AVG", "OBP": "OBP",
        "SLG": "SLG",
    }

    # Tag group type so we know if this player has batting or pitching stats
    if group_type == "pitching":
        parsed["_role"] = "pitcher"
    elif group_type == "batting" and "_role" not in parsed:
        parsed["_role"] = "batter"

    use_keys = keys if keys else []
    for i, label in enumerate(labels):
        if i >= len(raw):
            break
        val = raw[i]

        # Try to map via keys first, then labels
        key = use_keys[i] if i < len(use_keys) else ""
        stat_code = mlb_key_map.get(key, mlb_label_map.get(label, ""))

        if not stat_code:
            continue

        # Handle split format like "H-AB" or "PC-ST"
        if "-" in str(val) and label in ("H-AB", "PC-ST"):
            continue  # Skip combined columns; individual columns are parsed

        try:
            if "." in str(val):
                parsed[stat_code] = float(val)
            else:
                parsed[stat_code] = int(val)
        except (ValueError, TypeError):
            parsed[stat_code] = val


def _parse_nfl_stats(parsed, labels, keys, raw, group_type):
    """Parse NFL box score stats (passing/rushing/receiving)."""
    nfl_key_map = {
        # Passing
        "completions/passingAttempts": "COMP_ATT",
        "passingYards": "PASS_YDS", "yardsPerPassAttempt": "YPA",
        "passingTouchdowns": "PASS_TD", "interceptions": "INT",
        "sacks-sackYardsLost": "SACKS",
        "adjQBR": "QBR", "QBRating": "RTG",
        # Rushing
        "rushingAttempts": "RUSH_ATT", "rushingYards": "RUSH_YDS",
        "yardsPerRushAttempt": "YPC", "rushingTouchdowns": "RUSH_TD",
        "longRushing": "LONG_RUSH",
        # Receiving
        "receptions": "REC", "receivingYards": "REC_YDS",
        "yardsPerReception": "YPR", "receivingTouchdowns": "REC_TD",
        "receivingTargets": "TARGETS", "longReception": "LONG_REC",
    }
    nfl_label_map = {
        "C/ATT": "COMP_ATT", "YDS": None,  # Ambiguous without group
        "TD": None, "INT": "INT",
    }

    # Tag role
    role_map = {"passing": "passer", "rushing": "rusher", "receiving": "receiver"}
    if group_type in role_map and "_role" not in parsed:
        parsed["_role"] = role_map[group_type]

    use_keys = keys if keys else []
    for i, label in enumerate(labels):
        if i >= len(raw):
            break
        val = raw[i]
        key = use_keys[i] if i < len(use_keys) else ""
        stat_code = nfl_key_map.get(key, "")

        if not stat_code:
            # Disambiguate labels by group type
            if label == "YDS":
                stat_code = {"passing": "PASS_YDS", "rushing": "RUSH_YDS",
                             "receiving": "REC_YDS"}.get(group_type, "")
            elif label == "TD":
                stat_code = {"passing": "PASS_TD", "rushing": "RUSH_TD",
                             "receiving": "REC_TD"}.get(group_type, "")
            else:
                stat_code = nfl_label_map.get(label, "")

        if not stat_code:
            continue

        # Handle combined formats like "15/23" or "2-14"
        if "/" in str(val) and stat_code == "COMP_ATT":
            parts = val.split("/")
            try:
                parsed["COMPLETIONS"] = int(parts[0])
                parsed["PASS_ATT"] = int(parts[1])
            except (ValueError, IndexError):
                pass
            continue

        try:
            if "." in str(val):
                parsed[stat_code] = float(val)
            else:
                parsed[stat_code] = int(val)
        except (ValueError, TypeError):
            parsed[stat_code] = val


def _parse_nhl_stats(parsed, labels, keys, raw, group_type):
    """Parse NHL box score stats (skaters + goalies)."""
    nhl_key_map = {
        "goals": "G", "assists": "A", "points": "PTS",
        "plusMinus": "+/-", "penaltyMinutes": "PIM",
        "shotsOnGoal": "SOG", "blockedShots": "BLK",
        "hits": "HIT", "faceoffWins/faceoffAttempts": "FOW",
        "timeOnIce": "TOI",
        # Goalie
        "saves-shotsAgainst": "SV_SA", "saves": "SV",
        "savePercentage": "SV%", "goalsAgainst": "GA",
    }
    nhl_label_map = {
        "G": "G", "A": "A", "PTS": "PTS", "+/-": "+/-",
        "PIM": "PIM", "SOG": "SOG", "BLK": "BLK",
        "HIT": "HIT", "TOI": "TOI",
        "SV": "SV", "SA": "SA", "SV%": "SV%", "GA": "GA",
    }

    if group_type == "goalies":
        parsed["_role"] = "goalie"
    elif "_role" not in parsed:
        parsed["_role"] = "skater"

    use_keys = keys if keys else []
    for i, label in enumerate(labels):
        if i >= len(raw):
            break
        val = raw[i]
        key = use_keys[i] if i < len(use_keys) else ""
        stat_code = nhl_key_map.get(key, nhl_label_map.get(label, ""))

        if not stat_code:
            continue

        # Handle combined save format "28-32"
        if "-" in str(val) and stat_code == "SV_SA":
            parts = val.split("-")
            try:
                parsed["SV"] = int(parts[0])
                parsed["SA"] = int(parts[1])
            except (ValueError, IndexError):
                pass
            continue

        if label == "+/-":
            try:
                parsed[stat_code] = int(str(val).replace("+", ""))
            except ValueError:
                parsed[stat_code] = 0
            continue

        try:
            if "." in str(val):
                parsed[stat_code] = float(val)
            else:
                parsed[stat_code] = int(val)
        except (ValueError, TypeError):
            parsed[stat_code] = val


def get_stat_value(stats: dict, stat_key: str, sport: str = "nba"):
    """Get a player's stat value, handling composite stats.

    Returns the numeric value or None if not found.
    """
    if not stats:
        return None

    cfg = SPORTS.get(sport, SPORTS["nba"])

    # Check composite stats first
    composites = cfg.get("composite_stats", {})
    if stat_key in composites:
        return composites[stat_key](stats)

    # Moneyline is handled separately (game result, not player stat)
    if stat_key == "ML":
        return None

    return stats.get(stat_key)


def check_moneyline(scoreboard_data: dict, team_abbr: str) -> bool | None:
    """Check if a team won their game (for moneyline bets).

    Returns True (won), False (lost), or None (game not final).
    """
    team_espn = espn_abbr(team_abbr)
    for event in scoreboard_data.get("events", []):
        comp = event.get("competitions", [{}])[0]
        competitors = comp.get("competitors", [])
        teams = [c.get("team", {}).get("abbreviation", "") for c in competitors]
        if team_espn not in teams:
            continue
        status = comp.get("status", {}).get("type", {}).get("name", "")
        if status != "STATUS_FINAL":
            return None
        # Find winner
        for c in competitors:
            if c.get("winner"):
                return c.get("team", {}).get("abbreviation", "") == team_espn
        # Fallback: compare scores
        scores = {c.get("team", {}).get("abbreviation", ""): int(c.get("score", 0))
                  for c in competitors}
        team_score = scores.get(team_espn, 0)
        opp_scores = [s for t, s in scores.items() if t != team_espn]
        if opp_scores:
            return team_score > max(opp_scores)
    return None
