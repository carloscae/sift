#!/usr/bin/env python3
# Drains .sift-queue.d — called by WatchPaths LaunchAgent
import json
import os
import subprocess
import sys
import urllib.request
from pathlib import Path

QUEUE_DIR = Path("/Users/carlosvargas/.sift-queue.d")
VAULT = Path("/Users/carlosvargas/Library/Mobile Documents/iCloud~md~obsidian/Documents/Ideaverse")
CAPTURES_DIR = VAULT / "captures"
SIFT_BIN = "/Users/carlosvargas/Projects/sift/.venv/bin/sift"
ENV_FILE = Path("/Users/carlosvargas/.sift/.env")


def _load_env() -> dict:
    env = {}
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                env[k.strip()] = v.strip()
    return env


def _tg_send(token: str, chat_id: str, text: str) -> None:
    try:
        payload = json.dumps({"chat_id": chat_id, "text": text}).encode()
        req = urllib.request.Request(
            f"https://api.telegram.org/bot{token}/sendMessage",
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        urllib.request.urlopen(req, timeout=10)
    except Exception as e:
        print(f"telegram notify failed: {e}", file=sys.stderr)


def _new_capture_title(before: set) -> str | None:
    try:
        after = set(CAPTURES_DIR.glob("*.md"))
        new_files = after - before
        if not new_files:
            return None
        newest = sorted(new_files, key=lambda p: p.stat().st_mtime)[-1]
        for line in newest.read_text().splitlines():
            if line.startswith("# "):
                return line[2:].strip()
    except Exception:
        pass
    return None


_extra_env = _load_env()
_proc_env = {**os.environ, **_extra_env}
_bot_token = _extra_env.get("TELEGRAM_BOT_TOKEN") or os.environ.get("TELEGRAM_BOT_TOKEN")

for f in sorted(QUEUE_DIR.glob("*.json")):
    entry = json.loads(f.read_text())
    url = entry["url"]
    chat_id = entry.get("chat_id")

    captures_before = set(CAPTURES_DIR.glob("*.md")) if CAPTURES_DIR.exists() else set()

    try:
        subprocess.run(
            [SIFT_BIN, "add", url, "--vault", str(VAULT), "--now"],
            check=True,
            env=_proc_env,
        )
        f.unlink()

        if _bot_token and chat_id:
            title = _new_capture_title(captures_before)
            msg = f"✓ {title}" if title else "✓ saved to captures/"
            _tg_send(_bot_token, chat_id, msg)

    except Exception as e:
        print(f"FAILED {f.name}: {e}", file=sys.stderr)
        if _bot_token and chat_id:
            _tg_send(_bot_token, chat_id, f"❌ sift failed: {str(e)[:200]}")
