# pip install pyflakes
pyflakes src
if [ $? -eq 0 ]; then
  echo "No issues found"
fi
#pip uninstall pyflakes -y
