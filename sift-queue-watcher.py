#!/usr/bin/env python3
# Drains .sift-queue.d — called by WatchPaths LaunchAgent
import json
import os
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

QUEUE_DIR = Path("/Users/carlosvargas/.sift-queue.d")
DEAD_DIR = QUEUE_DIR / ".dead"
ENV_FILE = Path("/Users/carlosvargas/.sift/.env")
VAULT = "/Users/carlosvargas/Library/Mobile Documents/iCloud~md~obsidian/Documents/Ideaverse"
LAST_RUN_FILE = Path("/Users/carlosvargas/.sift/last-run.json")
MAX_RETRIES = 3

UTC = timezone.utc


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


def _latest_capture_title(captures_path: Path) -> str:
    """Return the frontmatter title of the most recently modified capture file."""
    try:
        latest = max(captures_path.glob("*.md"), key=os.path.getmtime, default=None)
        if latest is None:
            return "✓ saved to captures/"
        for line in latest.read_text(errors="replace").splitlines():
            if line.startswith("title:"):
                title = line.partition(":")[2].strip().strip('"').strip("'")
                if title:
                    return f"✓ {title}"
    except Exception:
        pass
    return "✓ saved to captures/"


if __name__ == "__main__":
    # Ensure log directory exists when LaunchAgent first fires
    Path.home().joinpath("Library/Logs/sift").mkdir(parents=True, exist_ok=True)

    _extra_env = _load_env()

    # Inject extra env into process so sift can pick up keys (e.g. OPENROUTER_API_KEY)
    os.environ.update(_extra_env)

    _bot_token = _extra_env.get("TELEGRAM_BOT_TOKEN") or os.environ.get("TELEGRAM_BOT_TOKEN")

    DEAD_DIR.mkdir(parents=True, exist_ok=True)
    LAST_RUN_FILE.parent.mkdir(parents=True, exist_ok=True)

    from sift.config import load_config
    from sift.pipeline import confirmation_for, process_pending
    from sift.queue import Queue

    config = load_config(Path(VAULT) / "vault-ingest.yaml")

    start_time = time.time()
    n_processed = 0
    n_failed = 0
    n_dead = 0

    for f in sorted(QUEUE_DIR.glob("*.json")):
        # Finding 17 — wrap each file's read+process in try/except for JSONDecodeError
        try:
            entry = json.loads(f.read_text())
        except Exception as e:
            print(f"SKIPPED {f.name}: malformed JSON — {e}", file=sys.stderr)
            continue

        url = entry["url"]
        chat_id = entry.get("chat_id")
        retries = entry.get("retries", 0)

        try:
            queue = Queue(config)
            item_id = queue.enqueue_url(url)
            run = process_pending(config)
            saved, msg = confirmation_for(
                item_id, run, lambda: _latest_capture_title(config.captures_path)
            )
            if not saved:
                # Item drained but did not save: fail this trigger file so the
                # retry / dead-letter path below runs and no success is sent.
                raise RuntimeError(f"capture did not save for {url}")
            f.unlink()
            n_processed += 1

            if _bot_token and chat_id and msg:
                _tg_send(_bot_token, chat_id, msg)

        except Exception as e:
            print(f"FAILED {f.name}: {e}", file=sys.stderr)
            n_failed += 1

            # Finding 4 — increment retry counter; dead-letter after MAX_RETRIES
            retries += 1
            if retries >= MAX_RETRIES:
                n_failed -= 1  # moving to dead, not staying failed
                n_dead += 1
                dead_path = DEAD_DIR / f.name
                f.rename(dead_path)
                print(f"DEAD-LETTERED {f.name} after {retries} attempts", file=sys.stderr)
                if _bot_token and chat_id:
                    _tg_send(
                        _bot_token,
                        chat_id,
                        f"💀 dead-lettered after {retries} failures: {url}\n{str(e)[:200]}",
                    )
            else:
                entry["retries"] = retries
                f.write_text(json.dumps(entry))
                if _bot_token and chat_id:
                    _tg_send(_bot_token, chat_id, f"❌ sift failed (attempt {retries}/{MAX_RETRIES}): {str(e)[:200]}")

    last_run = {
        "timestamp": datetime.now(UTC).isoformat(),
        "processed": n_processed,
        "failed": n_failed,
        "dead_lettered": n_dead,
        "duration_sec": round(time.time() - start_time, 1),
    }
    LAST_RUN_FILE.write_text(json.dumps(last_run, indent=2))
