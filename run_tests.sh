# If there's no FooBars.csv
# do this:
# python ./src/team/create_team.py

# This is the old way to run the tests:
# python3 -m unittest discover -s tests  -p "*_test.py" -v

# Use pytest, it's better
pip install pytest
pytest
# For now we can just leave it installed
# pip uninstall pytest -y
