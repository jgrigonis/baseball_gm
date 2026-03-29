A Python 3 project

(Requires at least python 3.11)
(Only tested under python 3.12 - 3.14)

Create a virtual environment
Recommend .venv

python3 -m venv .venv

pip install -e .

For developing:

pip install -e ".[dev]"

On windows I had to use pythom -m pip
Or I'd get permission problems.

On windows you should also do this in a powershell as an admin:

[System.Environment]::SetEnvironmentVariable("PYTHONUTF8", "1", "Machine")

### Editor Notes

To get rid of syntax highlight errors in the .html files

In cursor and probably vscode:

Open your Settings (Cmd + , or Ctrl + ,)
Search for Files: Associations.
Add an item: Item: *.html / Value: jinja-html.
Note: This might slightly change how your standard HTML 
auto-completes, but it stops the syntax errors in your style attributes.

### Goals:
* Create a random player (done)
* Create a custom player
* Edit an existing player

* Create a random team (done)
* Create a custom team
* Edit an existing team

* Simulate a baseball game (done)

### Eventual Gameplay modes:

* Multiplayer League

* Single player League vs AI

* Historic Team vs Team in exhibition and series modes

* Simple gameplay, no defense, no errors, just hitting

* Comprehensive gameplay, with everything
