# Baseball GM Sim — Product Design Document

## Vision

A web-based baseball GM simulation where players manage a franchise through
multiple seasons. Supports both quick-play sessions (a full GM career in
60-90 minutes with a group) and longer-form leagues where seasons unfold
over days or weeks.

The AI GM is a first-class participant — human GMs can drop out, and
the league continues either way.

---

## Sim Performance

The sim engine runs at up to **8 games per second**. A full 30-team,
174-game season generates ~2,610 games, taking roughly **5 minutes of pure
sim time**. This sets the scale in terms of pacing:

| Scope             | Games   | Sim time   |
|-------------------|---------|------------|
| 1 regular season  | 2,610   | ~5 min     |
| + playoffs        | ~60     | ~8 sec     |
| 5-season career   | ~13,000 | ~26 min    |
| 8-season career   | ~20,000 | ~42 min    |
| 25-season career  | ~62,000 | ~2 hrs     |

Sim time is not a significant bottleneck in Blitz — **GM decision time is**.
In the Long Form version, Simulation time is insignificant, as the players
(some human) are intended to take time for nearly every single game.
---

## Experience Modes

### Quick Play ("Blitz League")
- A full GM career spans **5–8 seasons**, matching real-world GM tenure
- Real GMs typically last 3–4 years if underperforming; 8–10 if successful
- 5 seasons of sim takes ~26 minutes — total session with draft and decisions
  is aimed towards around **60–90 minutes**
- League currently always runs at **~30 teams** — the full sim size
- Human GMs range from **1 to 30** depending on who joins; AI fills the rest
- Join with strangers (via future public lobby) or friends via a league code
- Sim advances on a timer between phases — GMs who aren't ready get AI fallback
- At career end: performance verdict, optionally start a new career

### Long Form ("Commissioner League")
- A season unfolds over days or weeks
- Sim engine advances on a schedule (e.g. one series per day, or 10 games)
- GMs make decisions on their own schedule between sim runs
- League generally runs at **~30 teams**
- Human GMs range from 1 to 30; AI fills the rest
- Higher stakes, more deliberate decision-making
- A "career" plays out over weeks or months of real time

**Both modes use the same sim engine and GM decision model.**
The main difference is the pace at which the sim clock advances.
Also, the intended stopping and adjustment points vary

---

## The Game Loop

```
League Created
    │
    ▼
Pre-Season
  ├── Draft (see Draft Format below)
  ├── Set 40-man active roster and/or 26-man (and adjust full roster)
  └── Set strategic profile

    │
    ▼
Regular Season  (repeating — ~5 min sim per season)
  ├── [Between series]  Review upcoming opponent, adjust profile/lineup
  │                     Blitz: configurable window (see Decision Windows)
  │                     Long form: hours to days. Can advance when all are ready.
  ├── [Sim runs]        Games execute automatically using GM profiles
  └── [After series]    Review results; lineup, strategy and roster adjustments

    │
    ▼
Playoffs
  ├── Bracket announced
  ├── [Between series]  Adjust rotation, lineup, profile, roster
  │                         Long form pauses after each game.  
  └── [Sim runs]        ~8 seconds per playoff round

    │
    ▼
Offseason
  ├── Performance review (GM firings — see below)
  ├── Free agency / trades (TBD)
  ├── Draft
  └── New season begins
```

---

## Draft Format

Different formats per mode, reflecting the time available:

### Blitz — Preference List (Auto-Draft)
- GMs submit a ranked preference list before the draft runs
- Draft executes automatically in snake order using each GM's list
- If a player is gone, the next available preference is taken
- Fast — completes in seconds, not minutes
- GMs spend their decision time *building the list*, not watching picks tick down

### Long Form / Scheduled — Interactive Snake Draft
- Live draft room, all GMs present
- Each pick has a configurable timer (default 90 seconds)
- If a GM doesn't pick in time, auto-selects from their submitted preference list
- Preference list acts as a fallback, not the primary mechanism
- Draft can be paused by Commissioner

---

## Roster Structure

### Blitz Mode
- **40-man roster** — players who appear in games
- Full Organization - Unlimited size.
- Moves between 40-man are unrestricted between series

### Long Form / Scheduled Mode
- **26-man active roster** — players who are allowed to appear in games
- **40-man roster** — standard organizational threshold
- **Full org roster** — up to 160 players (existing sim cap)
- Players must be on the 40-man to be called up to the 26-man
- Moving a player from full org → 40-man requires a roster move (limited
  per series, exact number TBD, may introduce waivers, free agency, etc)
- Moving a player off the 40-man to make room follows MLB-style rules:
  outright waivers, DFA, release (details TBD for v1)

> **Design note:** The 40-man threshold is what gives Long Form its
> strategic texture. Protecting prospects, managing the 40-man crunch
> before the trade deadline, and making DFA decisions are core GM activities
> in real baseball. Blitz skips this complexity intentionally.
>
> Specific roster move limits (transactions per series, option rules, DFA
> mechanics) will be defined in a separate ruleset doc once v1 is stable.

