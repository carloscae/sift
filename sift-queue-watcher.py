#!/usr/bin/env python3
# Drains .sift-queue.d — called by WatchPaths LaunchAgent
import json
import os
import subprocess
import sys
from pathlib import Path

QUEUE_DIR = Path("/Users/carlosvargas/.sift-queue.d")
VAULT = "/Users/carlosvargas/Library/Mobile Documents/iCloud~md~obsidian/Documents/Ideaverse"
SIFT_BIN = "/Users/carlosvargas/Projects/sift/.venv/bin/sift"
ENV_FILE = Path("/Users/carlosvargas/.sift/.env")


def _load_env() -> dict:
    """Load extra env vars from ~/.sift/.env (KEY=VALUE lines, # comments ok)."""
    env = {}
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                env[k.strip()] = v.strip()
    return env


_extra_env = _load_env()
_proc_env = {**os.environ, **_extra_env}

for f in sorted(QUEUE_DIR.glob("*.json")):
    try:
        entry = json.loads(f.read_text())
        url = entry["url"]
        subprocess.run(
            [SIFT_BIN, "add", url, "--vault", VAULT, "--now"],
            check=True,
            env=_proc_env,
        )
        f.unlink()
    except Exception as e:
        print(f"FAILED {f.name}: {e}", file=sys.stderr)
