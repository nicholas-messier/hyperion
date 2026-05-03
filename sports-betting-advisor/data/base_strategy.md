# Base Betting Strategy — Universal Framework

**Applies to:** All sports, all seasons
**Last Updated:** April 2026
**Advisor:** Jay Trotter

This document defines the universal betting strategy that applies across all sports and events. Sport-specific and event-specific docs (e.g., `celtics_postseason_2026.md`) inherit from this base and override only what's specific to that event.

---

## Table of Contents

1. [Philosophy](#philosophy)
2. [Confidence Tier System](#confidence-tier-system)
3. [Bankroll Management](#bankroll-management)
4. [Odds Floor Rules](#odds-floor-rules)
5. [Value Betting Framework](#value-betting-framework)
6. [High-Value Bet Identification](#high-value-bet-identification)
7. [Bet Type Playbook](#bet-type-playbook)
8. [Hedging Playbook](#hedging-playbook)
9. [Sport-Specific Notes](#sport-specific-notes)

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

**Always express the daily cap as a percentage.** Never hardcode a dollar amount — it goes stale as the bankroll changes.

### Single-Game Exposure Limit

**Max single-game exposure: 50% of daily exposure.** Never put more than half of the day's action on one game. If a game goes sideways — blowout, injury, bad reffing — it shouldn't be able to sink the entire card.

### Single-Player Exposure Limit

**Max single-player exposure: 40% of daily exposure (including parlay legs).** If a player appears in a straight bet AND a parlay, count both wagers toward that player's total. One player having an off night should never be able to tank the whole card.

**Example:** Daily exposure is $15. Max on any single player = $6. If you have a $4 straight bet on Player X, their parlay leg can only account for $2 of the parlay wager.

### Parlay Rules

- **Max 2-leg parlays only.** Three legs and beyond is a sucker's game at small-to-medium bankrolls.
- Parlay wagers capped at **10% of current bankroll.**
- **Both legs must independently be Strong Lean or better.** No exceptions. If a player is tiered as Lean or Fade, they don't go in a parlay — period. If the data has changed enough to justify a parlay leg, formally re-tier the player first.
- **Cross-game parlays are preferred** over same-game parlays. Different games = less correlated risk.
- **Same-game parlay (SGP) warning:** When both legs involve teammates (e.g., Player A assists and Player B points), they are positively correlated. That means they boom together AND bust together. If the team has a bad offensive night, both legs fail. **SGPs with same-team players must both be Lock tier.** Treat the positive correlation as added risk, not a bonus.
- Parlays are the upside play — the grind should be profitable even if every parlay loses.
- **Use parlays for super-juiced props:** When two legs are individually juiced past -200 but both are Locks, the parlay can offer real value at combined odds of -150 or better.

### Never Chase Losses

If we lose a bet, the next bet stays within the tier system. No doubling up. No "revenge" bets. The data doesn't care about our feelings.

### Drawdown Protocol

After a losing session (net negative on the day):

1. **Reduce next-day exposure by 25%.** If our normal daily cap is 30%, drop to ~22% the next day. One bad night doesn't mean the strategy is broken, but tightening up protects against tilt and consecutive losses.
2. **Lock and Strong Lean only.** No Lean bets the day after a loss, even on the anchor team. Earn the right to loosen back up with a winning session.
3. **Review what went wrong before placing new bets.** Was it bad luck (player underperformed despite good data) or bad process (broke a rule, skipped EV calc, ignored a red flag)? If it was process, fix it before betting again.
4. **After two consecutive losing sessions:** Drop to Lock-only bets and cut daily exposure to 15% until a winning session resets the streak.

### Milestone Withdrawals

Milestones are based on **total deposited**, not starting bankroll. If you deposit more over time, the milestone targets adjust accordingly.

- At **2x total deposited**: withdraw 25% of total deposited (lock in partial profit)
- At **3x total deposited**: withdraw another 25% of total deposited
- At **5x total deposited**: withdraw original total deposit — everything left is pure profit

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

### Why the Floor is -200 (Not Higher)

We've been asked to extend the floor to -300 or -400. **The math says don't do it at our bankroll size.** The further past -200 you go, the steeper the cliff:

| Odds | Implied % | $1 profit | 7-3 (10 bets, $3 each) | 8-2 | 9-1 |
|------|-----------|-----------|------------------------|-----|-----|
| -110 | 52.4% | $0.91 | **+$10.09** | +$15.82 | +$21.55 |
| -150 | 60.0% | $0.67 | +$5.00 | +$10.00 | +$15.00 |
| -200 | 66.7% | $0.50 | +$1.50 | +$6.00 | +$10.50 |
| -300 | 75.0% | $0.33 | **-$2.00** | +$2.00 | +$6.00 |
| -400 | 80.0% | $0.25 | -$3.75 | **$0.00 (BREAKEVEN)** | +$3.75 |
| -500 | 83.3% | $0.20 | -$4.80 | -$1.20 | +$2.40 |

**Key takeaways:**
- At -400, going **8-2 (80%)** is literally **breakeven**. Vegas already prices the line at 80% — to profit, your hit rate must *exceed* the implied probability, not just match it.
- One -400 loss requires **4 wins** to recoup. Catastrophic at small bankrolls.
- Real example: Apr 20 we went **3-1 with super-juiced lines (-446, -710)** and netted **-$1.06**. A winning night turned into a loss because the juice ate the margins.

### Lock Exception (Future — Not Yet Active)

**When the bankroll grows past $200**, we may consider a Lock-only exception allowing odds up to **-300 max** for plays with all of:
- Documented 90%+ hit rate over the last 10 games
- Verified matchup-specific data (no league-wide averages alone)
- Combined into a 2-leg parlay (no straight bets past -200, ever)

Until then, **the -200 floor holds. Period.**

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

## Bet Type Playbook

We don't bet every type the book offers. Each bet type has a specific role in the strategy. Use the right tool for the job.

### Player Props (Primary)

- **Our bread and butter.** We have the deepest tooling here (`nba_stats.py`, `nfl_stats.py`).
- Most predictable, most data-rich, most exploitable inefficiencies.
- All other bet types are supplementary — props are how we grind.

### Spread Bets (Secondary)

Spreads are the **second-best risk-adjusted bet type** because the juice is standardized at ~-110, which means the [Odds Floor](#odds-floor-rules) is never a problem.

#### When to Bet a Spread
- **NBA/NFL playoffs:** Series-level box scores give us real cover patterns. Track ATS performance per-team, per-venue.
- **The road favorite trap:** Public lays heavy juice on the better team. When the road favorite is **0-2 ATS in the opponent's building this series**, fade them every time.
- **The home dog rebound:** When the home underdog has **covered every home game this series**, take them again. Cover patterns persist within a series.
- **Cross-game spread parlays:** Two spread legs at -110 each = combined odds around **+264**. This is the upside play of the spread world.

#### Spread Tier System (Mirrors the Confidence Tiers)
- **Lock spread:** Team has covered 3+ of last 4 games in the same context (home/away/series). Public bias creates value. Bet within sizing rules.
- **Strong Lean spread:** Team has covered 2 of last 3, OR is 0-2 ATS in opponent's building this series (fade road favorite). Bet moderate size.
- **Lean spread:** Mixed cover history but matchup data favors the side. Anchor team only.
- **Fade spread:** No clear cover pattern. Don't bet.

#### Spread Pitfalls (Avoid)
- **Hooks matter.** A -3.5 vs -3 difference in NBA is huge — half a point can flip a winner to a push or loss. Always note the hook.
- **Backdoor covers.** A garbage-time three can flip a side's cover. Late-game intentional fouls in a blowout can turn a 7-point game into a 12-point game in 90 seconds. Closeouts and blowouts amplify this.
- **No advanced team metrics tooling yet.** We rely on series box scores and recent ATS records. If we can't pull the data, we don't bet the spread.
- **MLB run lines (+/- 1.5)** and **NHL pucklines (+/- 1.5)** behave differently than NBA/NFL spreads — they're closer to alternate moneylines because of low scoring. The favorite -1.5 puckline is essentially asking "will the favorite win by 2+?" In NHL playoffs, half of games end in 1-goal margins. **Avoid puckline favorites.** Underdog pucklines (+1.5) at plus money can have value in tight matchups.

#### Spread vs Moneyline Decision Tree
- **Game has a clear better team, juice past -200 on ML:** Bet the spread instead. Standard juice, similar edge.
- **Game is close on the ML (-150 or better):** Either is fine — pick the one with better data backing.
- **Heavy ML favorite (-300+) IS a Lock:** Look at the alternate spread (e.g., -7.5 instead of -3.5) for a leveraged upside play.
- **You like the underdog outright:** Take the ML, not the +spread. ML pays more if they win.

### Moneyline Bets (Tertiary)

- **Use sparingly.** ML's are inherently more variance-heavy than props with documented hit rates.
- **Best ML spots:**
  - Heavy ML favorite paired with a Lock spread (cross-bet hedge)
  - Underdog ML when the data supports a true coin-flip pricing the dog at +130+
  - Parlay leg combining 2-3 modest favorites for combined odds at +150 or better
- **Worst ML spots:**
  - Any straight ML past -200 (odds floor rule)
  - "Better team" plays without matchup data
  - Late-night MLB games where bullpen variance is unpredictable

### Totals (Over/Under)

- **Lowest priority bet type.** Heavily influenced by pace, weather, foul trouble — high variance.
- Only bet totals when there's a clear systemic edge: starting pitcher matchup with extreme strikeout rates, NFL game in 30 mph wind, NBA team on B2B with backup point guard.
- **Skip otherwise.** Use the bankroll for props and spreads.

### Exotic Bets (First Basket, Anytime TD, Specials)

- **Avoid almost universally.** Variance is the entire bet — no consistent edge available.
- Exception: DK promotional boosts on a Lock-tier player (e.g., +900 boost on a player who scores in 90% of games). Even then, it's a low-conviction shot, not a core play.

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
- See [Single-Game Exposure Limit](#single-game-exposure-limit) and [Single-Player Exposure Limit](#single-player-exposure-limit) for hard caps.

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
