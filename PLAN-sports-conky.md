# Plan: Dedicated Sports Conky Panel

**Created:** April 19, 2026
**Status:** Ready for implementation
**Goal:** Extract the sports section from the clock panel into its own dedicated conky window (middle position), expanded with full bet tracking and bankroll status.

---

## Current Layout (right-to-left from screen edge)

| Panel | gap_x | Width | Content |
|-------|-------|-------|---------|
| Clock | 20 | 320 | Clock, timezones, weather, **sports** |
| System | 360 | 320-420 | CPU, disk, services |

## New Layout (right-to-left)

| Panel | gap_x | Width | Content |
|-------|-------|-------|---------|
| Clock | 20 | 320 | Clock, timezones, weather (sports removed) |
| **Sports** | **360** | **320** | **Playoffs + open bets + bankroll** |
| System | **700** | 320-420 | CPU, disk, services (shifted left) |

Spacing is 20px between all panels (same as current gap between clock and system).

---

## Sports Panel Sections

### Section 1: NBA Playoffs (top)

Reuse the existing `fetch_playoff_series()` logic from `conky/update_sports.py`:

- Header: "NBA Playoffs" with configured team record
- All current-round series matchups with win counts
- Color coding:
  - Orange: live games (with score + quarter)
  - Light blue: your team's series
  - Yellow: series with active bet teams
  - Gray: series with no upcoming game (TBD)
- Next game date/time for each series

### Section 2: Open Bets (middle)

Read `~/.config/sports-bets/active_bets.json` for all active bets:

- Header: "Active Bets" with total amount in play
- Each straight bet listed: Player, Stat, Target, Wager
  - Format: `$6 Jokic 11+ REB`
- Parlay legs grouped and labeled
- **During live games:** switch to progress display
  - Green checkmark: bet has hit (current >= target)
  - Yellow diamond: bet in progress (show current/target)
  - Gray question mark: player not yet in box score
  - Parlay hit status (e.g., "1/2 legs")
- **When no bets are active:** show "No active bets"

### Section 3: Bankroll Status (bottom)

Read `~/.config/sports-bets/bankroll.json` for bankroll data:

- Separator line
- Balance: current unwagered balance (green if > starting, red if below)
- Net P/L: +$12.33 (green) or -$5.00 (red) vs total deposited
- Record: 3W - 0L (win count - loss count)
- In Play: amount currently wagered on active bets

Example output:
```
--------------------------------
Bankroll: $36.33
Net: +$12.33  Record: 3-0
In Play: $16.00
```

---

## Implementation Details

### Step 1: Create `~/.config/sports-bets/bankroll.json`

New structured JSON file tracking bankroll state. Seeded from current values in `sports-betting-advisor/data/celtics_postseason_2026.md`:

```json
{
    "starting_bankroll": 20.00,
    "total_deposited": 40.00,
    "current_balance": 36.33,
    "in_play": 16.00,
    "wins": 3,
    "losses": 0
}
```

This file is the machine-readable data source. Updated by the betting advisor (Devin "Juan Consuelo" personality) alongside the markdown strategy doc during betting sessions.

The `install.sh` script should create this file with defaults if it doesn't exist (similar to how it creates `active_bets.json`).

---

### Step 2: Create `conky/update_sports_dashboard.py`

New Python script following the same pattern as `conky/update_sports.py`:

- PEP 723 inline dependency metadata (`requests`)
- Called by conky via `${execpi 60 python3 __BIN_DIR__/conky/update_sports_dashboard.py}`
- Outputs conky-formatted text (with `${color}` tags) to stdout

**Structure:**

```python
#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["requests"]
# ///
"""
update_sports_dashboard.py — Full sports panel for conky

Outputs three sections:
1. NBA Playoffs — series matchups, scores, next games
2. Active Bets — current open bets with live progress
3. Bankroll Status — balance, net P/L, W-L record

Called from conky's execpi every 60 seconds:
    ${execpi 60 python3 /path/to/update_sports_dashboard.py}
"""
```

**Logic flow:**

1. Read `config.env` for team config
2. Fetch playoff series data (cached 5 min, same as existing)
3. Print playoff section (reuse `playoff_output()` logic)
4. Print separator
5. Read `active_bets.json`
6. If bets exist AND matching games are live → show live progress (reuse `eval_bet()` / ESPN box score logic)
7. If bets exist but no live games → show static bet list
8. If no bets → show "No active bets"
9. Print separator
10. Read `bankroll.json` → print bankroll summary

