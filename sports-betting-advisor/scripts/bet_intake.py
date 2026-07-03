#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["pillow"]
# ///
"""
bet_intake.py — Receive DraftKings bet slip screenshots and parse into active bets

Runs a lightweight HTTP server that accepts screenshots from an iOS Shortcut,
processes them with OCR (tesseract), and updates ~/.config/sports-bets/active_bets.json
so the conky live bet tracker picks them up automatically.

Usage:
    # Start the server (default port 8420)
    python3 bet_intake.py

    # Custom port and auth token
    python3 bet_intake.py --port 9000 --token mysecret

    # Process a local image file directly (no server)
    python3 bet_intake.py --file /path/to/screenshot.png

    # Clear all active bets
    python3 bet_intake.py --clear

Requires: tesseract-ocr (sudo apt install tesseract-ocr)
"""

import argparse
import json
import os
import re
import subprocess
import sys
import traceback
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path

try:
    from PIL import Image, ImageOps
except ImportError:
    Image = None

try:
    import requests as _requests
except ImportError:
    _requests = None

# SQLite database (optional — falls back to JSON-only if unavailable)
try:
    from db import init_db as _init_db, record_bet as _db_record_bet, \
        record_parlay as _db_record_parlay, sync_json as _db_sync_json
    _HAS_DB = True
except ImportError:
    _HAS_DB = False

# ── Paths ────────────────────────────────────────────────────

BETS_FILE = Path.home() / ".config" / "sports-bets" / "active_bets.json"
INTAKE_DIR = Path.home() / ".cache" / "sports-bets" / "intake"
SCRIPT_DIR = Path(__file__).resolve().parent
CONFIG_ENV = SCRIPT_DIR.parent.parent / "config.env"

# ── Team name → abbreviation (NBA + MLB) ─────────────────────

NBA_TEAMS = {
    "boston celtics": "BOS", "celtics": "BOS",
    "brooklyn nets": "BKN", "nets": "BKN",
    "new york knicks": "NYK", "knicks": "NYK",
    "philadelphia 76ers": "PHI", "76ers": "PHI", "sixers": "PHI",
    "toronto raptors": "TOR", "raptors": "TOR",
    "chicago bulls": "CHI", "bulls": "CHI",
    "cleveland cavaliers": "CLE", "cavaliers": "CLE", "cavs": "CLE",
    "detroit pistons": "DET", "pistons": "DET",
    "indiana pacers": "IND", "pacers": "IND",
    "milwaukee bucks": "MIL", "bucks": "MIL",
    "atlanta hawks": "ATL", "hawks": "ATL",
    "charlotte hornets": "CHA", "hornets": "CHA",
    "miami heat": "MIA", "heat": "MIA",
    "orlando magic": "ORL", "magic": "ORL",
    "washington wizards": "WAS", "wizards": "WAS",
    "denver nuggets": "DEN", "nuggets": "DEN",
    "minnesota timberwolves": "MIN", "timberwolves": "MIN", "wolves": "MIN",
    "oklahoma city thunder": "OKC", "thunder": "OKC",
    "portland trail blazers": "POR", "blazers": "POR",
    "utah jazz": "UTA", "jazz": "UTA",
    "golden state warriors": "GSW", "warriors": "GSW",
    "la clippers": "LAC", "los angeles clippers": "LAC", "clippers": "LAC",
    "los angeles lakers": "LAL", "la lakers": "LAL", "lakers": "LAL",
    "phoenix suns": "PHX", "suns": "PHX",
    "sacramento kings": "SAC", "kings": "SAC",
    "dallas mavericks": "DAL", "mavericks": "DAL", "mavs": "DAL",
    "houston rockets": "HOU", "rockets": "HOU",
    "memphis grizzlies": "MEM", "grizzlies": "MEM",
    "new orleans pelicans": "NOP", "pelicans": "NOP",
    "san antonio spurs": "SAS", "spurs": "SAS",
}

MLB_TEAMS = {
    "arizona diamondbacks": "ARI", "diamondbacks": "ARI", "d-backs": "ARI",
    "atlanta braves": "ATL", "braves": "ATL",
    "baltimore orioles": "BAL", "orioles": "BAL",
    "boston red sox": "BOS", "red sox": "BOS",
    "chicago cubs": "CHC", "cubs": "CHC",
    "chicago white sox": "CHW", "white sox": "CHW",
    "cincinnati reds": "CIN", "reds": "CIN",
    "cleveland guardians": "CLE", "guardians": "CLE",
    "colorado rockies": "COL", "rockies": "COL",
    "detroit tigers": "DET", "tigers": "DET",
    "houston astros": "HOU", "astros": "HOU",
    "kansas city royals": "KC", "royals": "KC",
    "la angels": "LAA", "los angeles angels": "LAA", "angels": "LAA",
    "la dodgers": "LAD", "los angeles dodgers": "LAD", "dodgers": "LAD",
    "miami marlins": "MIA", "marlins": "MIA",
    "milwaukee brewers": "MIL", "brewers": "MIL",
    "minnesota twins": "MIN", "twins": "MIN",
    "new york mets": "NYM", "mets": "NYM",
    "new york yankees": "NYY", "yankees": "NYY",
    "athletics": "ATH", "oakland athletics": "ATH",
    "philadelphia phillies": "PHI", "phillies": "PHI",
    "pittsburgh pirates": "PIT", "pirates": "PIT",
    "san diego padres": "SD", "padres": "SD",
    "san francisco giants": "SF", "giants": "SF",
    "seattle mariners": "SEA", "mariners": "SEA",
    "st. louis cardinals": "STL", "cardinals": "STL",
    "tampa bay rays": "TB", "rays": "TB",
    "texas rangers": "TEX", "rangers": "TEX",
    "toronto blue jays": "TOR", "blue jays": "TOR",
    "washington nationals": "WSH", "nationals": "WSH",
}

