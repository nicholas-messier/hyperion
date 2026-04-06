# Sports Betting Advisor

A collection of Python scripts and an AGENTS.md personality file that turns Devin into a data-driven sports betting advisor for NBA and NFL, with a focus on DraftKings odds.

## What's Included

| File | Description |
|------|-------------|
| `AGENTS.md` | Devin personality config — makes Devin act as "The Edge", a sharp sports betting analyst |
| `scripts/nba_stats.py` | Fetches NBA player stats (per-game + averages) via the free nba_api |
| `scripts/nfl_stats.py` | Fetches NFL player game logs from ESPN's free API |
| `scripts/odds_checker.py` | Pulls current DraftKings odds for NBA/NFL via The Odds API |

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# NBA stats (no API key needed)
python3 scripts/nba_stats.py --player "Stephen Curry" --season 2024

# NFL stats (no API key needed)
python3 scripts/nfl_stats.py --player "Lamar Jackson" --season 2024

# DraftKings odds (free API key required)
export ODDS_API_KEY="your_key"  # Get one at https://the-odds-api.com
python3 scripts/odds_checker.py --sport nba
```

## Data Sources

| Source | Cost | API Key? | Coverage |
|--------|------|----------|----------|
| [nba_api](https://github.com/swar/nba_api) | Free | No | NBA player stats, game logs, season averages (1946-present) |
| [ESPN API](https://www.espn.com) | Free | No | NFL player game logs, stats, team info |
| [The Odds API](https://the-odds-api.com) | Free tier (500 req/mo) | Yes | DraftKings odds — spreads, moneylines, totals |

## Script Details

### NBA Stats (`nba_stats.py`)
- Search any NBA player by name
- Full season game logs with box score stats
- Calculated season averages with shooting splits
- Filter to last N games for recent form analysis

### NFL Stats (`nfl_stats.py`)
- Search any NFL player by name via ESPN
- Full season game logs with position-aware stat columns
- Disambiguates duplicate stats (e.g., passing YDS vs rushing R_YDS)
- Smart averages: rate stats (CMP%, QBR, RTG) show averages only, counting stats show totals + per-game

### Odds Checker (`odds_checker.py`)
- Real-time DraftKings odds for NBA and NFL
- Supports moneyline (h2h), spreads, and totals markets
- Player props support (may require paid API tier)
- Shows API usage to track free tier limits
- Raw JSON output option for programmatic use

## How It Works with Devin

1. Place the `AGENTS.md` file in your repo root
2. When you chat with Devin, it will adopt "The Edge" personality
3. Ask for picks or analysis — Devin will run the scripts to pull real data
4. Get data-backed recommendations with confidence ratings

Example prompts:
- "What do you think about Jokic over 25.5 points tonight?"
- "Give me your best NFL picks for this week's games"
- "Check the DraftKings spread for tonight's Lakers game"
- "How has Lamar Jackson been playing the last 5 games?"
