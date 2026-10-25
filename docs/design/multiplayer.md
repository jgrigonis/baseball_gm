# Multiplayer: commissioner, who can sim, and the ready-check

This is how a league moves forward once more than one person is playing.
`Master_design.md` has the wider vision; this file describes what is built.

## Single-player and multiplayer

A league is **multiplayer** when it has two or more active human GMs. A GM
counts if they are not AI, belong to a user, and have not been fired
(`gms.is_ai = false`, `user_id` set, `fired_at` null). Away GMs still count.
`is_multiplayer()` in `src/api/services/ready_check.py` is the one place
that decides this.

| | Single-player (1 human GM) | Multiplayer (2+ human GMs) |
| --- | --- | --- |
| Sim regular season (day, until injury, full season) | The GM, any time | Ready-check only |
| Sim playoffs (day, round, all) | The GM, any time | Ready-check, one playoff day per period |
| Begin the offseason | The GM | Ready-check |
| Run the draft | The GM | Ready-check |

In a multiplayer league, `/sim`, `/playoffs/sim`, `/offseason/begin` and
`/draft/execute` return 403 (the `SinglePlayer` dependency), and the pages
show the ready bar instead of those buttons.

## Commissioner

The commissioner is the league's administrator: the GM in
`leagues.commissioner_gm_id`, which is whoever created the league. The role
is separate from running a team, so a commissioner fired as GM stays
commissioner.

The commissioner starts the league and renames it. The commissioner has no
control over when the league sims: there is no force and no pause, so
organising a league gives no competitive advantage. Once the league leaves
the lobby the commissioner plays like any other GM.

The lobby's GM list polls every few seconds, so the commissioner sees GMs
join, and every GM waiting there is taken to the draft once the league
starts.

New GMs can join only while the league is in the lobby. Entering the join
code of a league that has started shows an error on the join page; a GM who
is already in that league is taken straight to it.

## Leaving a league

A GM leaves from the Leave button on `/leagues/` (`POST /leagues/{id}/leave`,
`src/api/services/leave_league.py`).

- **In the lobby** the GM's row is deleted. No team has been handed out yet,
  and AI GMs fill the empty teams when the league starts.
- **Once the league has started** AI takes over the team. The GM's row
  becomes an AI GM (`is_ai = true`, `user_id` null, "AI Manager") and keeps
  its `team_id`, so the team keeps its draft picks, pick rights, results and
  name in the standings. From then on the AI drafts for it, sets its lineup
  and rebuilds its rotation each offseason, and the standings stop marking
  it as a human team. The GM can't rejoin, since joining is lobby-only.
- The ready-check and injury news only look at human GMs, so the leaver
  drops out of both straight away, and their unseen news is deleted. If
  everyone left is ready, the period runs on the next status poll. A league
  that drops to one human GM becomes single-player.
- A **commissioner** who leaves hands the role to the human GM who has been
  in the league longest. With no humans left, a started league has no
  commissioner and a lobby league is deleted.
- Leaving takes the league lock, so it can't land in the middle of a sim
  (409 while one is running).

## The ready-check

A multiplayer league advances one **period** at a time. What a period does
depends on the league's state:

| League state | One period |
| --- | --- |
| draft | runs the draft |
| preseason, season | `sim_period_days` days of the regular season (default 3); the last one sets up the playoffs |
| playoffs | one playoff day |
| offseason | runs the offseason |

When a period runs is set by `leagues.pace_control`, chosen when the league
is created:

| pace_control | The period runs when |
| --- | --- |
| timer (default) | every GM who isn't away is ready, or the period's window runs out |
| confirmed | every GM who isn't away is ready; there is no clock |
| scheduled | a fixed real-world interval passes, e.g. once a day (not built yet) |

- **Away GMs** don't hold the league up. If everyone is away, only the
  clock moves a timer league, and a confirmed league waits.
- Under confirmed pace, a GM who leaves without marking themselves away
  stalls the league. The ready bar names who it is waiting on.
- Under timer pace, the next window starts as soon as a period finishes.
  The draft gets the Draft Window (`draft_window_sec`), the preseason period
  right after it, where GMs set their first lineup, gets the Lineup Window
  (`lineup_window_sec`), and every other period gets the Decision Window
  (`decision_window_sec`).

### How it is built

- `leagues.sim_period` counts periods. A GM is ready when
  `gms.ready_period = leagues.sim_period`, so starting the next period
  un-readies everyone in one update. `leagues.period_deadline` is when the
  current window ends.
- There is no background worker. `GET /leagues/{id}/sim/status` and
  `POST`/`DELETE /leagues/{id}/ready` check whether the period is due. If it
  is, that request takes the league lock, checks again, runs the period and
  moves to the next one. A window that runs out while nobody has the page
  open runs when the next GM opens it.
- `POST /leagues/{id}/away` with `{"away": true}` marks a GM away.
- The ready bar (`dashboard/partials/_ready_bar.html`) polls the status
  every 3 seconds, one request at a time.

## The league lock

Anything that advances a league (sims, playoffs, the offseason, the draft,
starting the league) runs inside `league_lock()` from `src/db/locks.py`, a
Postgres advisory lock named after the league. A second request gets 409
"A sim is already running for this league." rather than playing the same
games twice.

It is an advisory lock, not `SELECT ... FOR UPDATE` on the league row,
because the sim commits after every game and a row lock is released at the
first commit. The advisory lock belongs to the connection, so it stays held
through those commits. Postgres holds it, so it works across server
processes, and it is released if the connection drops.

## Injury news

After every sim day or playoff run, each human GM gets the injuries and
returns on their own team, stored in `gm_notifications`. The GM who ran the
sim sees them in the response. Everyone else sees them the next time they
load a page, or right after a period through the ready bar
(`GET /leagues/{id}/news`).