---

## Player Ratings (Scouting Grades)

GMs see **scouting grades**, not raw numbers. Exact numerical ratings are
only visible in debug/dev mode.

### Grade Scale
Standard 20-80 scouting scale mapped to letter grades with +/–:

| Grade | Range  | Label       |
|-------|--------|-------------|
| A+    | 75–80  | Elite       |
| A     | 70–74  | Plus-plus   |
| A-    | 65–69  | Plus        |
| B+    | 60–64  | Above avg   |
| B     | 55–59  | Average+    |
| B-    | 50–54  | Average     |
| C+    | 45–49  | Below avg+  |
| C     | 40–44  | Below avg   |
| C-    | 35–39  | Fringe      |
| D+    | 30–34  | Well below  |
| D     | 25–29  | Poor        |
| D-    | 20–24  | Very poor   |
| F     | < 20   | Non-prospect|

### Tools Shown Per Player Type
**Position players:** Contact, Power, Eye, Speed, Arm, Field, Overall

**Pitchers:** Stuff, Control, Stamina, Recovery, Overall

Entire SKILLS found in positions.py:


SKILLS: MappingProxyType[str, int] = MappingProxyType(
    {
        # Pitching
        "accuracy": 50,  # Control, ability to hit spots
        "stamina": 50,  # Pitch count capacity (50 = ~100 pitches)
        "recovery": 50,  # Days to recover stamina (50 = 5 days)
        "ground_balls": 50,  # Ground ball tendency
        "strikes": 50,  # Swing-and-miss ability (stuff)
        # General
        "clutch": 50,  # Performance in high-pressure situations
        "speed": 50,  # Running speed
        "durability": 50,  # player durability
        # Hitting
        "power": 50,  # Home run power
        "eye": 50,  # Plate discipline, walk rate
        "contact": 50,  # Ability to make contact
        "base_running": 50,  # Base running instincts
        "bunting": 50,  # Bunting ability
        # Defense
        "catching": 50,  # Catcher-specific skills
        "infield": 50,  # Infield defense
        "outfield": 50,  # Outfield defense
        "arm": 50,  # Throwing arm strength
    }
)

### Scouting Uncertainty (future)
- Early in a career, grades have a ±1 letter uncertainty range
    Some skills are easier to assess than others
- Scouting improves as the player accumulates games
- Adds hidden information tension during the draft

---

## GM Decisions

### Strategic Profile
The core GM tool. A set of tendencies the AI uses to manage the team
when the GM isn't making an explicit override. Changeable at any point
between games.

This is under construction:

**Batting**
- Lineup style: `traditional` | `analytics` | `speed-first` | `power-first`
- Steal aggression: `conservative` | `standard` | `aggressive`
- Sac bunt usage: `never` | `situational` | `frequent`

**Pitching**
- Starter usage: `let-them-work` | `pitch-count-strict` | `matchup-based`
- Closer usage: `saves-only` | `high-leverage` | `best-available`
- Bullpen depth preference: `deep-pen` | `starter-heavy`

**Roster**
- Platoon usage: `none` | `vs-handedness` | `aggressive`

### Explicit Overrides (between series/games)
- Set starting lineup for next game/series
- Set starting pitcher
- 26/40-man roster moves (call-ups, optioning down)
- Set rotation order for a series

### In-Game (not player-controlled)
All in-game decisions (pinch hits, pitching changes, stolen base attempts,
hit and run) are executed by the AI using the GM's strategic profile.

> **Design principle:** GMs set *strategy*, not *tactics*.
> The AI handles real-time execution.

---

## Decision Windows (Blitz)

The time GMs have between series to make decisions before the sim advances.

### Configurable per league
- Commissioner sets a window range (e.g. 30–180 seconds)
- Before the league starts, each GM sets their **fastest comfortable pace**
- The league runs at the **fastest pace all GMs agree to**
  (i.e. the minimum of all GM preferences)
- If a GM is AFK, the AI handles their decisions — they aren't penalized
  as long as they marked themselves away

### Suggested defaults
- **Pickup / strangers**: 120 seconds (forgiving for new players)
- **Friends / experienced**: 60 seconds
- **Speed run**: 30 seconds

### Late-session behavior
Window does not automatically shrink as the session progresses — the
configured pace stays consistent. GMs who want faster play choose it
upfront. Future implementation would be to change window based on a quorum.

### Decision points
- Also configurable is how often to set decision windows
- Some standards are: Every 4 games, Every 10 games, twice per season, etc
- Allow Blitz to approach, but not intersect with the Long Form version.

---

## Progression & Stakes

### GM Tenure
Real GMs last 3–4 years if underperforming, 8–10 if successful. The sim
mirrors this:

- **Years 1–2**: Grace period. Roster inherited, expectations calibrated.
- **Year 3+**: Evaluated against roster quality. Consistent underperformance
  triggers a warning, then firing.
- **Firing**: GM is removed from their franchise.

### Re-Entry After Firing

Configurable per league (Commissioner toggle):