**Key functions to extract/share from `update_sports.py`:**
- `fetch_playoff_series()` — playoff data fetching and caching
- `format_game_time()` — time formatting
- `load_bets()` — read active_bets.json
- `eval_bet()` — evaluate bet progress against live stats
- `get_scoreboard()` / `find_bet_games()` / `get_player_stats()` — ESPN API calls

You can either import from `update_sports.py` or duplicate the relevant functions (duplicating is simpler given that `update_sports.py` will still be needed during the transition, and both scripts are self-contained).

---

### Step 3: Create `conky/conky-sports.conf`

New conky configuration template:

```lua
conky.config = {
    alignment = "top_right",
    gap_x = 360,
    gap_y = 20,

    update_interval = 2,
    total_run_times = 0,

    use_xft = true,
    font = "JetBrainsMono Nerd Font:size=12",
    use_spacer = "none",

    minimum_width = 320,
    minimum_height = 450,
    maximum_width = 320,
    text_buffer_size = 8192,
    override_utf8_locale = true,

    own_window = true,
    own_window_type = "desktop",
    own_window_transparent = false,
    own_window_argb_visual = true,
    own_window_argb_value = 180,
    own_window_colour = "#000000",

    own_window_hints = "undecorated,sticky,skip_taskbar,skip_pager,below",

    draw_shades = false,
    draw_outline = false,
    draw_borders = false,
    draw_graph_borders = false,

    double_buffer = true,
};

conky.text = [[
${execpi 60 python3 __BIN_DIR__/conky/update_sports_dashboard.py}
]];
```

Notes:
- `text_buffer_size = 8192` — larger than clock panel (4096) since sports output can be lengthy with multiple series + bets
- Same visual styling (font, colors, transparency, window hints) as other panels
- Single `execpi` call handles all content

---

### Step 4: Modify `conky/conky-clock.conf`

Remove the sports section from the clock panel. Change lines 43-45 from:

```
${color #888888}--------------------------------${color}
${execpi 60 python3 __BIN_DIR__/conky/update_sports.py}
]];
```

To:

```
]];
```

This makes the clock panel end after the weather section. The trailing separator above weather can stay since weather is now the bottom section.

---

### Step 5: Modify `conky/conky-system.conf`

Change `gap_x` from `360` to `700`:

```lua
gap_x = 700,
```

This shifts the system panel left to make room for the new Sports panel in the middle.

---

### Step 6: Update `conky/install.sh`

Add the following changes:

1. **Deploy sports config** — Add `conky-sports.conf` to the template deployment loop (line ~170):
   ```bash
   for conf in conky-clock.conf conky-system.conf conky-sports.conf; do
   ```

2. **Make script executable** (line ~192):
   ```bash
   chmod +x "$SCRIPT_DIR/update_sports_dashboard.py"
   ```

3. **Create bankroll.json** if it doesn't exist (after the active_bets.json section, ~line 276):
   ```bash
   BANKROLL_FILE="$BETS_DIR/bankroll.json"
   if [ ! -f "$BANKROLL_FILE" ]; then
       cat > "$BANKROLL_FILE" <<'BANKEOF'
   {
       "starting_bankroll": 0,
       "total_deposited": 0,
       "current_balance": 0,
       "in_play": 0,
       "wins": 0,
       "losses": 0
   }
   BANKEOF
       ok "Created empty bankroll config at $BANKROLL_FILE"
   else
       ok "Bankroll config already exists at $BANKROLL_FILE"
   fi
   ```

4. **Add XDG autostart entry** for the Sports panel:
   ```bash
   cat > "$AUTOSTART_DIR/Sports Conky.desktop" <<EOF
   [Desktop Entry]
   Type=Application
   Exec=conky -d -c $CONKY_DIR/conky-sports.conf
   X-GNOME-Autostart-enabled=true
   NoDisplay=false
   Hidden=false
   Name[en_US]=Sports Conky
   Comment[en_US]=Conky sports dashboard (middle panel)
   X-GNOME-Autostart-Delay=3
   EOF
   ```

5. **Start sports panel** in the "start conky" section:
   ```bash
   conky -c "$CONKY_DIR/conky-sports.conf" -d
   ```

6. **Update final output** to list the new files.

---

### Step 7: Update `conky/README.md`

- Add `conky-sports.conf` and `update_sports_dashboard.py` to the Files table
- Update the layout description to show three panels
- Add Manual Start command for the sports panel
- Document `bankroll.json` format under a new "Bankroll Tracking" section
- Mention that the betting advisor updates `bankroll.json`

---

### Step 8: Update `sports-betting-advisor/AGENTS.md`

Add to the "What you do" section:

