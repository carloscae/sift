"""Tests for sift-queue-watcher.py.

The module filename has dashes so it can't be imported with a normal
`import` statement — loaded via importlib.util instead. All module-level
path globals (QUEUE_DIR, DEAD_DIR, VAULT, ENV_FILE, LAST_RUN_FILE) are
monkeypatched to tmp_path locations before any test calls module.main(), so
none of these tests ever touch Carlos's real ~/.sift-queue.d or vault.
"""
import importlib.util
import json
from pathlib import Path

import pytest

_WATCHER_PATH = Path(__file__).parent.parent / "sift-queue-watcher.py"


def _load_watcher_module():
    spec = importlib.util.spec_from_file_location("sift_queue_watcher", _WATCHER_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def watcher(tmp_vault: Path, tmp_path: Path, monkeypatch):
    module = _load_watcher_module()
    queue_dir = tmp_path / "queue.d"
    dead_dir = queue_dir / ".dead"
    queue_dir.mkdir()

    monkeypatch.setattr(module, "QUEUE_DIR", queue_dir)
    monkeypatch.setattr(module, "DEAD_DIR", dead_dir)
    monkeypatch.setattr(module, "ENV_FILE", tmp_path / "nonexistent.env")
    monkeypatch.setattr(module, "VAULT", str(tmp_vault))
    monkeypatch.setattr(module, "LAST_RUN_FILE", tmp_path / "last-run.json")
    # Never make a real network call in tests, however TELEGRAM_BOT_TOKEN happens
    # to be set in the dev environment.
    monkeypatch.setattr(module, "_tg_send", lambda *a, **k: None)

    (tmp_vault / "vault-ingest.yaml").write_text(f"vault: {tmp_vault}\n")
    return module, queue_dir, dead_dir


def test_dead_letter_path_is_reached_after_max_retries(watcher, monkeypatch):
    """Regression proof for the highest-value bug: the old mark_failed made
    queue status terminal after a single failure, so a re-enqueued item
    vanished from pending_items() on the watcher's second pass, was silently
    classified 'absent', and reported to Carlos as a success — MAX_RETRIES in
    the trigger JSON never actually got hit and .dead/ stayed empty forever.

    With genuine retry-then-terminal semantics in Queue.mark_failed, three
    consecutive failing watcher runs on the same URL must now dead-letter
    the trigger file for real.
    """
    module, queue_dir, dead_dir = watcher

    from sift.extractors.base import ExtractFailure

    def _always_fails(url, work_dir):
        return ExtractFailure(
            url=url, platform="generic", error_class="unknown", error_detail="boom"
        )

    monkeypatch.setattr("sift.pipeline.dispatch_extract", _always_fails)

    trigger = queue_dir / "trigger1.json"
    trigger.write_text(
        json.dumps({"url": "https://example.com/dead-letter-me", "chat_id": "123"})
    )

    for _ in range(3):
        module.main()

    assert not trigger.exists()
    dead_files = list(dead_dir.glob("*.json"))
    assert len(dead_files) == 1
    assert json.loads(dead_files[0].read_text())["url"] == "https://example.com/dead-letter-me"


def test_item_still_pending_after_one_failure_is_not_falsely_confirmed(watcher, monkeypatch):
    """A single failed watcher pass must not send a success confirmation —
    the exact 'absent == false success' bug this session fixes."""
    module, queue_dir, dead_dir = watcher

    from sift.extractors.base import ExtractFailure

    def _always_fails(url, work_dir):
        return ExtractFailure(
            url=url, platform="generic", error_class="unknown", error_detail="boom"
        )

    monkeypatch.setattr("sift.pipeline.dispatch_extract", _always_fails)

    sent_messages = []
    monkeypatch.setattr(
        module, "_tg_send", lambda token, chat_id, text: sent_messages.append(text)
    )

    trigger = queue_dir / "trigger2.json"
    trigger.write_text(
        json.dumps({"url": "https://example.com/one-failure", "chat_id": "123"})
    )

    module.main()

    # Still present (retried, not dead-lettered yet) and no success ✓ sent.
    assert trigger.exists()
    assert not any(m.startswith("✓") for m in sent_messages)
    assert not list(dead_dir.glob("*.json"))