NFL_TEAMS = {
    "arizona cardinals": "ARI", "cardinals": "ARI",
    "atlanta falcons": "ATL", "falcons": "ATL",
    "baltimore ravens": "BAL", "ravens": "BAL",
    "buffalo bills": "BUF", "bills": "BUF",
    "carolina panthers": "CAR", "panthers": "CAR",
    "chicago bears": "CHI", "bears": "CHI",
    "cincinnati bengals": "CIN", "bengals": "CIN",
    "cleveland browns": "CLE", "browns": "CLE",
    "dallas cowboys": "DAL", "cowboys": "DAL",
    "denver broncos": "DEN", "broncos": "DEN",
    "detroit lions": "DET", "lions": "DET",
    "green bay packers": "GB", "packers": "GB",
    "houston texans": "HOU", "texans": "HOU",
    "indianapolis colts": "IND", "colts": "IND",
    "jacksonville jaguars": "JAX", "jaguars": "JAX",
    "kansas city chiefs": "KC", "chiefs": "KC",
    "las vegas raiders": "LV", "raiders": "LV",
    "los angeles chargers": "LAC", "chargers": "LAC",
    "los angeles rams": "LAR", "la rams": "LAR", "rams": "LAR",
    "miami dolphins": "MIA", "dolphins": "MIA",
    "minnesota vikings": "MIN", "vikings": "MIN",
    "new england patriots": "NE", "patriots": "NE", "pats": "NE",
    "new orleans saints": "NO", "saints": "NO",
    "new york giants": "NYG",
    "new york jets": "NYJ", "jets": "NYJ",
    "philadelphia eagles": "PHI", "eagles": "PHI",
    "pittsburgh steelers": "PIT", "steelers": "PIT",
    "seattle seahawks": "SEA", "seahawks": "SEA",
    "san francisco 49ers": "SF", "49ers": "SF", "niners": "SF",
    "tampa bay buccaneers": "TB", "buccaneers": "TB", "bucs": "TB",
    "tennessee titans": "TEN", "titans": "TEN",
    "washington commanders": "WAS", "commanders": "WAS",
}

NHL_TEAMS = {
    "anaheim ducks": "ANA", "ducks": "ANA",
    "boston bruins": "BOS", "bruins": "BOS",
    "buffalo sabres": "BUF", "sabres": "BUF",
    "calgary flames": "CGY", "flames": "CGY",
    "carolina hurricanes": "CAR", "hurricanes": "CAR",
    "chicago blackhawks": "CHI", "blackhawks": "CHI",
    "colorado avalanche": "COL", "avalanche": "COL",
    "columbus blue jackets": "CBJ", "blue jackets": "CBJ",
    "dallas stars": "DAL", "stars": "DAL",
    "detroit red wings": "DET", "red wings": "DET",
    "edmonton oilers": "EDM", "oilers": "EDM",
    "florida panthers": "FLA",
    "los angeles kings": "LA", "la kings": "LA",
    "minnesota wild": "MIN", "wild": "MIN",
    "montreal canadiens": "MTL", "canadiens": "MTL", "habs": "MTL",
    "nashville predators": "NSH", "predators": "NSH", "preds": "NSH",
    "new jersey devils": "NJ", "devils": "NJ",
    "new york islanders": "NYI", "islanders": "NYI",
    "new york rangers": "NYR",
    "ottawa senators": "OTT", "senators": "OTT", "sens": "OTT",
    "philadelphia flyers": "PHI", "flyers": "PHI",
    "pittsburgh penguins": "PIT", "penguins": "PIT", "pens": "PIT",
    "san jose sharks": "SJ", "sharks": "SJ",
    "seattle kraken": "SEA", "kraken": "SEA",
    "st. louis blues": "STL", "blues": "STL",
    "tampa bay lightning": "TB", "lightning": "TB",
    "toronto maple leafs": "TOR", "maple leafs": "TOR", "leafs": "TOR",
    "utah hockey club": "UTA",
    "vancouver canucks": "VAN", "canucks": "VAN",
    "vegas golden knights": "VGK", "golden knights": "VGK",
    "washington capitals": "WSH", "capitals": "WSH", "caps": "WSH",
    "winnipeg jets": "WPG",
}

# Combined lookup for team detection in OCR text
ALL_TEAMS = {**NBA_TEAMS, **MLB_TEAMS, **NFL_TEAMS, **NHL_TEAMS}

# Reverse lookup: abbreviation → sport
_ABBR_TO_SPORT = {}
for _name, _abbr in NBA_TEAMS.items():
    _ABBR_TO_SPORT.setdefault(_abbr, "nba")
for _name, _abbr in MLB_TEAMS.items():
    _ABBR_TO_SPORT.setdefault(_abbr, "mlb")
for _name, _abbr in NFL_TEAMS.items():
    _ABBR_TO_SPORT.setdefault(_abbr, "nfl")
for _name, _abbr in NHL_TEAMS.items():
    _ABBR_TO_SPORT.setdefault(_abbr, "nhl")


def detect_sport_from_team_name(team_name):
    """Detect sport from a full team name found in OCR text."""
    tl = team_name.lower()
    if tl in NBA_TEAMS:
        return "nba"
    if tl in MLB_TEAMS:
        return "mlb"
    if tl in NFL_TEAMS:
        return "nfl"
    if tl in NHL_TEAMS:
        return "nhl"
    return ""


# ── Stat type mapping (DraftKings labels → our codes) ───────

STAT_MAP = {
    # NBA
    "points": "PTS", "pts": "PTS", "point": "PTS",
    "rebounds": "REB", "reb": "REB", "rebound": "REB",
    "total rebounds": "REB",
    "assists": "AST", "ast": "AST", "assist": "AST",
    "steals": "STL", "stl": "STL", "steal": "STL",
    "blocks": "BLK", "blk": "BLK", "block": "BLK",
    "3-pointers": "3PT", "3-pointers made": "3PT",
    "three pointers": "3PT", "threes": "3PT", "3pt": "3PT",
    "made threes": "3PT", "three-pointers": "3PT",
    "pts + reb + ast": "PRA", "pra": "PRA",
    "points + rebounds + assists": "PRA",
    # MLB
    "strikeouts": "K", "strikeouts thrown": "K", "strikeout": "K",
    "pitcher strikeouts": "K", "k": "K",
    "hits": "H", "hit": "H", "hits allowed": "HA",
    "total bases": "TB", "bases": "TB",
    "home runs": "HR", "home run": "HR", "hrs": "HR",
    "rbis": "RBI", "rbi": "RBI", "runs batted in": "RBI",
    "runs": "R", "run": "R",
    "walks": "BB", "walk": "BB",
    "earned runs": "ER", "earned run": "ER",
    "innings pitched": "IP",
    "outs recorded": "OUTS", "pitcher outs": "OUTS",
    # NFL
    "passing yards": "PASS_YDS", "pass yards": "PASS_YDS",
    "rushing yards": "RUSH_YDS", "rush yards": "RUSH_YDS",
    "receiving yards": "REC_YDS", "rec yards": "REC_YDS",
    "passing touchdowns": "PASS_TD", "pass tds": "PASS_TD",
    "rushing touchdowns": "RUSH_TD",
    "receiving touchdowns": "REC_TD",
    "receptions": "REC", "reception": "REC",
    "completions": "COMPLETIONS", "completion": "COMPLETIONS",
    "interceptions": "INT", "interception": "INT",
    "touchdowns": "TD",
    # NHL
    "goals": "G", "goal": "G",
    "shots on goal": "SOG", "shots": "SOG",
    "saves": "SV", "save": "SV",
    "goals against": "GA",
}


