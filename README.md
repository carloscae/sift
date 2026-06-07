# sift

[![Build](https://github.com/carloscae/sift/actions/workflows/test.yml/badge.svg)](https://github.com/carloscae/sift/actions/workflows/test.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://python.org)

**The working bridge between social media and your second brain.**

Drop a link to a TikTok, an X thread, a YouTube video, or a generic article into your Obsidian vault. Get a clean, transcribed, summarized markdown note back. URL in, note out. Local-first, pluggable AI backends, opinionated.

We maintain extractors for the platforms that fight scraping the hardest, so you don't have to.

## Status

v0.2.0 — working daily driver.

- **Extractors:** YouTube, TikTok, X/Twitter (video + text threads), generic articles
- **Transcription:** local via [whisper-svc](https://github.com/carloscae/whisper-svc) (Whisper Large v3 Turbo, MLX)
- **Summarisation:** two backends — `claude-cli` (uses your Claude subscription) or `openrouter` (OpenRouter API)
- **Telegram bridge:** send a URL from your phone → note appears in vault automatically

## Quickstart

```bash
pip install sift
sift init ~/Documents/MyVault
```

Pick a summarisation backend in `~/Documents/MyVault/vault-ingest.yaml`:

**Option A — Claude CLI** (uses your existing Claude Code subscription, no extra API key):
```yaml
enricher:
  backend: claude-cli
  claude_cli:
    claude_bin: /path/to/claude   # find with: which claude
    whisper_svc_url: http://localhost:8742
```

**Option B — OpenRouter** (pay-per-token, ~$0.0001/clip with Gemini Flash Lite):
```yaml
enricher:
  backend: openrouter
  openrouter:
    api_key_env: OPENROUTER_API_KEY
    whisper_svc_url: http://localhost:8742
    model_text: google/gemini-2.5-flash-lite
    model_vision: google/gemini-2.5-flash
```

Then run:
```bash
sift add https://www.youtube.com/watch?v=jNQXAC9IVRw --vault ~/Documents/MyVault --now
```

Open `~/Documents/MyVault/captures/` — your note is there with title, summary, and full transcript.

**Transcription requires [whisper-svc](https://github.com/carloscae/whisper-svc) running locally.**

## Why not just use \<obvious alternative\>?

Most "save to second brain" tools either stop at clipping the URL or work only for clean articles. sift commits to maintaining the gnarly per-platform extraction layer — the part that breaks every few weeks when TikTok rotates its anti-scrape defenses. That maintenance commitment is the differentiator.

## sift status

```
$ sift status
2 pending
  • [URL] https://www.youtube.com/watch?v=abc123
  • [URL] https://x.com/user/status/456
Last run: 2026-05-26T08:14:03+00:00 (4.2s) — 1 processed, 0 failed, 0 dead-lettered
```

The last-run data is read from `~/.sift/last-run.json`, written by `sift-queue-watcher.py` after each drain. If you use `sift run` directly (no watcher), this file is not written.

## Configuration

See `vault-ingest.yaml.example` for a full annotated config. The `raw_dir` and `state_dir` fields accept absolute paths, so you can keep scratch files outside your vault (useful for iCloud vaults).

Key options:

```yaml
enricher:
  backend: openrouter         # openrouter | claude-cli | local
  monthly_budget_usd: 10      # optional; caps total openrouter spend per calendar month
```

`monthly_budget_usd` is enforced at run time: if the month's spend (tracked in `~/.sift/budget.json`) meets or exceeds the cap, the enricher is skipped for that batch. Items are still written to `captures/` but without transcript or summary.

## Log and dead-letter locations

- **Watcher log:** `~/Library/Logs/sift/watcher.log`
- **Dead-letter queue:** `~/.sift-queue.d/.dead/` — items moved here after 3 consecutive failures. Inspect the JSON for the error, fix the cause, then re-add the URL with `sift add <url>`.

## Architecture + roadmap

- [ARCHITECTURE.md](ARCHITECTURE.md) — pipeline stages, registries, data contracts, how to add an extractor or enricher backend.
- [ROADMAP.md](ROADMAP.md) — what's coming next.
- [Issues](https://github.com/carloscae/sift/issues) — open work.

## License

MIT
