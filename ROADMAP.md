# Roadmap

## v0.1.0 — shipped 2026-05-19

YouTube + TikTok audio extraction (yt-dlp), generic article extraction (readability-lxml), OpenRouter chat-completions for summarisation and image captioning, queue + writer + CLI, GitHub Actions CI. 51 tests.

Known limitation: real audio transcription does not work, see issue #1.

## whisper-svc — shared transcription service (prerequisite for v0.1.1)

A small FastAPI service wrapping mlx-whisper (Whisper Large v3 Turbo). Lives in a separate repo. Runs as a LaunchAgent on the Mac Mini — process always up (~50 MB idle), model loads on demand per request and unloads immediately after (~1.5 GB active, zero when idle). Exposes `POST /transcribe` accepting an audio file, returns transcript text.

Shared across all callers: sift, iPhone shortcuts (via Tailscale), and the future Telegram bridge. One service, one model, one place to update.

## v0.1.1 — wire transcription to whisper-svc

Drop the broken `OpenRouterEnricher.transcribe()` path entirely. sift calls `whisper-svc` at `http://localhost:PORT/transcribe` instead. OpenRouter stays for summarisation and image captioning.

- Replace `transcribe()` with an HTTP call to whisper-svc
- Remove `_STT_COST_PER_SEC` table (transcription is now local, zero cost)
- Drop the issue-#1 warning from `README.md`; restore a YouTube-based quickstart

Acceptance: `sift add https://www.youtube.com/watch?v=jNQXAC9IVRw --vault /tmp/v --now` produces a capture with a non-empty transcript and `status: raw`.

## v0.2.0 — Instagram + X extractors + failure handling

The two platforms missing from the current stack:

- Instagram (yt-dlp via cookie file)
- X video (yt-dlp)
- X text threads (fxtwitter / nitter fallback)

Failure handling improvements deferred from v0.1.0:

- `scan_raw` includes `failed` items in the seen-source check; explicit `--retry-failed` flag on `sift run`.
- Per-stage status on `QueueEntry` so "extraction worked, enrichment didn't" is distinguishable from "extraction failed."
- Failure log surfaced via `sift status --verbose` with per-entry error_class.

## v0.3.0 — Telegram bridge

Send a link or audio to a Telegram bot like sharing with a friend. The bot detects content type, routes to the right extractor, enriches, and writes a capture note to the vault. Replaces the current iPhone shortcut + manual inbox flow.

- Telegram bot worker (polling mode, no webhook required for personal use)
- Routes URLs to existing sift extractors; audio messages to whisper-svc
- Writes directly to configured vault path
- Accessible via Tailscale from iPhone

This is the UX north star for personal use.

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