# ── Config ───────────────────────────────────────────────────

def read_config():
    """Read config.env key=value pairs."""
    config = {}
    if CONFIG_ENV.exists():
        for line in CONFIG_ENV.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, val = line.partition("=")
                config[key.strip()] = val.strip().strip('"')
    return config


# ── Image preprocessing ─────────────────────────────────────

def preprocess_image(image_path):
    """Preprocess image for better OCR results.

    DraftKings bet slips may have dark backgrounds or colored text.
    We scale up 2x, convert to high-contrast black-on-white for tesseract.
    """
    if Image is None:
        return image_path

    img = Image.open(image_path)

    # Scale up for better OCR (tesseract prefers larger images)
    if img.width < 2000:
        scale = max(2, 2000 // img.width)
        img = img.resize(
            (img.width * scale, img.height * scale), Image.LANCZOS
        )

    img = img.convert("L")  # grayscale

    # If mostly dark (DK dark mode), invert so text is dark on light
    avg_pixel = sum(img.getdata()) / (img.width * img.height)
    if avg_pixel < 128:
        img = ImageOps.invert(img)

    # High-contrast threshold (200 works well for DK share cards)
    img = img.point(lambda x: 0 if x < 200 else 255)

    out = str(Path(image_path).with_suffix(".processed.png"))
    img.save(out)
    return out


# ── OCR ──────────────────────────────────────────────────────

def ocr_image(image_path):
    """Run tesseract OCR on an image. Returns extracted text.

    Tries PSM 6 (uniform block) first, then PSM 4 (variable block)
    if the first attempt returns too little text.
    """
    for psm in ["6", "4", "3"]:
        try:
            result = subprocess.run(
                ["tesseract", image_path, "stdout", "--psm", psm],
                capture_output=True, text=True, timeout=30,
            )
            text = result.stdout.strip()
            if len(text) > 20:
                return text
        except (subprocess.TimeoutExpired, FileNotFoundError) as e:
            return f"[OCR error: {e}]"
    return text if text else ""


# ── DraftKings bet slip parser ───────────────────────────────

def find_teams_in_text(text):
    """Find all team abbreviations (NBA + MLB) mentioned in the OCR text.

    Uses word-boundary matching to avoid false positives like
    'DraftKings' matching 'kings' → SAC.
    """
    found = {}
    text_lower = text.lower()
    for name, abbr in ALL_TEAMS.items():
        # Require word boundaries to avoid substring false positives
        pattern = r"(?<![a-z])" + re.escape(name) + r"(?![a-z])"
        if re.search(pattern, text_lower):
            found[abbr] = name
    return found


# Cache for ESPN player → team lookups (avoid repeat API calls)
_player_team_cache = {}


def lookup_player_team(player_name, sports=("basketball", "baseball", "football", "hockey")):
    """Look up a player's current team via ESPN search API.

    Searches across all 4 major sports by default.
    Returns the ESPN team abbreviation (e.g., 'BOS') or '' if not found.
    Results are cached for the lifetime of the process.
    """
    if player_name in _player_team_cache:
        return _player_team_cache[player_name]

    if _requests is None:
        return ""

    for sport in sports:
        try:
            resp = _requests.get(
                "https://site.api.espn.com/apis/common/v3/search",
                params={"query": player_name, "limit": 1, "type": "player", "sport": sport},
                timeout=10,
            )
            resp.raise_for_status()
            items = resp.json().get("items", [])
            if items:
                for rel in items[0].get("teamRelationships", []):
                    abbr = rel.get("core", {}).get("abbreviation", "")
                    if abbr:
                        _player_team_cache[player_name] = abbr
                        return abbr
        except Exception:
            pass

    _player_team_cache[player_name] = ""
    return ""


def _clean_ocr_line(line):
    """Strip common OCR noise characters from a line."""
    line = re.sub(r'^[\s|:@=©*«»\-.,;!?\'"{}()\[\]<>]+', "", line)
    line = re.sub(r'[\s|:@=©*«»\-.,;!?\'"{}()\[\]<>]+$', "", line)
    line = re.sub(r"\s{2,}", " ", line)
    return line.strip()


def _find_player_stat(line):
    """Try to extract (player_name, stat_code) from a line like 'Jaylen Brown Points'.

    Searches for a known stat keyword at the end of the line, then extracts
    capitalized words before it as the player name. Handles OCR noise
    before the player name (e.g., headshot artifacts).
    """
    lower = line.lower().strip()
    # Sort by length descending so "total rebounds" matches before "rebounds"
    for stat_key in sorted(STAT_MAP, key=len, reverse=True):
        if len(stat_key) < 3:
            continue
        if lower.endswith(stat_key):
            prefix = line[: len(line) - len(stat_key)].strip()
            # Extract 2-4 consecutive capitalized words
            m = re.search(
                r"([A-Z][a-zA-Z.'\-]+(?:\s+[A-Z][a-zA-Z.'\-]+){1,3})\s*$",
                prefix,
            )
            if m:
                return m.group(1).strip(), STAT_MAP[stat_key]
    return None, None


# ── Spread / run line / puck line detection ─────────────────
# DK formats spread bets as:
#   "<TeamName> +/-<num.5>"
# followed by a "Spread" / "Run Line" / "Puck Line" keyword on the
# same or next line. Examples we've seen in the wild:
#   "PHI 76ers +8.5"          (NBA spread)
#   "Boston Celtics -3.5"     (NBA spread)
#   "ORL Magic +3.5"          (parlay leg)
#   "PHI76ers+8.5"            (OCR collapsed spaces)
#   "LAD Dodgers -1.5"        (MLB run line)
#   "EDM Oilers +1.5"         (NHL puck line)

SPREAD_KEYWORDS = re.compile(
    r"\b(?:spread|run\s*line|runline|puck\s*line|puckline|point\s*spread)\b",
    re.I,
)

# Loose pattern matching "<anything> +/-<digits.optional>" where the
# spread number is reasonable (0.5 to 50.5).  Captures sign and value.
_SPREAD_NUM_RE = re.compile(
    r"([+\-~])\s*(\d{1,2}(?:\.\d)?)\b"
)


def _extract_spread_value(line):
    """Return signed spread value from a line, or None.

    Matches '+8.5' / '-3.5' / '+1.5' patterns. Treats '~' as '-' since
    Tesseract often misreads a hyphen.
    """
    for m in _SPREAD_NUM_RE.finditer(line):
        sign_raw = m.group(1)
        try:
            num = float(m.group(2))
        except ValueError:
            continue
        # Skip values that are too large (likely odds, not spreads)
        if num > 50.5 or num < 0.5:
            continue
        sign = -1 if sign_raw in ("-", "~") else 1
        return sign * num
    return None


def _find_team_in_line(line):
    """Find a team in the line by name. Handles OCR variants:
        - 'Philadelphia 76ers'    full name
        - '76ers'                 short name
        - 'PHI 76ers'             abbreviation prefix
        - 'PHI76ers'              OCR concatenated (no space)
        - 'ORL Magic'             3-letter prefix + city/nick

    Returns (team_name, team_abbr) or (None, None) if no match.
    For ambiguous abbreviations (e.g., PHI = 76ers/Phillies/Eagles/Flyers)
    the matched short name disambiguates which sport's team we use.
    """
    line_lower = line.lower()
    line_squished = re.sub(r"\s+", "", line_lower)

    # Sort longest-first so "philadelphia 76ers" matches before "76ers"
    for team_name in sorted(ALL_TEAMS, key=len, reverse=True):
        team_abbr = ALL_TEAMS[team_name]
        # Match #1: full name with word boundaries (handles "Philadelphia 76ers")
        pattern = r"(?<![a-z])" + re.escape(team_name) + r"(?![a-z])"
        if re.search(pattern, line_lower):
            return _canonical_full_name(team_name, team_abbr), team_abbr
        # Match #2: full name collapsed (handles "Philadelphia76ers" OCR garble)
        if " " in team_name:
            collapsed = team_name.replace(" ", "")
            if collapsed in line_squished:
                return _canonical_full_name(team_name, team_abbr), team_abbr
        # Match #3: abbreviation immediately followed by short name
        # (handles "PHI76ers", "ORL Magic", "TOR Raptors", etc.)
        # Only consider names that look like a city/nickname (no spaces, len >= 4)
        if " " not in team_name and len(team_name) >= 4:
            abbr_then_name = team_abbr.lower() + team_name
            if abbr_then_name in line_squished:
                return _canonical_full_name(team_name, team_abbr), team_abbr
    return None, None


def _smart_title(name):
    """Title-case a team name while preserving tokens like '76ers'."""
    parts = name.split()
    out = []
    for p in parts:
        # Keep tokens with digits as-is (e.g., "76ers", "49ers")
        if any(c.isdigit() for c in p):
            out.append(p)
        else:
            out.append(p.capitalize())
    return " ".join(out)


def _canonical_full_name(short_or_full_name, team_abbr):
    """Return the most readable full team name for the matched team.

    Disambiguates abbreviations shared across sports (PHI, ATL, etc.) by
    using the matched name's sport — so '76ers' resolves to
    'Philadelphia 76ers', not 'Philadelphia Phillies'.
    """
    # If we already matched a multi-word name, use it directly.
    if " " in short_or_full_name:
        return _smart_title(short_or_full_name)

    # Detect sport from the matched name to disambiguate shared abbreviations
    sport_lookup = {
        "nba": NBA_TEAMS, "mlb": MLB_TEAMS,
        "nfl": NFL_TEAMS, "nhl": NHL_TEAMS,
    }
    detected = detect_sport_from_team_name(short_or_full_name)
    if detected:
        # Find the spaced full-name for this abbr in the correct sport
        for full_name, abbr in sport_lookup[detected].items():
            if abbr == team_abbr and " " in full_name:
                return _smart_title(full_name)

    # Fallback: any spaced full-name with this abbr (across all sports)
    candidates = [n for n, a in ALL_TEAMS.items() if a == team_abbr and " " in n]
    return _smart_title(max(candidates, key=len) if candidates else short_or_full_name)


def _find_spread_bets(cleaned, default_odds=None):
    """Detect spread / run line / puck line bets in OCR text.

    Looks for the 'Spread' (or related) keyword as an anchor, then
    pulls the team + signed number from the same line OR the line
    immediately above. Each detected bet gets its own odds if found
    nearby, otherwise falls back to default_odds.

    Returns a list of bet dicts with stat='SPREAD', target=signed value.
    """
    spread_bets = []
    seen = set()  # (team_abbr, target) to dedupe across same/prev line matches

    for i, line in enumerate(cleaned):
        if not SPREAD_KEYWORDS.search(line):
            continue

        # Search this line and the previous one (DK often puts the
        # spread number above the "Spread" label on a separate line).
        candidates = [line]
        if i > 0:
            candidates.insert(0, cleaned[i - 1])

        for cand in candidates:
            spread_val = _extract_spread_value(cand)
            if spread_val is None:
                continue
            team_name, team_abbr = _find_team_in_line(cand)
            if not team_abbr:
                continue
            key = (team_abbr, spread_val)
            if key in seen:
                continue
            seen.add(key)

            # Try to find leg-specific odds AFTER the spread number.
            # American odds for spreads are typically -110 to +200.
            # OCR may render '-' as '~' or 'N' (e.g., '~108' or 'N110').
            # default_odds is the slip-level fallback — caller passes
            # None for parlays (where it'd be the combined parlay odds,
            # not the leg odds) and passes the bet odds for singles.
            odds_value = _extract_spread_leg_odds(cand, spread_val) or default_odds

            spread_bets.append({
                "player": team_name,
                "team": team_abbr,
                "stat": "SPREAD",
                "target": spread_val,
                "wager": 0,
                "odds": odds_value,
            })
            break  # Only one bet per "Spread" anchor

    return spread_bets


def _extract_spread_leg_odds(line, spread_val):
    """Find the odds value for a spread bet leg.

    DK formats lines like 'ORL Magic +3.5 -108' where the odds (-108)
    follow the spread (+3.5). OCR may garble '-' as '~' or 'N'.
    Returns signed integer odds or None.
    """
    # Locate the spread value in the line so we only look AFTER it
    spread_str_int = str(int(abs(spread_val)))
    spread_str_dec = f"{abs(spread_val):.1f}"  # e.g., "3.5" or "8.5"
    after_idx = -1
    for needle in (spread_str_dec, spread_str_int + ".5", spread_str_int):
        idx = line.find(needle)
        if idx >= 0:
            after_idx = idx + len(needle)
            break
    suffix = line[after_idx:] if after_idx >= 0 else line

    # Match patterns: -108 / +119 / ~108 / N110 / -110 etc.
    # 100-999 numeric range filters out random 2-digit noise.
    odds_re = re.compile(r"(?<!\d)(?P<sign>[+\-~Nn])\s*(?P<num>\d{2,3})(?!\d)")
    for m in odds_re.finditer(suffix):
        try:
            num = int(m.group("num"))
            if not (100 <= num <= 999):
                continue
        except ValueError:
            continue
        sign_raw = m.group("sign")
        sign = -1 if sign_raw in ("-", "~", "N", "n") else 1
        return sign * num
    return None


def _derive_odds_from_payout(wager, to_pay):
    """Convert wager + total payout into American odds.

    DK shows "Wager: $5.00" and "To Pay: $42.50" on every slip. The
    To Pay reflects the actual odds DK is honoring — including any
    profit boost — so this is the most reliable odds source.

    Returns signed integer American odds, or None if inputs are missing
    or inconsistent (e.g., to_pay <= wager which would imply a non-bet).
    """
    if not wager or not to_pay:
        return None
    if to_pay <= wager:
        return None
    profit = to_pay - wager
    if profit >= wager:
        # Positive odds: profit / wager * 100
        return int(round(profit / wager * 100))
    else:
        # Negative odds: -wager / profit * 100
        return -int(round(wager / profit * 100))


def _score_ocr_text(text):
    """Score OCR text by how many bet-relevant components it contains.

    Used to compare OCR results from different image preprocessing.
    Higher score = more parseable bet data found.
    """
    score = 0
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        cleaned = _clean_ocr_line(line)
        # Target patterns: "14+", "25+"
        if re.search(r"\b\d{1,3}\+", cleaned):
            score += 3
        # Odds patterns: "-151", "+200"
        if re.search(r"[+-]\d{3}", cleaned):
            score += 2
        # Player + stat lines
        p, s = _find_player_stat(cleaned)
        if p and s:
            score += 3
        # Wager amount
        if re.search(r"[Ww]ager.*\$\d+", line):
            score += 2
        # Spread bet patterns
        if SPREAD_KEYWORDS.search(cleaned):
            score += 2
        if _extract_spread_value(cleaned) is not None:
            score += 1
    return score


def parse_betslip(text):
    """Parse DraftKings bet slip OCR text into structured bets.

    Handles DraftKings share card format (most common from iPhone shares):
        25+
        Jaylen Brown Points

    Traditional Over/Under format:
        Jaylen Brown Over 24.5 Points

    And multi-line Over/Under:
        Jaylen Brown
        Over 24.5 Points

    Returns (bets_list, parlays_list).
    """
    raw_lines = [l.strip() for l in text.splitlines() if l.strip()]
    cleaned = [_clean_ocr_line(l) for l in raw_lines]
    found_teams = find_teams_in_text(text)

    bets = []
    is_parlay = False
    wager = None

    # ── Scan for wager amount ────────────────────────────────
    for line in cleaned:
        m = re.search(r"[Ww]ager[:\s]*\$(\d+\.?\d*)", line)
        if m:
            wager = float(m.group(1))
            break
    if wager is None:
        for line in cleaned:
            m = re.search(r"\$(\d+\.?\d*)", line)
            if m and re.search(r"wager|stake|bet|risk|total", line, re.I):
                wager = float(m.group(1))
                break

    # ── Scan for "To Pay" amount (used to derive boosted odds) ─
    to_pay = None
    for line in cleaned:
        m = re.search(r"[Tt]o\s*[Pp]ay[:\s]*\$(\d+\.?\d*)", line)
        if m:
            to_pay = float(m.group(1))
            break

    # ── Check for parlay indicator ───────────────────────────
    if re.search(r"\d+\s*[-_ ]?\s*(?:Pick|Leg)\s+Par(?:lay|l?a?y?)", text, re.I):
        is_parlay = True
    elif re.search(r"\d+[- ]?leg\s*par?l?a?y?", text, re.I):
        is_parlay = True
    elif re.search(r"[Pp]ar(?:lay|l?a?y?)\s*\+\d+", text, re.I):
        is_parlay = True

    # ── Determine the slip's effective odds ──────────────────
    # Prefer odds derived from wager + To Pay (this captures profit
    # boosts — DK shows the boosted "To Pay" but lists the original
    # odds too). Fall back to scanning text for "[+-]ddd" patterns.
    odds_value = _derive_odds_from_payout(wager, to_pay)
    if odds_value is None:
        for line in cleaned:
            m = re.search(r"([+-]\d{3,4})", line)
            if m:
                val = int(m.group(1))
                if -10000 < val < -100 or 100 < val < 10000:
                    odds_value = val
                    break

    # ── Strategy 0a: Detect spread / run line / puck line bets ─
    # Look for "Spread"/"Run Line"/"Puck Line" keyword near a team
    # and signed spread number (e.g., "PHI 76ers +8.5 / Spread").
    # For parlays, don't pass default_odds since that'd be the parlay's
    # combined odds, not the leg's odds. Each leg's odds must come
    # from inline OCR or stay None for manual review.
    spread_default_odds = None if is_parlay else odds_value
    spread_bets = _find_spread_bets(cleaned, default_odds=spread_default_odds)

    # ── Strategy 0b: Detect team moneyline legs ────────────────
    # Look for "TeamName" near "Moneyline" / "Money Line" / "ML" text.
    # OCR may split "Moneyline" across lines (e.g., "Mone ne" / "yline").
    # Skip ML detection if we already have spread bets — DK rarely
    # mixes spread + ML for the same team in one slip, and the parser
    # might pick up "ML" as a substring of OCR noise.
    moneyline_bets = []
    full_text_lower = " ".join(cleaned).lower()
    has_moneyline = bool(re.search(r"mone.{0,10}l[il]?ne|moneyline|money\s*line", full_text_lower))
    if has_moneyline and not spread_bets:
        for team_name, team_abbr in ALL_TEAMS.items():
            pattern = r"(?<![a-z])" + re.escape(team_name) + r"(?![a-z])"
            if re.search(pattern, full_text_lower):
                moneyline_bets.append({
                    "player": team_name.title(), "team": team_abbr,
                    "stat": "ML", "target": 0, "wager": 0,
                    "odds": odds_value,
                })
                break  # Only one ML leg expected per slip

    # ── Strategy 1: DK share card format (N+ / Player Stat) ─
    # Collect targets (N+) and player+stat lines, pair them in order.
    targets = []        # (target_num, line_index)
    player_stats = []   # (player, stat_code, line_index)

    for i, line in enumerate(cleaned):
        if not line:
            continue

        # Target: "25+" or "10+" — a number followed by + (with optional noise)
        t_match = re.search(r"(?:^|[=\s])(\d+)\+", line)
        if t_match and len(line) < 30:
            targets.append((int(t_match.group(1)), i))

        # Player Name Stat: "Jaylen Brown Points" or "Tyler Glasnow Strikeouts Thrown"
        player, stat = _find_player_stat(line)
        if player and stat:
            player_stats.append((player, stat, i))

    # Pair targets with player+stat by proximity (target before its player).
    # Note: we deliberately leave team="" here for player props and rely on
    # the ESPN lookup later. Auto-assigning the only OCR-detected team is
    # wrong for multi-game parlays where (e.g.) the spread is on NYK but
    # one of the player-prop legs is on a player from a different team.
    if targets and player_stats:
        used = set()
        for player, stat, ps_idx in player_stats:
            best_t = None
            best_dist = float("inf")
            for ti, (tval, t_idx) in enumerate(targets):
                if ti in used:
                    continue
                dist = ps_idx - t_idx
                if 0 < dist < best_dist:
                    best_t = ti
                    best_dist = dist
            target = targets[best_t][0] if best_t is not None else 0
            if best_t is not None:
                used.add(best_t)
            bets.append({
                "player": player, "team": "",
                "stat": stat, "target": target, "wager": 0,
                "odds": odds_value,
            })
    elif player_stats:
        # Fallback: player+stat found but OCR missed the target line.
        # This happens when the player headshot merges with nearby text
        # during image preprocessing, garbling the "N+" target.
        # Create the bet anyway so it isn't silently dropped.
        for player, stat, ps_idx in player_stats:
            bets.append({
                "player": player, "team": "",
                "stat": stat, "target": 0, "wager": 0,
                "odds": odds_value,
            })
            sys.stderr.write(
                f"[intake] WARNING: No target found for {player} {stat}"
                f" — bet created with target=0, needs manual update\n"
            )

    # ── Strategy 2: Traditional Over/Under format (fallback) ─
    if not bets:
        ou_pattern = re.compile(
            r"(?:Over|Under|O|U)\s*(\d+\.?\d*)\s+([A-Za-z][A-Za-z+ ]*)",
            re.I,
        )
        current_player = None
        for line in cleaned:
            if not line:
                continue
            if re.match(
                r"^(My Bets?|Active|Settled|Pending|Bet Slip|DraftKings|Share|"
                r"Same Game|Odds|Payout|To Win|Potential|Leg |IF |Boost|Promo)",
                line, re.I,
            ):
                continue

            # Combined: "Player Name Over X.X Stat"
            combined = re.match(
                r"([A-Z][a-zA-Z.'\-]+(?:\s+[A-Z][a-zA-Z.'\-]+)+)\s+"
                r"(?:Over|Under|O|U)\s*(\d+\.?\d*)\s+"
                r"([A-Za-z][A-Za-z+ ]*)",
                line,
            )
            if combined:
                pname = combined.group(1).strip()
                target_raw = float(combined.group(2))
                stat_text = combined.group(3).strip().lower().rstrip("s ")
                sval = STAT_MAP.get(stat_text) or STAT_MAP.get(stat_text + "s", "")
                if sval:
                    target = int(target_raw) + (1 if target_raw != int(target_raw) else 0)
                    bets.append({
                        "player": pname, "team": "",
                        "stat": sval, "target": target, "wager": 0,
                    })
                    current_player = None
                    continue

            # Standalone Over/Under line
            ou_match = ou_pattern.match(line)
            if ou_match and current_player:
                target_raw = float(ou_match.group(1))
                stat_text = ou_match.group(2).strip().lower().rstrip("s ")
                sval = STAT_MAP.get(stat_text) or STAT_MAP.get(stat_text + "s", "")
                if sval:
                    target = int(target_raw) + (1 if target_raw != int(target_raw) else 0)
                    bets.append({
                        "player": current_player, "team": "",
                        "stat": sval, "target": target, "wager": 0,
                    })
                    current_player = None
                    continue

            # Player name line
            name_match = re.match(
                r"^([A-Z][a-zA-Z.'\-]+(?:\s+[A-Z][a-zA-Z.'\-]+){1,3})$", line
            )
            if name_match:
                candidate = name_match.group(1)
                if candidate.lower() not in ALL_TEAMS and len(candidate) > 4:
                    current_player = candidate

    # ── Merge spread + moneyline legs ────────────────────────
    if spread_bets:
        bets = spread_bets + bets
    if moneyline_bets:
        bets = moneyline_bets + bets

    # ── Distribute wager ─────────────────────────────────────
    if wager and bets and not is_parlay:
        per_bet = round(wager / len(bets), 2)
        for b in bets:
            b["wager"] = per_bet

    # ── Build parlays ────────────────────────────────────────
    parlays = []
    if is_parlay and len(bets) > 1:
        legs = [f"{b['player']}:{b['stat']}:{b['target']}" for b in bets]
        parlays.append({
            "name": "",
            "legs": legs,
            "wager": wager or 0,
            "odds": odds_value or 0,
        })

    # ── Fill in missing teams via ESPN player search ─────────
    # Also clean player names: OCR noise from headshot areas can
    # prepend short garbage words (e.g., "Ad Nikola Jokic").
    # If the full name fails ESPN lookup, try trimming leading words.
    for bet in bets:
        if not bet.get("team"):
            team = lookup_player_team(bet["player"])
            if team:
                bet["team"] = team
            else:
                words = bet["player"].split()
                for start in range(1, len(words) - 1):
                    trimmed = " ".join(words[start:])
                    team = lookup_player_team(trimmed)
                    if team:
                        bet["player"] = trimmed
                        bet["team"] = team
                        break

    # ── Detect sport for each bet ────────────────────────────
    # Use team abbreviation → sport lookup, then fall back to
    # detected team names from OCR text.
    detected_sport = ""
    if found_teams:
        for team_name in found_teams.values():
            detected_sport = detect_sport_from_team_name(team_name)
            if detected_sport:
                break

    for bet in bets:
        if not bet.get("sport"):
            abbr = bet.get("team", "")
            bet["sport"] = _ABBR_TO_SPORT.get(abbr, detected_sport or "nba")

    return bets, parlays


# ── Bets file management ────────────────────────────────────

def update_active_bets(new_bets, new_parlays, mode="append"):
    """Update ~/.config/sports-bets/active_bets.json.

    mode='append' adds to existing bets; mode='replace' overwrites.
    """
    BETS_FILE.parent.mkdir(parents=True, exist_ok=True)

    if mode == "append" and BETS_FILE.exists():
        try:
            existing = json.loads(BETS_FILE.read_text())
        except json.JSONDecodeError:
            existing = {"bets": [], "parlays": []}
        all_bets = existing.get("bets", []) + new_bets
        all_parlays = existing.get("parlays", []) + new_parlays
    else:
        all_bets = new_bets
        all_parlays = new_parlays

    data = {"bets": all_bets, "parlays": all_parlays}
    BETS_FILE.write_text(json.dumps(data, indent=4) + "\n")
    return data


# ── Database integration ─────────────────────────────────────

def _parse_target(target_str):
    """Parse a leg target string into int or float.

    Player prop targets are typically integers ('25', '10').
    Spread / run line / puck line targets are floats ('-12.5', '+8.5').
    """
    try:
        return int(target_str)
    except ValueError:
        return float(target_str)


def _write_to_db(bets, parlays):
    """Write parsed bets to the SQLite database.

    Returns True if the write succeeded (or was skipped because no DB
    module is available — a no-op success). Returns False if a real
    exception occurred during the write so the caller can fall back to
    the JSON-only path.
    """
    if not _HAS_DB:
        return False

    try:
        _init_db()

        # Record parlays first
        for parlay in parlays:
            legs = []
            for leg_str in parlay.get("legs", []):
                parts = leg_str.split(":")
                if len(parts) == 3:
                    # Find matching bet to get team and sport
                    p_name, p_stat = parts[0], parts[1]
                    p_target = _parse_target(parts[2])
                    leg_team = ""
                    leg_sport = "nba"
                    for b in bets:
                        if (b["player"] == p_name and b["stat"] == p_stat
                                and b["target"] == p_target):
                            leg_team = b.get("team", "")
                            leg_sport = b.get("sport", "nba")
                            break
                    legs.append({
                        "player": p_name,
                        "stat": p_stat,
                        "target": p_target,
                        "team": leg_team,
                        "sport": leg_sport,
                    })
            if legs:
                _db_record_parlay(legs=legs, wager=parlay.get("wager", 0),
                                  odds=parlay.get("odds", 0))

        # Record straight bets (skip parlay legs with wager == 0)
        for bet in bets:
            if bet.get("wager", 0) > 0:
                _db_record_bet(
                    player=bet["player"],
                    stat=bet["stat"],
                    target=bet["target"],
                    wager=bet["wager"],
                    team=bet.get("team", ""),
                    sport=bet.get("sport", "nba"),
                    odds=bet.get("odds") or 0,
                )

        _db_sync_json()
        return True
    except Exception as e:
        sys.stderr.write(f"[intake] DB write failed: {e!r}\n")
        traceback.print_exc(file=sys.stderr)
        return False


# ── Full pipeline ────────────────────────────────────────────

def process_image(image_path, mode="append"):
    """Preprocess → OCR → parse → update active bets. Returns result dict."""
    INTAKE_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    # Preprocess
    processed = preprocess_image(image_path)

    # OCR — try both processed and original image, pick the one
    # with more parseable bet data (targets, player names, odds).
    # The preprocessed image can mangle numbers near player headshots,
    # so the original sometimes produces better results for those regions.
    processed_text = ocr_image(processed)
    original_text = ocr_image(image_path) if processed != image_path else ""

    proc_score = _score_ocr_text(processed_text)
    orig_score = _score_ocr_text(original_text) if original_text else -1

    if original_text and orig_score > proc_score:
        raw_text = original_text
    else:
        raw_text = processed_text

    # Save raw OCR output for debugging
    ocr_path = INTAKE_DIR / f"{timestamp}_ocr.txt"
    ocr_path.write_text(raw_text)

    # Parse bets from text
    bets, parlays = parse_betslip(raw_text)

    # Write to SQLite DB (primary) — sync_json() updates active_bets.json
    # automatically. If DB write fails (or DB module missing), fall back
    # to writing the JSON file directly so the bet is still persisted.
    db_ok = _write_to_db(bets, parlays) if _HAS_DB else False
    if db_ok:
        try:
            active = json.loads(BETS_FILE.read_text())
        except (json.JSONDecodeError, FileNotFoundError):
            active = {"bets": bets, "parlays": parlays}
    else:
        if _HAS_DB:
            sys.stderr.write(
                "[intake] DB write failed — falling back to JSON write\n"
            )
        active = update_active_bets(bets, parlays, mode)

    return {
        "raw_text": raw_text,
        "bets": bets,
        "parlays": parlays,
        "active_bets": active,
        "ocr_file": str(ocr_path),
        "db_ok": db_ok,
    }


# ── HTTP server ──────────────────────────────────────────────

class BetIntakeHandler(BaseHTTPRequestHandler):
    """Minimal HTTP handler for receiving bet slip images."""

    auth_token = ""

    def _check_auth(self):
        if not self.auth_token:
            return True
        auth = self.headers.get("Authorization", "")
        return auth == f"Bearer {self.auth_token}"

    def _json_response(self, code, data):
        body = json.dumps(data, indent=2).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    # GET ──────────────────────────────────────────────────────

    def do_GET(self):
        if self.path == "/health":
            self._json_response(200, {"status": "ok"})
            return

        if not self._check_auth():
            self._json_response(401, {"error": "unauthorized"})
            return

        if self.path == "/bets":
            if BETS_FILE.exists():
                data = json.loads(BETS_FILE.read_text())
            else:
                data = {"bets": [], "parlays": []}
            self._json_response(200, data)
        else:
            self._json_response(404, {"error": "not found"})

    # POST ─────────────────────────────────────────────────────

    def do_POST(self):
        if not self._check_auth():
            self._json_response(401, {"error": "unauthorized"})
            return

        length = int(self.headers.get("Content-Length", 0))
        if length == 0:
            self._json_response(400, {"error": "empty body"})
            return

        body = self.rfile.read(length)

        if self.path == "/upload":
            # Save image and process
            INTAKE_DIR.mkdir(parents=True, exist_ok=True)
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")

            ext = ".png"
            if body[:2] == b"\xff\xd8":
                ext = ".jpg"

            img_path = str(INTAKE_DIR / f"{ts}{ext}")
            Path(img_path).write_bytes(body)

            try:
                result = process_image(img_path, mode="append")
            except Exception as e:
                sys.stderr.write(f"[intake] process_image failed: {e!r}\n")
                traceback.print_exc(file=sys.stderr)
                self._json_response(500, {
                    "status": "error",
                    "error": str(e),
                    "image_saved": img_path,
                })
                return

            bets_found = len(result["bets"])
            parlays_found = len(result["parlays"])
            persisted = (
                bool(result.get("active_bets", {}).get("bets"))
                or bool(result.get("active_bets", {}).get("parlays"))
            )

            if bets_found == 0 and parlays_found == 0:
                # Nothing parseable — return 422 so the client knows
                # the upload was received but no bets were extracted.
                self._json_response(422, {
                    "status": "no_bets_parsed",
                    "bets_found": 0,
                    "raw_text_preview": result["raw_text"][:500],
                    "ocr_file": result.get("ocr_file"),
                })
                return

            self._json_response(200, {
                "status": "processed" if persisted else "parsed_not_saved",
                "bets_found": bets_found,
                "parlays_found": parlays_found,
                "db_ok": result.get("db_ok", False),
                "bets": result["bets"],
                "parlays": result["parlays"],
                "raw_text_preview": result["raw_text"][:500],
            })

        elif self.path == "/bets":
            # Accept JSON bets directly (manual entry)
            try:
                data = json.loads(body)
            except json.JSONDecodeError:
                self._json_response(400, {"error": "invalid JSON"})
                return
            mode = data.pop("mode", "append")
            new_bets = data.get("bets", [])
            new_parlays = data.get("parlays", [])
            _write_to_db(new_bets, new_parlays)
            result = update_active_bets(new_bets, new_parlays, mode)
            self._json_response(200, {"status": "updated", "active_bets": result})
        else:
            self._json_response(404, {"error": "not found"})

    # DELETE ────────────────────────────────────────────────────

    def do_DELETE(self):
        if not self._check_auth():
            self._json_response(401, {"error": "unauthorized"})
            return

        if self.path == "/bets":
            result = update_active_bets([], [], "replace")
            self._json_response(200, {"status": "cleared"})
        else:
            self._json_response(404, {"error": "not found"})

    def log_message(self, fmt, *args):
        ts = datetime.now().strftime("%H:%M:%S")
        sys.stderr.write(f"[{ts}] {fmt % args}\n")


# ── CLI ──────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="DraftKings bet slip intake — HTTP server + OCR pipeline"
    )
    parser.add_argument(
        "--port", type=int, default=8420,
        help="Server port (default: 8420, or INTAKE_PORT env var)",
    )
    parser.add_argument(
        "--token", default=None,
        help="Auth token (or set INTAKE_TOKEN env var)",
    )
    parser.add_argument(
        "--file", type=str,
        help="Process a local image file directly (no server)",
    )
    parser.add_argument(
        "--clear", action="store_true",
        help="Clear all active bets and exit",
    )
    parser.add_argument(
        "--mode", choices=["replace", "append"], default="append",
        help="How to update bets when using --file (default: append)",
    )
    args = parser.parse_args()

    # Read token from args, env, or config.env
    config = read_config()
    token = (
        args.token
        or os.environ.get("INTAKE_TOKEN", "")
        or config.get("INTAKE_TOKEN", "")
    )
    port = args.port if args.port != 8420 else int(
        os.environ.get("INTAKE_PORT", config.get("INTAKE_PORT", "8420"))
    )

    # --clear: wipe bets and exit
    if args.clear:
        update_active_bets([], [], "replace")
        print("Active bets cleared.")
        return

    # --file: process a single image and exit
    if args.file:
        if not Path(args.file).exists():
            print(f"File not found: {args.file}", file=sys.stderr)
            sys.exit(1)
        result = process_image(args.file, args.mode)
        print(json.dumps(result, indent=2))
        return

    # Verify tesseract is installed
    try:
        subprocess.run(["tesseract", "--version"], capture_output=True, check=True)
    except FileNotFoundError:
        print("ERROR: tesseract-ocr not installed.", file=sys.stderr)
        print("  sudo apt install tesseract-ocr", file=sys.stderr)
        sys.exit(1)

    # Start HTTP server
    BetIntakeHandler.auth_token = token
    server = HTTPServer(("0.0.0.0", port), BetIntakeHandler)

    print(f"Bet intake server running on port {port}")
    print(f"  Server IP: http://192.168.0.16:{port}")
    if token:
        print(f"  Auth token: Bearer {token[:4]}{'*' * (len(token) - 4)}")
    else:
        print("  WARNING: No auth token — set INTAKE_TOKEN in config.env")
    print()
    print("Endpoints:")
    print(f"  POST   /upload  — Upload bet slip image (OCR + parse)")
    print(f"  POST   /bets    — Submit bets as JSON directly")
    print(f"  GET    /bets    — View current active bets")
    print(f"  DELETE /bets    — Clear all active bets")
    print(f"  GET    /health  — Health check")
    print()
    print("Waiting for bet slips... (Ctrl+C to stop)")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServer stopped.")
        server.server_close()


if __name__ == "__main__":
    main()
