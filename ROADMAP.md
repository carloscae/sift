# Roadmap

## v0.1.0 — shipped 2026-05-19

YouTube + TikTok audio extraction (yt-dlp), generic article extraction (readability-lxml), OpenRouter chat-completions for summarisation and image captioning, queue + writer + CLI, GitHub Actions CI. 51 tests.

Known limitation: real audio transcription does not work, see issue #1.

## whisper-svc — shared transcription service (prerequisite for v0.1.1)

A small FastAPI service wrapping mlx-whisper (Whisper Large v3 Turbo). Lives in a separate repo. Runs as a LaunchAgent on the Mac Mini — process always up (~50 MB idle), model loads on demand per request and unloads immediately after (~1.5 GB active, zero when idle). Exposes `POST /transcribe` accepting an audio file, returns transcript text.

Shared across all callers: sift, iPhone shortcuts (via Tailscale), and the future Telegram bridge. One service, one model, one place to update.

## v0.1.1 — shipped 2026-05-25

Wired transcription to local whisper-svc (port 8742) instead of OpenRouter audio endpoint. Removed `model_stt`/Groq dependency. 54 tests.

## v0.1.2 — shipped 2026-05-25

X/Twitter extractor: yt-dlp for video tweets, fxtwitter API fallback for text threads. t.co short-link resolution. Registered before GenericUrlExtractor in dispatcher. 58 tests.

## v0.2.0 — Telegram bridge (in progress)

Send a URL to the personal Telegram bot → sift picks it up automatically. UX north star for daily use.

Architecture:
- tgbot (Docker) detects bare URLs in personal chat, writes JSON to `/vault/.sift-queue.d/`
- Host LaunchAgent (`com.carloscae.sift-watcher`) wakes on WatchPaths, calls `sift add <url> --now`, deletes the JSON
- Vault `vault-ingest.yaml` configured (done)
- Queue dir `.sift-queue.d/` created in vault (done)
- `sift-queue-watcher.py` and LaunchAgent plist written and loaded (done)

**Remaining:** Apply `tgbot-url-routing.patch` to `/Volumes/External/docker/config/tgbot/bot.py`, rebuild tgbot, smoke test.

## v0.3.0 — Instagram + failure handling

- Instagram (yt-dlp via cookie file)
- `scan_raw` includes `failed` items in the seen-source check; explicit `--retry-failed` flag on `sift run`.
- Per-stage status on `QueueEntry` so "extraction worked, enrichment didn't" is distinguishable from "extraction failed."
- Failure log surfaced via `sift status --verbose` with per-entry error_class.

## Parked — revisit after 60 days of real usage

The items below are either OSS-facing polish or infrastructure for scale. Parked until there is real usage data to justify them.

**Scheduling (`sift watch`):** Long-running loop with cron schedule, launchd/systemd templates, locking. Useful once the Telegram bridge is running and the capture habit is established.

**OSS launch polish:** `sift diagnose`, RAM guard, cost cap enforcement, `[private]` keyword filtering, `raw_ttl_days`, CONTRIBUTING.md, code of conduct, issue/PR templates.

**Hard launch:** Soft launch on audience channels, HN + Reddit r/ObsidianMD, documentation site. Only meaningful once the tool has been running reliably for 60+ days.

**Additional extractors:** Reddit, BlueSky, Substack, Notion-public, Mirror. Add when there is an actual capture habit driving demand.

**HTTP endpoint:** `POST {url, vault_id}` for browser extensions and mobile shortcuts. Revisit alongside or after the Telegram bridge.

**Local summarisation:** llama.cpp or Ollama for offline summarisation. The transcription story is already local via whisper-svc; summarisation via OpenRouter costs ~$0.001/item and is not a meaningful expense at personal scale.

---

For the original full design and the executable plan that delivered v0.1.0, see Carlos's private Obsidian vault docs `vault-ingest-design.md` and `vault-ingest-plan-v1.md`. They are not in this repo because they include personal infrastructure decisions outside sift's public scope.
