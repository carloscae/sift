#!/usr/bin/env python3
# Drains .sift-queue.d — called by WatchPaths LaunchAgent
import json
import subprocess
import sys
from pathlib import Path

QUEUE_DIR = Path("/Users/carlosvargas/Library/Mobile Documents/iCloud~md~obsidian/Documents/Ideaverse/.sift-queue.d")
VAULT = "/Users/carlosvargas/Library/Mobile Documents/iCloud~md~obsidian/Documents/Ideaverse"
SIFT_BIN = "/Users/carlosvargas/Projects/sift/.venv/bin/sift"

for f in sorted(QUEUE_DIR.glob("*.json")):
    try:
        entry = json.loads(f.read_text())
        url = entry["url"]
        subprocess.run([SIFT_BIN, "add", url, "--vault", VAULT, "--now"], check=True)
        f.unlink()
    except Exception as e:
        print(f"FAILED {f.name}: {e}", file=sys.stderr)
