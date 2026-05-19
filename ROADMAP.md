# Roadmap

## v0.1.0 — shipped 2026-05-19

YouTube + TikTok audio extraction (yt-dlp), generic article extraction (readability-lxml), OpenRouter chat-completions for summarisation and image captioning, queue + writer + CLI, GitHub Actions CI. 51 tests.

Known limitation: real audio transcription does not work, see issue #1.

## v0.1.1 — fix transcription (next)

The only blocker between v0.1.0 (draft release) and v0.1.0 (public release).

Swap `OpenRouterEnricher.transcribe()` from `/audio/transcriptions` (which OpenRouter does not implement) to a `/chat/completions` flow that passes audio as a message attachment.

Candidate models to evaluate: `openai/gpt-audio-mini`, `google/gemini-2.5-flash` with audio input, `google/gemini-2.5-pro`. Pick the cheapest one that returns reliable transcripts for 60-second audio clips.

Acceptance: `sift add https://www.youtube.com/watch?v=jNQXAC9IVRw --vault /tmp/v --now` produces a capture with a non-empty transcript and `status: raw`.

Also in this release:

- Update `_STT_COST_PER_SEC` table or replace it with per-token pricing in the chat-completions code path.
- Drop the issue-#1 warning from `README.md`; restore a YouTube-based quickstart.
- Publish the draft GitHub release.

## v0.2.0 — more extractors + failure handling (Phase 4)

Six new extractors to round out the social-media stack:

- Instagram (yt-dlp via cookie file)
- X video (yt-dlp)
- X text threads (fxtwitter / nitter fallback)
- Reddit (yt-dlp for videos; pushshift/json API for text)
- BlueSky (`atproto` library)
- Substack / Notion-public / Mirror (specialised article handlers if the generic readability fallback isn't good enough)

Plus failure handling improvements:

- `scan_raw` includes `failed` items in the seen-source check; explicit `--retry-failed` flag on `sift run`.
- Per-stage status on `QueueEntry` so "extraction worked, enrichment didn't" is distinguishable from "extraction failed."
- Failure log surfaced via `sift status --verbose` with per-entry error_class.
- T2 fallback prompts: when extraction fails, the capture file includes a clear "drop a screenshot / save the audio manually in raw/" suggestion.

## v0.3.0 — launch-quality polish (Phase 5)

Things that don't add features but make the tool ship-ready for an external audience:

- `sift diagnose` command: check Python version, ffmpeg, yt-dlp, OR API key, and write a one-paragraph status.
- RAM guard: refuse to load >500MB audio into memory; stream instead.
- Cost cap: enforce `monthly_budget_usd` from config; refuse enrichment when over.
- `[private]` keyword honoured: skip enrichment for captures whose title or content contains the configured private keywords.
- `raw_ttl_days` enforced: delete raw files older than N days on each `sift run`.
- CONTRIBUTING.md, code of conduct, issue/PR templates.

## v0.4.0 — scheduling (Phase 6)

Run unattended.

- `sift watch` command (long-running loop with cron schedule from config).
- Launchd template (macOS), systemd template (Linux), cron template (universal).
- Locking so two scheduled runs can't trample each other.
- `--quiet` mode for cron-suitable output.

## v0.5.0 — Telegram bridge (Phase 8)

Carlos's personal cutover happens here. A small bridge worker that polls a Telegram bot for messages forwarded to it and drops them into the configured vault's `raw/`. Telegram is just one ingress; the architecture stays vault-agnostic.

This is the phase where Carlos retires his hand-built Telegram-to-vault pipeline and runs the public product on himself.

## v0.6.0 — HTTP endpoint (Phase 7 / 9)

A POST endpoint that accepts `{url, file_url, vault_id}` and queues an item. Lets browser extensions, mobile shortcuts, and arbitrary scripts feed sift without shelling out to the CLI. Same auth model as OpenRouter (env var or config).

## v1.0.0 — hard launch (Phase 10 / 11)

After v0.4 ships:

- Soft launch: post on the OSS-clout audience channels Carlos has, gather feedback for 2-4 weeks.
- Hard launch: HN + Reddit r/ObsidianMD + Mastodon. README rewrite oriented around the elevator pitch + a 30-second demo gif.
- A documentation site (mkdocs or astro starlight) — `sift.dev` is not registered yet.

## v1.1.0 — local enricher (Phase 12)

Local-model backend that runs entirely offline. whisper.cpp for STT, llama.cpp or Ollama for summarisation, llava for vision/OCR. The config schema already supports `backend: local` (currently raises `NotImplementedError`).

This is the privacy story. Users who don't want to send transcripts to OpenRouter (or any cloud provider) can run sift without a network connection.

## Beyond v1.1

Open questions, not committed:

- Browser extension that captures the current tab as a sift `add`.
- Mobile app (or PWA) for capture-on-the-go (Carlos's iOS Shortcut already covers this for him, but a packaged version helps others).
- Vault search / re-summarise: pick a capture and re-run enrichment with a different model.
- Multi-vault routing (the config schema is single-vault today).

---

For the original full design and the executable plan that delivered v0.1.0, see Carlos's private Obsidian vault docs `vault-ingest-design.md` and `vault-ingest-plan-v1.md`. They are not in this repo because they include personal infrastructure decisions outside sift's public scope.
