# Baseball Manager

### A Python 3 project

(Requires at least python 3.14)

### Create a virtual environment

Recommend .venv

`python3 -m venv .venv`

To install the project for use:

`pip install -e .`

For developing:

`pip install -e ".[dev]"`

On windows I had to use python -m pip

Or I'd get permission problems.

On windows you should also do this in a powershell as an admin:

`[System.Environment]::SetEnvironmentVariable("PYTHONUTF8", "1", "Machine")`

### Useful script alias 

A handy script alias for your .zshrc file:

`alias cligr='python scripts/cligr.py'`

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

* Multiplayer League

* Single player League vs AI

* Historic Team vs Team in exhibition and series modes

* Simple arcade style hitting and pitching

* Comprehensive gameplay, with everything


### Development notes

At the root of the project you can run `pytest` to run the unit tests

You can run `ruff format .` to format the code, and `ruff check src tests scripts` to lint it (ruff's `F` rules cover pyflakes).

---

This project is licensed under the PolyForm Noncommercial License 1.0.0. See LICENSE for details.
