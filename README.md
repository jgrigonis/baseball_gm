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
runs any pending migrations first, like the web server does. Then start the
server again with `./start_webserver.sh`.

### Admin pages

Admins get an Admin link in the top bar, which opens `/admin/`: every league
with all its settings (change them, pause or resume the league, remove GMs)
and every user (add or delete accounts, set passwords and email addresses,
give or take away admin access).

The first time the server starts on a database, it creates an `admin` login
with the password `changeme`, or whatever `ADMIN_INITIAL_PASSWORD` is set to
in the environment or `.env`. Signing in with it asks for a new password
before anything else. Set `ADMIN_INITIAL_PASSWORD` before that first start
if anyone else can reach the server.

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

At the root of the project you can run `pytest` to run the unit tests

You can run `ruff format .` to format the code, and `ruff check src tests scripts` to lint it (ruff's `F` rules cover pyflakes).

---

This project is licensed under the PolyForm Noncommercial License 1.0.0. See LICENSE for details.
