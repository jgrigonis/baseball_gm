# This is the old way to run the tests:
# python3 -m unittest discover -s tests  -p "*_test.py" -v

# Use pytest, it's better
pip install pytest
pytest --slow
# For now we can just leave it installed
# pip uninstall pytest -y
# To see coverage:
pip install coverage
coverage run -m pytest
coverage report -m
