# Base Betting Strategy — Universal Framework

**Applies to:** All sports, all seasons
**Last Updated:** April 2026
**Advisor:** Juan Consuelo

This document defines the universal betting strategy that applies across all sports and events. Sport-specific and event-specific docs (e.g., `celtics_postseason_2026.md`) inherit from this base and override only what's specific to that event.

---

## Table of Contents

1. [Philosophy](#philosophy)
2. [Confidence Tier System](#confidence-tier-system)
3. [Bankroll Management](#bankroll-management)
4. [Odds Floor Rules](#odds-floor-rules)
5. [Value Betting Framework](#value-betting-framework)
6. [High-Value Bet Identification](#high-value-bet-identification)
7. [Hedging Playbook](#hedging-playbook)
8. [Sport-Specific Notes](#sport-specific-notes)

---

## Philosophy

### "The Grinder" Approach

We don't swing for the fences. We grind out consistent, data-backed wins with disciplined bankroll management and grow the pot methodically. Every bet needs a data-backed reason. "I have a feeling" is not a reason.

**Core Principles:**
- **Data first.** Every bet must be supported by recent player stats, hit rates, and line analysis.
- **Discipline always.** Follow the tier system. Follow the bankroll rules. No exceptions.
- **Volume over variance.** Small, consistent wins compound. One big loss can erase a week of grinding.
- **The books are smart, but they're not omniscient.** Inefficiencies exist — especially in player props. Our job is to find them.

---

## Confidence Tier System

Every bet gets assigned a confidence tier based on the data. This determines whether we bet and how much.

| Tier | Confidence | Hit Rate | Description | Action |
|------|-----------|----------|-------------|--------|
| **Lock** | 85%+ | 8.5+/10 last games | Elite play. Data overwhelmingly supports it. | Bet (within sizing rules) |
| **Strong Lean** | 70-84% | 7-8/10 last games | Very good play. Strong data support with minor risk factors. | Bet (moderate size) |
| **Lean** | 55-69% | 5.5-7/10 last games | Decent play but variance risk. | Bet small, familiar teams only |
| **Fade** | < 55% | < 5.5/10 last games | Not enough edge. | Do not bet. Walk away. |

**Rules:**
- **Lock and Strong Lean** are the only tiers where we bet on unfamiliar teams/players.
- **Lean** bets are restricted to teams/players we know well (e.g., our anchor team).
- **Fade** means no bet, period. Doesn't matter how good it "feels."
- Hit rates should be calculated from the last 10 games minimum. Season averages alone are not sufficient.

---

## Bankroll Management

All sizing rules use **percentages of current bankroll**, not fixed dollar amounts. This scales automatically as the bankroll grows or shrinks.

### Bet Sizing Tiers

| Confidence Level | Max % of Bankroll | Odds Requirement | When to Use |
|-----------------|-------------------|-----------------|-------------|
| Lock (85%+) | 20-25% | -200 or better | Anchor bets on elite props |
| Strong Lean (70-84%) | 10-15% | -175 or better | Secondary props, strong non-anchor plays |
| Lean (55-69%) | 5-10% | -150 or better | Anchor team only |
| Fade (< 55%) | 0% | — | Don't bet |
| Super-juiced Lock (past -200) | 0% straight | Parlay only | Combine into 2-leg parlays |

### Daily Exposure Limit

**Max daily exposure: 30% of bankroll.** No matter how many games are on, never risk more than 30% in a single day. This protects against a catastrophic multi-game wipeout.

### Parlay Rules

- **Max 2-leg parlays only.** Three legs and beyond is a sucker's game at small-to-medium bankrolls.
- Parlay wagers capped at **10% of current bankroll.**
- Both legs must independently be **Strong Lean or better.**
- **Cross-game parlays are preferred** over same-game parlays. Different games = less correlated risk.
- Parlays are the upside play — the grind should be profitable even if every parlay loses.
- **Use parlays for super-juiced props:** When two legs are individually juiced past -200 but both are Locks, the parlay can offer real value at combined odds of -150 or better.

### Never Chase Losses

If we lose a bet, the next bet stays within the tier system. No doubling up. No "revenge" bets. The data doesn't care about our feelings.

### Milestone Withdrawals

- At **2x starting bankroll**: withdraw 25% of starting amount (play with house money buffer)
- At **3x starting bankroll**: withdraw another 25%
- At **5x starting bankroll**: withdraw original stake entirely — everything left is pure profit

### Re-evaluate After Every Session

Update the bankroll tracker, review what hit and what didn't, adjust the approach. The strategy evolves with the data.

---

## Odds Floor Rules

A high hit rate means nothing if the juice eats your profit. The books price known overs accordingly.

**The Lesson:** Going 3-1 can still lose money if the winning bets were at -446 and -710. Hit rate alone does not justify a bet.

### Rules

| Rule | Description |
|------|-------------|
| **No straight bets worse than -200** | If DK is juicing a line past -200, implied probability is 67%+ and payout is garbage. One loss wipes out multiple wins. |
| **Check odds BEFORE hit rate** | Pull `odds_checker.py` first. If the line is past -200, skip straight bet. Look for parlay or alternate line. |
| **The Sweet Spot** | 70%+ hit rate AND odds between -110 and -200. That's where we print money. |
| **Parlay super-juiced props** | When two Lock props are both past -200 individually, combine them. Target -150 or better combined. |
| **Alternate lines** | Sometimes the alternate line (e.g., Over 12.5 REB instead of 10.5) offers better value due to odds misalignment. |

---

## Value Betting Framework

Don't just look for likely winners — look for **mispriced lines** where the data gives us an edge the books haven't fully priced in.

### Expected Value (EV) Calculation

```
EV = (hit_rate x net_payout) - ((1 - hit_rate) x wager)
```

**Only bet when EV > 0.** A positive EV bet is profitable over the long run, even if any individual bet can lose.

### Implied Probability vs. Actual Probability

Convert American odds to implied probability:
- **Negative odds:** `implied_prob = |odds| / (|odds| + 100)`
  - Example: -150 -> 150 / 250 = **60%**
- **Positive odds:** `implied_prob = 100 / (odds + 100)`
  - Example: +130 -> 100 / 230 = **43.5%**

Compare against the **actual hit rate** from recent stats:
- If actual hit rate > implied probability -> **value bet** (positive EV)
- If actual hit rate < implied probability -> **bad bet** (negative EV)
- If actual hit rate = implied probability -> **fair line** (no edge)

### "The Value Zone"

The Value Zone is where the actual hit rate exceeds implied probability by **10% or more.** These are our highest-priority bets.

**Example:**
- DK line: Jaylen Brown Over 25.5 PTS at -163
- Implied probability: 163 / 263 = **62%**
- Actual hit rate (last 10): **90%** (9/10 games)
- Gap: 90% - 62% = **+28%** -> Deep in the Value Zone

### Line Shopping

- Compare DK's lines against the data.
- If DK's line is **higher** than recent performance -> value on the over
- If DK's line is **lower** than recent performance -> the books already priced in what we know
- Always check if an **alternate line** offers a better risk/reward ratio

### Contrarian Plays

When public money pushes a line in one direction, the other side may have value. Use stats to validate — never go contrarian just to be contrarian.

---

## High-Value Bet Identification

### Systematic Scanning Process

For each game day:

1. **Pull stats** for all relevant players using `nba_stats.py` / `nfl_stats.py`
2. **Pull odds** using `odds_checker.py`
3. **Calculate EV** for each prop: compare hit rate vs. implied probability
4. **Rank by EV**: highest expected value gets priority
5. **Apply tier system**: only bet Lock / Strong Lean / Lean (anchor only)
6. **Apply odds floor**: no straight bets past -200
7. **Apply bankroll rules**: stay within daily exposure limit

### Priority Order

1. **Value Zone bets** (hit rate exceeds implied prob by 10%+)
2. **Lock with good odds** (-200 or better)
3. **Strong Lean with great odds** (-150 or better)
4. Skip everything else

### Inefficiency Targets

Less popular props are often less efficiently priced than points:
- **Rebounds** — books focus less on this; consistent rebounders offer reliable value
- **Assists** — especially for high-usage playmakers
- **Blocks** — for elite rim protectors (e.g., Wembanyama), books sometimes underprice
- **3-Pointers Made** — high variance but can be value if a shooter is hot

### Alternate Lines

Sometimes the alternate line offers better value:
- Standard: Over 10.5 REB at -250 (bad odds)
- Alternate: Over 12.5 REB at -110 (much better odds, player averages 14 REB)
- The alternate might actually be the smarter play

---

## Hedging Playbook

Hedging is how we protect downside while keeping upside.

### Strategy 1: Correlated Props

- Bet the **high-confidence prop straight** (e.g., Brown 25+ PTS at $5)
- Bet the **moderate-confidence prop straight** (e.g., Tatum 10+ REB at $3)
- Add a **small parlay combining both** ($2) for bonus upside
- **Why:** If one hits but the other misses, we still profit on the straight bet. If both hit, we cash all three.

### Strategy 2: Opposite Side Hedge

- For larger wagers, consider a **small hedge on the opposite outcome** if game situation changes (e.g., player in early foul trouble)
- DraftKings live betting allows mid-game hedges
- **Rule:** Only hedge if you can lock in guaranteed profit or cut losses by 50%+

### Strategy 3: Series-Level Hedging

- If running hot and up big on a series, take a **small position on the opponent** in a later game
- Guarantees profit for the series regardless of outcome
- **Example:** Bankroll at $35 after Game 2, put $3 on opponent ML in Game 3

### Strategy 4: Prop Diversification

- Diversify props across **multiple games and multiple stars**
- Anchor team props are the core. Layer in high-confidence plays from other matchups.
- If one game is a blowout, other games' props can still carry us.
- **Never have more than 50% of daily exposure on a single game.**

### Strategy 5: Live Betting Hedges

- When a bet is close to hitting at halftime, consider DK's **cash-out** feature
- **Use cash-out when:** the game situation has changed (injury, foul trouble, blowout risk)
- **Don't use cash-out when:** the bet is on track and the player is healthy
- **Manual hedge:** If cash-out value is bad, bet the opposite side live instead

### When NOT to Hedge

- Don't hedge low-confidence bets (if it was a Lean, accept the variance)
- Don't hedge if the cost exceeds 30% of potential payout
- Don't hedge just because you're nervous — let the data decide

---

## Sport-Specific Notes

### NBA

- **Focus on player props:** PTS, REB, AST are the most predictable
- **Check last 10 games**, not just season averages. Recent form matters more.
- **Blowout risk:** In lopsided series, stars may sit the 4th quarter. This caps point totals.
- **Back-to-backs:** Performance drops on the second night. Adjust targets down 10-15%.
- **Home/Away splits:** Some players have massive home/away differentials. Check before betting.
- **Pace factor:** High-pace games = more possessions = more stats for everyone. Check opponent pace.
- **Playoff adjustments:** Players often perform differently in playoffs. Tighter rotations, more minutes for stars.

### NFL

- **Weather matters.** Rain, wind, cold all affect passing and kicking props. Check the forecast.
- **Injury reports:** More impactful than NBA due to positional scarcity. A missing WR1 tanks receiving props.
- **Check last 5 games** (shorter season, more variance per game).
- **Position-specific rules:**
  - QB: Check completion %, pass attempts, opponent pass D rank
  - RB: Check carries/game, opponent rush D rank, game script (favored team runs more)
  - WR/TE: Check targets, opponent coverage stats, slot vs. outside
- **Red zone usage:** Crucial for TD props. Check red zone targets/carries.
- **Game script:** If a team is a heavy favorite, they'll likely run more in the second half. Adjust pass/rush props accordingly.

---

*This document is the foundation. Sport-specific and event-specific docs build on top of it. When in doubt, come back to the base.*
