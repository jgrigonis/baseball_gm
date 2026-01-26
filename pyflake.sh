# pip install pyflakes
pyflakes src
if [ $? -eq 0 ]; then
  echo "No issues found in src"
fi
pyflakes tests
if [ $? -eq 0 ]; then
  echo "No issues found in tests"
fi
pyflakes scripts
if [ $? -eq 0 ]; then
  echo "No issues found in scripts"
fi
#pip uninstall pyflakes -y
