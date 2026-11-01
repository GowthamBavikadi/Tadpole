#!/usr/bin/env bash
# run.sh - Brain macOS Desktop Pet & Terminal CLI
set -e
cd "$(dirname "$0")"

# Create venv if it doesn't exist
if [ ! -d "venv" ]; then
  echo "[setup] Setting up virtual environment..."
  python3 -m venv venv
  ./venv/bin/pip install -q -r requirements.txt
fi

MODE="${1:-pet}"

if [ "$MODE" = "--cli" ] || [ "$MODE" = "cli" ]; then
  echo "Launching Brain Terminal CLI..."
  exec ./venv/bin/python3 src/brain.py
elif [ "$MODE" = "--watcher" ] || [ "$MODE" = "watcher" ]; then
  echo "Starting Inbox Drop Watcher daemon (~/Desktop/Brain_Drop)..."
  exec ./venv/bin/python3 src/watcher.py
else
  echo "Launching Brain macOS Desktop Pet..."
  exec ./venv/bin/python3 src/pet_main.py
fi
