We need to fix this in here I believe. The issue is that if the UI has an injured 
starting pitcher in the rotation, it can just start every game of the season.

We also have one slight problem with the obvious solution, which is to use the 
fallback, we may end up overusing a starter from the rotation.

There are a few other issues with the rotations we need to work out as well.

One is that between the end of the season, and the playoffs, there is extra reecovery 
time, the rotation should start over. Also, during the playoffs, there is more time between
 games, as well as breaks between the series (especially if your series ends faster than the 
 other half of the bracket). We need to adjust starting pitchers accordingly.

Even doing this through the AI is very clumsy, as it's rarely clear which starter is up next.

So, before we start writing any code, we need to come up with all the situations we need to 
account for and solve.

------------------------------

Good, I have enough context. This is a rich design conversation — let me lay it all out clearly.

---

Here's a comprehensive breakdown of every rotation problem to solve before writing a line of code:

---

## Problem 1: Injured Starters Stay in the Rotation

**What happens:** `get_next_starter()` returns whoever is "next up" by rotation order, 
ignoring whether that pitcher is currently injured.

**What's needed:** Before assigning a starter, check if they're in `injured_ids`. If so, 
skip them and advance to the next eligible pitcher in the rotation. This needs to be a *skip*, 
not a fallback — the rotation order should be preserved, just with the injured pitcher temporarily 
stepped over. When they return from injury, they rejoin their original slot.

**Edge case:** What if the entire rotation is injured? Then fall back to best available 
non-injured pitcher (by stamina/energy), but log a warning.

---

## Problem 2: Fallback Overuses a Non-Rotation Starter

**What happens:** The current fallback `_best_pitcher_id()` picks whoever has the highest 
stamina. If called repeatedly (e.g., multiple games in a row with an injured rotation), 
the same guy pitches every game.

**What's needed:** The fallback needs to be energy-aware, not just stamina-aware. Sort 
eligible non-injured pitchers by *current energy*, not raw stamina. The guy who just pitched two days ago shouldn't be picked again.

---

## Problem 3: "Who's Next" Is Ambiguous and Fragile

**The root issue:** The current design is inferring "next starter" from game history. This 
is clumsy — as you noted, it's hard to know who's actually up. 

**What's needed:** The database needs an explicit **rotation pointer** — a record per 
team saying "the next game, pitcher at rotation_order N starts." After each game, the pointer advances to the next *eligible* (non-injured) slot. This pointer is the ground truth, not a calculation from past games.

**Schema addition:**
```
team_rotation_state (team_id, season_id, next_rotation_order)
```

This is updated atomically right after each game completes. No more inference.

---

## Problem 4: Regular Season → Playoffs Gap (Rotation Reset)

**What happens:** There are extra rest days between the end of the regular season and the 
first playoff game. If the pointer just continues, a team might start their Game 1 with 
whoever happened to be "next" rather than their ace.

**What's needed:** At the start of playoffs, reset every team's rotation pointer 
to `rotation_order = 1` (their ace). This is not just a pointer reset — it's also a 
reordering opportunity. Teams should be able to manually set who starts Game 1 of a series.

---

## Problem 5: Playoff Scheduling Has Variable Gaps

**The dynamics:**
- Regular season: typically 1 game/day, rotation cycles naturally
- Playoffs: games within a series may have off-days (travel days)
- Between series: 2–4 days of rest depending on when the other half of the bracket finishes

**What's needed:** Rotation advancement in playoffs should be **game-count-based within a series**, not 
date-based. The pitcher who started Game 1 should pitch Game 4 (or Game 5 with a travel day), not whoever 
happens to be "next" on calendar date.

Concretely: track `games_started_this_series` per pitcher per team per series. In a 7-game series
 on a 5-man rotation, the Game 1 starter can come back for Game 6, but only if they have the rest + energy.

---

## Problem 6: Rotation Reset Between Playoff Series

**What happens:** If Team A sweeps their series in 3 games while Team B plays 7, Team A gets 4+ extra 
rest days. Their ace could be fully recovered and ready for Game 1 of the next series. Team B might be running their #4 starter.

**What's needed:** Between series, re-evaluate who starts Game 1 based on:
- Rest since last start (days or pitch count)
- Current energy
- Rotation order preference

This is where the GM should also get an explicit prompt: "Your series starts in 3 days — set your Game 1 starter."

---

## Problem 7: The UI Is Disconnected From Reality

**What happens today:** The GM UI has a "Starting Pitcher" dropdown, but it's not clearly tied 
to a specific upcoming game. Is it for the next game only? The whole series? Forever?

**What's needed:** The UI should show:
- The upcoming game schedule with dates
- Who is currently projected to start each game (rotation order applied)
- An override option per game (or per series slot)
- Visual indicator when a projected starter is injured or low energy

---

## Summary: The Decisions to Make Before Coding

| # | Problem | Decision Needed |
|---|---------|-----------------|
| 1 | Injured starter picked | Skip injured pitchers in rotation, preserve slot |
| 2 | Fallback overuse | Fallback uses current energy, not raw stamina |
| 3 | Ambiguous "next" | Add explicit `team_rotation_state` pointer to DB |
| 4 | Season→Playoffs gap | Reset pointer to ace for Game 1 of playoffs |
| 5 | Intra-series gaps | Rotation advances by games-in-series, not calendar |
| 6 | Inter-series gaps | Re-evaluate Game 1 starter based on rest + energy |
| 7 | UI disconnect | Show projected starters per game, allow per-game override |

The foundation fix is **#3** — without an explicit pointer, everything else is fighting the 
same inference problem. Everything else builds on top of that. Want to dig into the pointer 
design first, or work through any of these in more detail?

------------------

I don't think problem 1 is solved that simply. 



For instance, if 3/5 starters are injured for example, you can't just reduce to a 2 man starting rotation, certainly not or long.



Perhaps if we sub in the 6th best starter on the team for the injured rotation pitcher, then the 7th best for the next man down, etc.



For problem 2 it's not just stamina how SP is chosen, but it is a big factor in the SP rating.



We definitely need to block a starter who has low energy and sub in an alternate.



Problem 3 does seem like a nice solution.



Problem 4 does seem like the correct solution



Really for Problem 5, we should have the user setup an entirely new rotation, as most teams will move to 4 starters.



Also, in some rare case, you may want your ace to pitch game 1, then game 4, then game 7. Essentially a 3 man rotation.



For problem 6, we could prompt to recreate the rotation for each series, and give them the relevant details, like days of rest, etc.



Problem 7 is still tbd

