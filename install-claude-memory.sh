#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SRC="$SCRIPT_DIR/claude-memory"
DST="$HOME/.claude/memory"

mkdir -p "$DST"
cp -r "$SRC/"* "$DST/"
echo "Done: copied to $DST"
