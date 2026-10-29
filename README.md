# Baseball Manager

### A Python 3 project

### Requirements

- Python 3.14 or newer
- [uv](https://docs.astral.sh/uv/) 0.11 or newer, which installs the
  dependencies and runs the tests

### Install uv

macOS or Linux:

`curl -LsSf https://astral.sh/uv/install.sh | sh`

Windows (PowerShell):

`powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"`

You can also use `brew install uv`, `winget install astral-sh.uv` or
`pip install uv`. Open a new terminal afterwards and check it with
`uv --version`.

### Set up the project

`uv sync --extra dev`

This creates `.venv` and installs the exact versions recorded in `uv.lock`.
Run tools inside it with `uv run`, for example `uv run pytest`, or activate
it with `source .venv/bin/activate` (`.venv\Scripts\activate` on Windows).

After changing dependencies in `pyproject.toml`, run `uv lock` and commit the
updated `uv.lock`. To upgrade everything to the newest allowed versions, run
`uv lock --upgrade`.

On windows you should also do this in a powershell as an admin:

`[System.Environment]::SetEnvironmentVariable("PYTHONUTF8", "1", "Machine")`

### Deploying

See [DEPLOY.md](DEPLOY.md): Docker Compose with Postgres, HTTPS, the sim
worker, nightly backups and email.

### Migrations

The web server doesn't change the database schema itself. Bring it up to
date first (it's safe to run any time; with nothing pending it does nothing):

`uv run python -m src.db.migrate`

`./start_webserver.sh` does this for you. In a deployment, run it once as a
step before starting the new version. The server refuses to start while
migrations are pending, and says which.

### The sim worker

Anything that moves a league on (simming days, the playoffs, the offseason,
the draft, starting a league, a multiplayer ready-check period) runs in a
separate process, the sim worker, not in the web request. The request queues
a job in Postgres and answers at once; the page polls until it's done. A full
season can take minutes, which would otherwise hold a web worker that long
and run into server timeouts.

`uv run python -m src.worker`

`./start_webserver.sh` starts one alongside the server. In a deployment, run
it as its own process (or container) next to the web server, with the same
`DATABASE_URL`. Run more than one for more leagues at once: they share the
queue and never run the same job, and each league has one job at a time.
Without a worker, sims wait in the queue and the page says it's waiting for
the sim worker.

To stop a worker, send it SIGTERM (what `docker stop` sends): it finishes the
job in hand first, so allow it a few minutes. A worker killed partway through
a job leaves that job to fail after about a minute with "try again"; every
game played up to then is kept.

### Useful script alias 

A handy script alias for your .zshrc file:

`alias cligr='python scripts/cligr.py'`

### Reset every league but keep user accounts

After pulling new code, instead of dropping the whole database you can delete
every league and keep everyone's account. Stop the web server first, then run
this from the repo root:

`uv run python scripts/cligr.py reset-leagues`

It lists the leagues it will delete and asks first; add `--yes` to skip the
question. Each league goes with everything it owns (GMs, drafts, seasons,
games, stats, teams and players) and its `team_files/<league_id>` folder, the
same cleanup as when the last GM leaves a league. It reads `DATABASE_URL` and
runs any pending migrations first. Then start the
server again with `./start_webserver.sh`.

### Admin pages

Admins get an Admin link in the top bar, which opens `/admin/`: every league
with all its settings (change them, pause or resume the league, remove GMs)
and every user (add or delete accounts, set passwords and email addresses,
give or take away admin access).

The first time migrations run on a database, they create an `admin` login
with the password `changeme`, or whatever `ADMIN_INITIAL_PASSWORD` is set to
in the environment or `.env`. Signing in with it asks for a new password
before anything else. Set `ADMIN_INITIAL_PASSWORD` before that first start
if anyone else can reach the server. Once
`PUBLIC_BASE_URL` is an `https://` address (a real deployment), the
migration step refuses to create the admin with `changeme`.

To make any account an admin, or get back in if the admin login is lost, run
this from the repo root (it creates the account if it doesn't exist, and
`--reset-password` asks for a new password):

`uv run python scripts/cligr.py make-admin USERNAME`

### Password reset emails

"Forgot your password?" on the sign-in page emails a reset link to the
address on the account. The link works once, for an hour. Users add or change
their email on the Account page; anyone without one asks an admin to set a
password for them.

Until SMTP is set up, these emails are written to the server log instead of
sent. To send them, set these in the environment or `.env` (any SMTP provider
works; this example is Resend):

```
SMTP_HOST=smtp.resend.com
SMTP_PORT=587
SMTP_USERNAME=resend
SMTP_PASSWORD=<API key>
MAIL_FROM=GM Sim <noreply@your-domain.com>
PUBLIC_BASE_URL=https://your-domain.com
```

`PUBLIC_BASE_URL` is required once `SMTP_HOST` is set, since it's what the
links in the emails point to. Port 465 uses SSL; other ports use STARTTLS.

### Sign-in limits

Ten wrong passwords for one username in 15 minutes, or thirty from one IP,
and sign-in is refused for the rest of those 15 minutes, even with the right
password. One IP can ask for ten reset emails an hour. The counts are kept in
Postgres, so they hold across restarts and gunicorn workers.

The per-IP limits need the visitor's real IP. Plain uvicorn sees it already.
Behind nginx, every request seems to come from nginx unless nginx passes the
address along and the server trusts it from there:

```
# nginx: replace the header rather than appending to it, so visitors can't
# fake their own address
proxy_set_header X-Forwarded-For $remote_addr;
```

Gunicorn's uvicorn workers and uvicorn itself only trust that header from the
addresses in `forwarded_allow_ips` (`127.0.0.1` by default), which is right
when nginx runs on the same machine. Otherwise set it to nginx's address, for
example `--forwarded-allow-ips=10.0.0.5`.

### Editor Notes

To get rid of syntax highlight errors in the .html files

In cursor and probably vscode:

Open your Settings (Cmd + , or Ctrl + ,)

Search for Files: Associations.

Add an item: Item: `*.html` / Value: `jinja-html`.

Note: This might slightly change how your standard HTML auto-completes, but it stops the syntax errors in your style attributes.

### Goals:

Create a fun, interactive game, where you manage and run a baseball team. 

### Eventual Gameplay modes:

* Multiplayer League (see [docs/design/multiplayer.md](docs/design/multiplayer.md))

* Single player League vs AI

* Historic Team vs Team in exhibition and series modes

* Simple arcade style hitting and pitching

* Comprehensive gameplay, with everything


### Development notes

The scripts at the root run from anywhere and install what `uv.lock` lists
first. The server ones need `DATABASE_URL` set, e.g.
`export DATABASE_URL=postgresql://$(whoami)@localhost/baseball_manager`.

- `./start_webserver.sh`: runs migrations, then starts the web server (on
  http://127.0.0.1:8000, reloading on code changes) and a sim worker. Ctrl-C
  stops both; the worker finishes a sim it's in the middle of unless you press
  Ctrl-C again. Extra arguments go to uvicorn, e.g. `--port 8080`.
- `./reset_leagues.sh`: deletes every league but keeps user accounts (see
  above), then starts the server. Stop a running server first.
- `./delete_db_start_webserver.sh`: drops and recreates the whole database
  (creating it if it doesn't exist yet), deletes `team_files/`, then starts the
  server on the empty database. It asks first; `--yes` skips that.
- `./run_tests_with_coverage.sh`: runs the tests under coverage and prints the
  report. Needs `DATABASE_TEST_URL`, a database the tests may wipe (e.g.
  `createdb baseball_manager_test`). Extra arguments go to pytest, e.g.
  `tests/api -x`.

At the root of the project you can run `uv run pytest` to run the unit tests

You can run `ruff format .` to format the code, and `ruff check src tests scripts` to lint it (ruff's `F` rules cover pyflakes).

---

This project is licensed under the PolyForm Noncommercial License 1.0.0. See LICENSE for details.
