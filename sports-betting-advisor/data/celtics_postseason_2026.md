# Celtics 2026 Postseason Betting Strategy

**Started:** April 2026 — NBA Playoffs Round 1
**Platform:** DraftKings
**Starting Bankroll:** $20.00
**Advisor:** Juan Consuelo

---

## Table of Contents

1. [Bankroll Tracker](#bankroll-tracker)
2. [Active Bets](#active-bets)
3. [Bet History](#bet-history)
4. [Core Strategy](#core-strategy)
5. [Bankroll Management Rules](#bankroll-management-rules)
6. [Hedging Playbook](#hedging-playbook)
7. [Player Profiles & Prop Targets](#player-profiles--prop-targets)
8. [Round-by-Round Game Plan](#round-by-round-game-plan)

---

## Bankroll Tracker

| Date | Action | Amount | Balance |
|------|--------|--------|---------|
| Apr 2026 | Starting bankroll | — | $20.00 |
| Apr 19, 2026 | Tatum 10+ REB bet | -$3.00 | $17.00 |
| Apr 19, 2026 | Brown 25+ PTS bet | -$5.00 | $12.00 |
| Apr 19, 2026 | Parlay (Tatum REB + Brown PTS) | -$2.00 | $10.00 |

**Current Balance (unwagered):** $10.00
**Total Wagered:** $10.00
**Total In Play:** $10.00

---

## Active Bets

### Bet 1: Tatum 10+ Rebounds — $3.00
- **Type:** Player Prop (Rebounds)
- **Confidence:** Strong Lean (75%)
- **Data Backing:**
  - Tatum averaging **10.0 RPG** on the season (16 games played)
  - Last 10 games rebound totals: 13, 5, 13, 11, 18, 5, 12, 12, 11, 9
  - Hit 10+ rebounds in **7 of last 10 games (70%)**
  - Playoff Tatum historically elevates his rebounding with increased minutes
- **Risk:** Two games at 5 rebounds show he can disappear on the glass. Small-ball lineups or foul trouble could limit boards.

### Bet 2: Jaylen Brown 25+ Points — $5.00
- **Type:** Player Prop (Points)
- **Confidence:** Lock (88%)
- **Data Backing:**
  - Brown averaging **28.7 PPG** on the season (71 games — workhorse)
  - Last 10 games scoring: 23, 35, 26, 26, 43, 29, 31, 29, 30, 32
  - Hit 25+ points in **9 of last 10 games (90%)**
  - Season-long shooting splits: 47.7% FG / 34.7% 3PT / 79.5% FT — efficient and consistent
  - Brown has been the Celtics' go-to scorer and his usage only goes up in the playoffs
- **Risk:** The one miss was 23 points — still close. Early blowout could limit minutes. Only real concern is foul trouble or injury.

### Bet 3: Parlay — Tatum 10+ REB + Brown 25+ PTS — $2.00
- **Type:** Parlay (2-leg)
- **Confidence:** Lean (65%)
- **Data Backing:**
  - Both legs have strong individual hit rates (70% and 90%)
  - Combined probability estimate: ~63% (0.70 x 0.90) — but real correlation may be higher since both benefit from competitive, full-length games
  - Parlay pays out at enhanced odds, making the $2 a smart value play
- **Risk:** Parlays are inherently riskier. One leg fails, the whole thing is toast. This is our "bonus" bet, not the backbone.

---

## Bet History

| Date | Bet | Wager | Result | Payout | Net |
|------|-----|-------|--------|--------|-----|
| *(no completed bets yet)* | | | | | |

**Running P&L:** $0.00 (bets in progress)

---

## Core Strategy

### Philosophy: "The Grinder"

We ain't here to hit one big parlay and call it a day. That's how you go broke. We're here to **grind out consistent, data-backed wins** with a small bankroll and grow it methodically through the Celtics postseason. Think of it like this — we're playing tight poker, not scratching lottery tickets.

### The Three Pillars

#### 1. Prop-Heavy Approach
- **Player props are our bread and butter.** We know Tatum and Brown's games inside and out. We watch them, we have the data, and props on familiar players give us an edge over the general public.
- Focus on **rebounds, points, and assists** — the stats with the most predictable baselines.
- Avoid exotic props (first basket, exact score) — too much variance.

#### 2. Data-First, Always
- **Never place a bet without pulling stats first.** Use `nba_stats.py` to check last 5-10 game trends before every bet.
- Look for props where the line is lower than the player's recent average. That's where the value lives.
- Track hit rates: if a player has hit an over in 7+ of last 10, that's a Strong Lean or Lock.

#### 3. Small Ball, Big Picture
- With a $20 bankroll, we can't afford to go wild. Max single bet is 25% of bankroll ($5 on our biggest lean).
- Parlays are limited to 10% of bankroll — they're the cherry on top, not the meal.
- Goal: **grow the bankroll 50% per round** ($20 -> $30 after Round 1, $30 -> $45 after Round 2, etc.)

---

## Bankroll Management Rules

### Bet Sizing Tiers

| Confidence Level | Single Bet Size | Max % of Bankroll |
|-----------------|----------------|-------------------|
| Lock (85%+) | $4-5 | 20-25% |
| Strong Lean (70-84%) | $2-3 | 10-15% |
| Lean (55-69%) | $1-2 | 5-10% |
| Fade (< 55%) | $0 — don't bet | 0% |

### Parlay Rules
- **Max 2-leg parlays only.** Three legs and beyond is a sucker's game at this bankroll size.
- Parlay wagers capped at **10% of current bankroll.**
- Both legs must independently be Strong Lean or better.
- Parlays are our upside play — we should be profitable even if every parlay loses.

### Bankroll Discipline
- **Never chase losses.** If we lose a bet, the next bet stays within the tier system. No doubling up.
- **Re-evaluate after each game.** Update the bankroll tracker, review what hit and what didn't, adjust the approach.
- **Withdraw profits at milestones.** If bankroll hits $40 (2x starting), pull $10 back and play with house money. If it hits $60 (3x), pull another $10.

---

## Hedging Playbook

Hedging is how we protect our downside while still keeping upside. Here's how we do it with this bankroll:

### Strategy 1: Correlated Props (Our Current Approach)
- Bet the **high-confidence prop straight** (Brown 25+ PTS at $5).
- Bet the **moderate-confidence prop straight** (Tatum 10+ REB at $3).
- Add a **small parlay combining both** ($2) for bonus upside.
- **Why this works:** If Brown hits (90% rate) but Tatum misses, we still profit on the Brown bet. If both hit, we cash all three. We only lose everything if Brown misses, which happens ~10% of the time.

### Strategy 2: Opposite Side Hedge (For Bigger Bets Later)
- When we have a larger bankroll and place a bigger wager, consider a **small hedge on the opposite outcome** if the game situation changes (e.g., player gets in early foul trouble).
- DraftKings live betting allows mid-game hedges.
- **Rule:** Only hedge if you can lock in a guaranteed profit or cut losses by 50%+.

### Strategy 3: Series-Level Hedging
- If we're running hot and up big on a series, we can take a **small position on the opponent** in a later game to guarantee profit for the series regardless of outcome.
- Example: If bankroll is at $35 after Game 2, put $3 on the opponent's moneyline in Game 3. If the Celtics win, we're still up big. If they lose, the hedge softens the blow and we live to bet Game 4.

### Strategy 4: Prop Diversification
- Don't put all our eggs in one player's basket. Spread props across **Tatum, Brown, and a role player** (Derrick White, Jrue Holiday) to reduce correlation risk.
- If one star has an off night, the other props can still carry us.

---

## Player Profiles & Prop Targets

### Jayson Tatum
| Stat | Season Avg | Last 10 Avg | Prop Target |
|------|-----------|-------------|-------------|
| Points | 21.8 | 22.4 | Over 20.5 (lean) — note: only 16 games, may be returning from injury, monitor minutes |
| Rebounds | 10.0 | 10.9 | **Over 9.5 / 10+ (strong lean)** — our money maker |
| Assists | 5.3 | 6.1 | Over 5.5 (lean) — playmaking trending up |

**Key Notes:**
- Only 16 games this season — likely missed significant time. **Monitor his minutes and conditioning closely.**
- When healthy, Tatum is a 10+ rebound machine. His last 10 show 10.9 RPG.
- Scoring is down from career norms (21.8 vs typical 26-28) — could be working back into rhythm. **Be cautious on points props until we see playoff minutes.**

### Jaylen Brown
| Stat | Season Avg | Last 10 Avg | Prop Target |
|------|-----------|-------------|-------------|
| Points | 28.7 | 30.4 | **Over 25.5 / 25+ (LOCK)** — our best bet every game |
| Rebounds | 6.9 | 6.1 | Over 5.5 (lean) — solid but not elite |
| Assists | 5.1 | 5.0 | Over 4.5 (lean) — playmaking is real |

**Key Notes:**
- Brown is the **alpha scorer** this season. 28.7 PPG over 71 games — that's not a hot streak, that's who he is.
- 47.7% FG is elite efficiency. He gets to the line (79.5% FT) and doesn't rely solely on threes.
- His floor is ~23 points, his ceiling is 43. That range means 25+ is almost automatic.
- **Brown points over is our anchor bet every single game.**

### Role Players to Watch
- **Derrick White:** Consistent 3PT shooter, rebounds well for a guard. Look for 3+ threes prop.
- **Jrue Holiday:** Veteran who shows up in playoffs. Assists and steals props can have value.
- **Al Horford / Kristaps Porzingis:** Check availability — big man props (rebounds, blocks) if they're playing.

---

## Round-by-Round Game Plan

### Round 1 (Current)
- **Bankroll:** $20
- **Goal:** Grow to $30+ ($10 profit)
- **Approach:** Conservative. Stick to Brown points (anchor) + Tatum rebounds (secondary) + small parlay.
- **Bet per game:** $8-10 total across 2-3 bets
- **Key rule:** We have 4-7 games in a series. Even if we lose Game 1 bets, there are plenty of opportunities. Don't panic.

### Round 2 (Target Bankroll: $30-35)
- **Goal:** Grow to $45-50
- **Approach:** Slightly more aggressive. Can add a third straight bet (role player prop or game total).
- **Bet per game:** $10-15 total across 2-4 bets
- **Introduce:** Series-level hedging if up big early

### Conference Finals (Target Bankroll: $45-55)
- **Goal:** Grow to $70+
- **Approach:** This is where we have real money to play with. Can start using live betting hedges.
- **Bet per game:** $15-20 total
- **Introduce:** Opposite side hedges on live betting, opponent moneyline hedges

### NBA Finals (Target Bankroll: $70+)
- **Goal:** Profit withdrawal + play with house money
- **Approach:** At this point, pull $20 (our original stake) and play with pure profit.
- **Bet per game:** Whatever we're comfortable with from profit
- **Introduce:** Larger parlay shots (3-leg) since we're playing with house money

---

## Session Notes

### April 19, 2026
- Celtics postseason Round 1 in progress.
- Placed three bets on current game: Tatum 10+ REB ($3), Brown 25+ PTS ($5), Parlay of both ($2).
- Data strongly supports both props. Brown's 25+ is the safest bet on the board (90% hit rate last 10). Tatum's rebounds are solid but have two clunker games in the mix.
- Bankroll sits at $10 unwagered. Waiting for results before placing next bets.
- **Next steps:** After this game resolves, update bet history, adjust bankroll, and evaluate lines for the next game.

---

## Rules for Future Sessions

When coming back to this strategy:
1. **Always check the date** and figure out where we are in the series/playoffs.
2. **Pull fresh stats** using `nba_stats.py` — don't rely on old data.
3. **Update the bankroll tracker** with results from any completed bets.
4. **Follow the bet sizing tiers** — no exceptions, no matter how good a bet "feels."
5. **Update this document** with new bets, results, and session notes.

---

*Remember: Sports betting involves risk. Only bet what you can afford to lose. This strategy is designed to be disciplined and data-driven, but there are no guarantees. Bet responsibly.*