```
- **Update `~/.config/sports-bets/bankroll.json`** whenever you update the bankroll tracker
  in the strategy doc. This JSON file is read by the conky sports dashboard for live display.
  Fields: starting_bankroll, total_deposited, current_balance, in_play, wins, losses.
```

This ensures the data stays in sync when the advisor runs betting sessions.

---

### Step 9: Update root `README.md`

Change the conky description in the Tools table from:
```
Desktop dashboard widgets — clock, weather, sports schedule, system stats
```
To:
```
Desktop dashboard widgets — clock/weather, sports/betting dashboard, system stats
```

---

## Data Sources & Files

| File | Purpose | Updated By |
|------|---------|-----------|
| `~/.config/sports-bets/active_bets.json` | Current open bets (player props + parlays) | bet_intake.py / betting advisor |
| `~/.config/sports-bets/bankroll.json` | Bankroll state (balance, W-L, deposits) | Betting advisor (Devin session) |
| `~/.cache/nba_playoffs.json` | Cached playoff series data (5-min TTL) | update_sports_dashboard.py |
| `sports-betting-advisor/data/celtics_postseason_2026.md` | Full strategy doc (human-readable) | Betting advisor (Devin session) |
| ESPN Scoreboard API | Live game scores, box scores | Fetched on each conky refresh (60s) |

## Data Flow Diagram

```
                                    ┌──────────────────────┐
                                    │  ESPN Scoreboard API  │
                                    │  (live scores/stats)  │
                                    └──────────┬───────────┘
                                               │
┌─────────────────────┐            ┌───────────▼───────────┐
│  active_bets.json   │───────────▶│                       │
│  (open bets)        │            │  update_sports_       │
└─────────────────────┘            │  dashboard.py         │──▶ stdout ──▶ conky-sports.conf
                                   │                       │     (conky-formatted text)
┌─────────────────────┐            │  (runs every 60s      │
│  bankroll.json      │───────────▶│   via execpi)         │
│  (balance, W-L)     │            └───────────────────────┘
└─────────────────────┘
         ▲
         │
         │  Updated by Devin "Juan Consuelo"
         │  during betting sessions
         │
┌────────┴────────────┐
│  celtics_postseason  │
│  _2026.md           │
│  (strategy doc)      │
└─────────────────────┘
```

---

## Verification Steps

After implementation:

1. **Unit test the dashboard script:**
   ```bash
   python3 conky/update_sports_dashboard.py
   ```
   Verify output has three sections with proper conky color codes.

2. **Seed bankroll.json with real data:**
   ```bash
   cat > ~/.config/sports-bets/bankroll.json <<'EOF'
   {
       "starting_bankroll": 20.00,
       "total_deposited": 40.00,
       "current_balance": 36.33,
       "in_play": 16.00,
       "wins": 3,
       "losses": 0
   }
   EOF
   ```

3. **Run install.sh** to deploy all three panels.

4. **Visual verification:**
   ```bash
   DISPLAY=:0 gnome-screenshot -f /tmp/screenshot.png
   ```
   Confirm three panels with correct spacing: Clock (right) | Sports (middle) | System (left).

5. **Verify clock panel** no longer shows sports data.

6. **Verify system panel** is shifted left with proper gap.

7. **Test edge cases:**
   - No active bets → shows "No active bets"
   - No bankroll.json → shows "Bankroll: N/A"
   - ESPN API failure → graceful fallback (show cached data or "unavailable")
   - Live game with active bets → shows progress indicators

---

## Risks & Considerations

- **Two sources of truth:** `bankroll.json` and the markdown strategy doc both track bankroll. Mitigated by the AGENTS.md instruction requiring the advisor to update both.
- **API load:** Same ESPN API cadence as current (60s refresh). No additional load since this replaces `update_sports.py` in the clock panel.
- **Screen width:** Three 320px panels + gaps = ~1120px minimum. User confirmed this fits their display.
- **text_buffer_size:** Set to 8192 in the sports panel since output can be long (8 series + 4 bets + bankroll). If truncated, increase to 16384.
- **Transition:** The old `update_sports.py` can remain in the repo (it's still useful for the betting advisor's `live_tracker.py` and as a reference). It just won't be called from conky anymore.

---

## Config.env Additions

No new `config.env` variables are strictly needed — the script reuses existing `SPORTS_TEAM`, `SPORTS_TEAM_NAME`, and `BIN_DIR`. However, if desired, you could add:

```bash
# Sports dashboard refresh interval (seconds, used by conky execpi)
SPORTS_DASHBOARD_INTERVAL=60
```

This is optional — 60 seconds is hardcoded in the conky config and works well.

---

*This plan is ready for a future Devin session to execute. All file paths, data formats, and logic are documented above.*
