# src/api/routers/sim.py
#
# Advancing the league: simming regular-season days, playoff games, and
# running the offseason.

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

from src.api.dependencies import (
    DB,
    GM,
    ActiveLeague,
    GMOrViewer,
    SinglePlayer,
    Unpaused,
)
from src.api.schemas import SimRequest
from src.api.services import sim_jobs
from src.api.services.injury_news import take_injury_news
from src.api.services.sim_summary import my_day
from src.db.repositories.league_repo import LeagueRepository
from src.db.repositories.season_repo import SeasonRepository
from src.db.repositories.sim_job_repo import SimJobRepository
from src.web.utils import _current_league_date

router = APIRouter(tags=["web"])


# Each of these queues a job for the sim worker and answers 202 with its id at
# once; the page polls /leagues/{id}/jobs/{job_id} for the result
# (src/api/services/sim_jobs.py).


def _queued(league_id: str, job_id: str) -> JSONResponse:
    return JSONResponse(
        {"job_id": job_id, "poll": f"/leagues/{league_id}/jobs/{job_id}"},
        status_code=202,
    )


@router.post("/leagues/{league_id}/sim")
def sim_games(
    league_id: str,
    body: SimRequest,
    db: DB,
    gm: GM,
    _active: ActiveLeague,
    _: SinglePlayer,
    _unpaused: Unpaused,
):
    """Sim N games (or until season end)."""
    job_id = sim_jobs.submit(db, league_id, "sim", {"count": body.count}, gm["id"])
    return _queued(league_id, job_id)


@router.post("/leagues/{league_id}/playoffs/sim")
def sim_playoff_route(
    request: Request,
    league_id: str,
    db: DB,
    gm: GM,
    _active: ActiveLeague,
    _: SinglePlayer,
    _unpaused: Unpaused,
    mode: str = "game",
):
    job_id = sim_jobs.submit(db, league_id, "playoffs", {"mode": mode}, gm["id"])
    return _queued(league_id, job_id)


@router.post("/leagues/{league_id}/offseason/begin")
def begin_offseason(
    league_id: str,
    db: DB,
    gm: GM,
    _active: ActiveLeague,
    _: SinglePlayer,
    _unpaused: Unpaused,
):
    job_id = sim_jobs.submit(db, league_id, "offseason", gm_id=gm["id"])
    return _queued(league_id, job_id)


# A job still queued this long after it was asked for suggests no sim worker
# is running; the page says so rather than waiting quietly.
WORKER_MISSING_SECONDS = 15


@router.get("/leagues/{league_id}/jobs/{job_id}")
def job_status(league_id: str, job_id: str, db: DB, gm: GMOrViewer):
    """Where a queued sim has got to. Once it's done, its result in the shape
    the page expects, plus this GM's injury news for the sims that have
    any.

    A viewer can poll too: the sim that ends the playoffs is where owners
    fire GMs (src/api/services/firing.py), so the GM who asked for it may be
    a viewer by the time it's done. They still get the result, flagged
    fired, so the page can show the finals and their new view."""
    job = SimJobRepository(db).get(job_id)
    if not job or job["league_id"] != league_id:
        raise HTTPException(status_code=404, detail="No such sim.")
    if job["state"] in ("queued", "running"):
        return JSONResponse(
            {
                "state": job["state"],
                "stage": job["stage"],
                "waiting_for_worker": job["state"] == "queued"
                and job["age_seconds"] > WORKER_MISSING_SECONDS,
            }
        )
    if job["state"] == "failed":
        return JSONResponse({"state": "failed", "detail": job["error"]})

    body = {"state": "done", **(job["result"] or {})}
    if job["kind"] in ("sim", "playoffs"):
        league = LeagueRepository(db).get_by_id(league_id)
        body["league_state"] = league["state"] if league else "lobby"
        if gm.get("fired"):
            body["fired"] = True
        if gm.get("id"):
            body.update(take_injury_news(db, gm["id"]))
    if job["kind"] == "sim":
        season_id = SeasonRepository(db).get_current_id_for_league(league_id)
        body["current_date"] = _current_league_date(db, season_id, body["league_state"])
        # The GM's own team after the day, for the line under the sim buttons.
        body["my_team"] = my_day(
            db, league_id, season_id, gm.get("team_id"), body.get("last_date")
        )
    return JSONResponse(body)


@router.get("/leagues/{league_id}/news")
def injury_news(league_id: str, db: DB, gm: GM, team: bool = False):
    """The GM's injury news from sims they didn't see, e.g. ones another GM
    ran. Marked seen once returned. ``team`` (a multiplayer period just ran)
    adds the GM's team after the last day played, in the regular season,
    for the sim card's line."""
    body = take_injury_news(db, gm["id"])
    if team:
        league = LeagueRepository(db).get_by_id(league_id)
        if league and league["state"] == "season":
            season_id = SeasonRepository(db).get_current_id_for_league(league_id)
            row = db.execute(
                """SELECT MAX(game_date) AS d FROM games
                   WHERE season_id = %s AND completed = 1 AND series_id IS NULL""",
                (season_id,),
            ).fetchone()
            body["my_team"] = my_day(
                db, league_id, season_id, gm.get("team_id"), row["d"] if row else None
            )
    return JSONResponse(body)


@router.get("/leagues/{league_id}/progress")
def league_progress(league_id: str, db: DB, _gm: GMOrViewer):
    """Polled by pages that don't move the league on themselves, e.g. a
    viewer's, so they can refresh once it has. Only reads; unlike
    /sim/status it never runs a period."""
    return JSONResponse(LeagueRepository(db).progress(league_id))
