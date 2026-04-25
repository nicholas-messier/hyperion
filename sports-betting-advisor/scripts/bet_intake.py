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

# ── NBA team name → ESPN abbreviation ────────────────────────

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

# ── Stat type mapping (DraftKings labels → our codes) ───────

STAT_MAP = {
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
    """Find all NBA team abbreviations mentioned in the OCR text.

    Uses word-boundary matching to avoid false positives like
    'DraftKings' matching 'kings' → SAC.
    """
    found = {}
    text_lower = text.lower()
    for name, abbr in NBA_TEAMS.items():
        # Require word boundaries to avoid substring false positives
        pattern = r"(?<![a-z])" + re.escape(name) + r"(?![a-z])"
        if re.search(pattern, text_lower):
            found[abbr] = name
    return found


# Cache for ESPN player → team lookups (avoid repeat API calls)
_player_team_cache = {}


def lookup_player_team(player_name):
    """Look up a player's current team via ESPN search API.

    Returns the ESPN team abbreviation (e.g., 'BOS') or '' if not found.
    Results are cached for the lifetime of the process.
    """
    if player_name in _player_team_cache:
        return _player_team_cache[player_name]

    if _requests is None:
        return ""

    try:
        resp = _requests.get(
            "https://site.api.espn.com/apis/common/v3/search",
            params={"query": player_name, "limit": 1, "type": "player", "sport": "basketball"},
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

    # ── Check for parlay indicator ───────────────────────────
    if re.search(r"\d+\s*[-_ ]?\s*(?:Pick|Leg)\s+Par(?:lay|l?a?y?)", text, re.I):
        is_parlay = True
    elif re.search(r"\d+[- ]?leg\s*par?l?a?y?", text, re.I):
        is_parlay = True
    elif re.search(r"[Pp]ar(?:lay|l?a?y?)\s*\+\d+", text, re.I):
        is_parlay = True

    # ── Extract odds from text (e.g., "-151", "+200") ──────────
    odds_value = None
    for line in cleaned:
        m = re.search(r"([+-]\d{3})", line)
        if m:
            val = int(m.group(1))
            if -1000 < val < -100 or 100 < val < 1000:
                odds_value = val
                break

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

        # Player Name Stat: "Jaylen Brown Points"
        player, stat = _find_player_stat(line)
        if player and stat:
            player_stats.append((player, stat, i))

    # Pair targets with player+stat by proximity (target before its player)
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
            team = list(found_teams.keys())[0] if len(found_teams) == 1 else ""
            bets.append({
                "player": player, "team": team,
                "stat": stat, "target": target, "wager": 0,
                "odds": odds_value,
            })
    elif player_stats:
        # Fallback: player+stat found but OCR missed the target line.
        # This happens when the player headshot merges with nearby text
        # during image preprocessing, garbling the "N+" target.
        # Create the bet anyway so it isn't silently dropped.
        for player, stat, ps_idx in player_stats:
            team = list(found_teams.keys())[0] if len(found_teams) == 1 else ""
            bets.append({
                "player": player, "team": team,
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
                    team = list(found_teams.keys())[0] if len(found_teams) == 1 else ""
                    bets.append({
                        "player": pname, "team": team,
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
                    team = list(found_teams.keys())[0] if len(found_teams) == 1 else ""
                    bets.append({
                        "player": current_player, "team": team,
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
                if candidate.lower() not in NBA_TEAMS and len(candidate) > 4:
                    current_player = candidate

    # ── Distribute wager ─────────────────────────────────────
    if wager and bets and not is_parlay:
        per_bet = round(wager / len(bets), 2)
        for b in bets:
            b["wager"] = per_bet

    # ── Build parlays ────────────────────────────────────────
    parlays = []
    if is_parlay and len(bets) > 1:
        legs = [f"{b['player']}:{b['stat']}:{b['target']}" for b in bets]
        parlays.append({"name": "", "legs": legs, "wager": wager or 0})

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

def _write_to_db(bets, parlays):
    """Write parsed bets to the SQLite database.

    Falls back silently if the DB module is unavailable.
    """
    if not _HAS_DB:
        return

    try:
        _init_db()

        # Record parlays first
        for parlay in parlays:
            legs = []
            for leg_str in parlay.get("legs", []):
                parts = leg_str.split(":")
                if len(parts) == 3:
                    legs.append({
                        "player": parts[0],
                        "stat": parts[1],
                        "target": int(parts[2]),
                        "team": "",
                    })
            if legs:
                _db_record_parlay(legs=legs, wager=parlay.get("wager", 0))

        # Record straight bets (skip parlay legs with wager == 0)
        for bet in bets:
            if bet.get("wager", 0) > 0:
                _db_record_bet(
                    player=bet["player"],
                    stat=bet["stat"],
                    target=bet["target"],
                    wager=bet["wager"],
                    team=bet.get("team", ""),
                    odds=bet.get("odds") or 0,
                )

        _db_sync_json()
    except Exception:
        pass  # DB write failed — JSON file is the fallback


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
    # automatically.  Only fall back to direct JSON write when DB is
    # unavailable so we don't double-write and create duplicates.
    if _HAS_DB:
        _write_to_db(bets, parlays)
        # Read back the synced JSON for the return value
        try:
            active = json.loads(BETS_FILE.read_text())
        except (json.JSONDecodeError, FileNotFoundError):
            active = {"bets": bets, "parlays": parlays}
    else:
        active = update_active_bets(bets, parlays, mode)

    return {
        "raw_text": raw_text,
        "bets": bets,
        "parlays": parlays,
        "active_bets": active,
        "ocr_file": str(ocr_path),
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

            result = process_image(img_path, mode="append")
            self._json_response(200, {
                "status": "processed",
                "bets_found": len(result["bets"]),
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
