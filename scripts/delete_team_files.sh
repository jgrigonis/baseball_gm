
#!/bin/sh

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PARENT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

rm -rf "$PARENT_DIR"/team_files/*