- **One and done**: Fired GMs sit out the rest of the session. Creates
  maximum stakes — losing your job means watching from the sidelines.
  Best for competitive groups.

- **Re-entry**: Fired GMs join a pool and are reassigned to the next
  franchise that has an opening (e.g. another GM quits, or an AI team
  is made available). Creates a second-chance arc. Best for casual groups
  or when you want everyone playing the whole session.

### Performance Evaluation
Each GM is evaluated at season end on:
- Win percentage vs expectation (based on roster quality rating)
- Playoff appearances
- Championship wins
- Trend (improving vs declining)

### Contracts (future)
- Player contracts add financial constraints
- Trades become meaningful when salary cap is involved
- Out of scope for v1

---

## Multiplayer Model

### League Codes
- Any player can create a league and share a join code
- League creator becomes Commissioner (admin controls)
- Empty GM slots filled by AI — league always runs at full size
- Public Lobby. Can put a league in the public lobby, then anyone can join
  simply with a click.

### Pace Control (Commissioner setting)
- **Blitz**: sim advances on the agreed decision window timer and frequency
- **Confirmed**: sim advances when all GMs confirm ready, or timeout expires
- **Scheduled**: sim runs at fixed real-world times (e.g. one series per day
  at 8pm)

### AI Fallback
- If a human GM is absent when the sim runs, their strategic profile governs
- GMs can mark themselves "away" to prevent being penalized for absence
- Commissioner can permanently replace absent human GMs with AI mid-season

---

## Technical Architecture (proposed)

### Backend
- **FastAPI** — REST API + WebSocket for live updates during sim
- **SQLite** — initial development target; clean migration to PostgreSQL
  when multiplayer requires concurrent writes
- **Python sim engine** — existing codebase, runs as background task
- **Celery + Redis** — task queue for sim jobs (added when moving to Postgres
  for multiplayer; not needed for single-player SQLite phase)

### Frontend
- **Server-rendered HTML (Jinja2)** for most views — standings, rosters,
  box scores, leaderboards
- **HTMX** for partial page updates — live standings refresh, series results
  appearing as sim runs
- **React** only for high-interactivity components — draft board, live game
  log during active sim, strategic profile editor

### Data Flow
```
GM action (web form / API call)
    → FastAPI endpoint validates + writes to DB
    → Sim task triggered (or runs on schedule via Celery)
    → Sim engine reads team profiles from DB
    → Game results written to DB in batches
    → WebSocket pushes series results to connected GMs
    → Standings / game log update via HTMX
```

### SQLite → PostgreSQL Migration (when needed)
Development starts against SQLite — the existing schema and codebase work
as-is. Migration to Postgres happens when multiplayer concurrent writes
require it. Known deltas at that point:
- `TEXT` UUIDs work in both — no change needed
- SQLite `INTEGER` PRIMARY KEY → Postgres `UUID` with `gen_random_uuid()`
- SQLite-specific pragmas (`PRAGMA journal_mode`, etc.) removed
- `player_game_stats`, `player_season_stats` rollup tables port cleanly
- Indexes translate directly
- Row factory (`sqlite3.Row`) → psycopg2 `RealDictCursor` or SQLAlchemy ORM

---

## Views (MVP)

### League Hub
- Current standings with division breakdown
- Recent series results
- Upcoming schedule
- Active GM list (online / away / AI)
- Commissioner controls

### My Team
- Current roster with scouting grades
- 26-man / 40-man breakdown (Long Form) or 26/40 (Blitz)
- Strategic profile editor
- Lineup setter for next series
- Recent performance (last 10 games)

### League Leaders
- Batting / pitching leaderboards (current season)
- Records (single-game, season, all-time)

### Game Log
- Box score for completed games
- Play-by-play (condensed — key events only)

### Draft Room
- Blitz: preference list builder with player grades and filters
- Long Form: interactive snake draft room with pick timer and live board

### History
- Season archives with standings and awards
- All-time franchise records
- Player career traces

---

## Resolved Design Decisions

| Question | Decision |
|----------|----------|
| Draft format | Preference list for Blitz; interactive snake with timer for Long Form |
| Roster size | 26-man active / 40-man org for Blitz; 26/40/160 for Long Form |
| Rating visibility | A+–F scouting grades in UI; raw numbers debug-only |
| Decision window | Configurable; runs at fastest pace all GMs agree to |
| Re-entry after firing | Commissioner toggle: one-and-done or re-entry pool |
| League size | ~30 teams always; 1–30 human GMs, AI fills the rest |
| 40-man move limits | TBD — separate ruleset doc, post-v1 |
| Database | SQLite for development; PostgreSQL when multiplayer requires it |

---

## Deferred / Future Scope

- Trades between GMs
- Free agency market
- Salary caps / contracts
- In-game tactical control
- Mobile app (responsive web is sufficient for v1)
- Spectator mode
- Scouting uncertainty / hidden grade ranges
- 40-man transaction ruleset (DFA, options, waivers)
- Celery / Redis task queue (added with Postgres for multiplayer)
