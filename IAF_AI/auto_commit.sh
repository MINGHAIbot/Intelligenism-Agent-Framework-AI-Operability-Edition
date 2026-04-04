#!/bin/bash
# Safety snapshot — run before destructive operations.
# Usage: bash auto_commit.sh "description of upcoming changes"
cd "$(dirname "$0")"
git add -A
git commit -m "${1:-auto-snapshot $(date +%Y%m%d-%H%M%S)}" --allow-empty
echo "Snapshot created: $(git rev-parse --short HEAD)"
