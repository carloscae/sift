# Roadmap

## v0.2.0 — shipped 2026-05-26

SQLite queue, in-process watcher, budget guard, URL dedup normalization, last-run observability.

- SQLite + WAL mode replaces `queue.json` + fcntl locking. DB at `<state_dir>/queue.db`. Auto-prunes processed/failed rows >30 days old.
- URL normalization for deduplication: strips tracking params (utm_*, `s`, `t`, `si`), resolves `youtu.be/<id>` → `youtube.com/watch?v=<id>`, normalizes `x.com` → `twitter.com`.
- `sift-queue-watcher.py` refactored to in-process execution (direct Python imports instead of spawning a `sift add` subprocess). Writes `~/.sift/last-run.json` after each drain. Log moved to `~/Library/Logs/sift/watcher.log`.
- Dead-letter queue at `~/.sift-queue.d/.dead/` after `MAX_RETRIES=3` failures.
- `YtDlpAudioExtractor` base class in `extractors/ytdlp_base.py` — YouTube and TikTok are now thin subclasses.
- Twitter: fxtwitter API first (fast, no auth); yt-dlp only for video tweets; Playwright soft dependency with clear error if not installed. `extraction_warning` metadata field on degraded fallback results.
- `enriched_by` frontmatter records the actual backend (`openrouter` or `claude-cli`) instead of hardcoding `"openrouter"`.
- `monthly_budget_usd` enforced: checked against `~/.sift/budget.json` before enrichment starts each run.
- `EnricherConfig.backend` is `Literal["openrouter", "claude-cli", "local"]` — typos caught at config load time.
- `sift status` shows last-run timestamp, duration, processed/failed/dead-lettered counts.

## v0.1.2 — shipped 2026-05-25

X/Twitter extractor: yt-dlp for video tweets, fxtwitter API fallback for text threads. t.co short-link resolution. Registered before GenericUrlExtractor in dispatcher. 58 tests.

## v0.1.1 — shipped 2026-05-25

Wired transcription to local whisper-svc (port 8742) instead of OpenRouter audio endpoint. Removed `model_stt`/Groq dependency. 54 tests.

## whisper-svc — shared transcription service (prerequisite for v0.1.1)

A small FastAPI service wrapping mlx-whisper (Whisper Large v3 Turbo). Lives in a separate repo. Runs as a LaunchAgent on the Mac Mini — process always up (~50 MB idle), model loads on demand per request and unloads immediately after (~1.5 GB active, zero when idle). Exposes `POST /transcribe` accepting an audio file, returns transcript text.

Shared across all callers: sift, iPhone shortcuts (via Tailscale), and the Telegram bridge. One service, one model, one place to update.

## v0.1.0 — shipped 2026-05-19

YouTube + TikTok audio extraction (yt-dlp), generic article extraction (readability-lxml), OpenRouter chat-completions for summarisation and image captioning, queue + writer + CLI, GitHub Actions CI. 51 tests.

## v0.3.0 — Instagram + failure handling

- Instagram (yt-dlp via cookie file)
- `scan_raw` includes `failed` items in the seen-source check; explicit `--retry-failed` flag on `sift run`.
- Per-stage status on `QueueEntry` so "extraction worked, enrichment didn't" is distinguishable from "extraction failed."
- Failure log surfaced via `sift status --verbose` with per-entry error_class.

## Parked — revisit after 60 days of real usage

The items below are either OSS-facing polish or infrastructure for scale. Parked until there is real usage data to justify them.

**Scheduling (`sift watch`):** Long-running loop with cron schedule, launchd/systemd templates, locking. Useful once the Telegram bridge is running and the capture habit is established.

**OSS launch polish:** `sift diagnose`, RAM guard, `[private]` keyword filtering, `raw_ttl_days` enforcement, CONTRIBUTING.md, code of conduct, issue/PR templates.

**Hard launch:** Soft launch on audience channels, HN + Reddit r/ObsidianMD, documentation site. Only meaningful once the tool has been running reliably for 60+ days.

**Additional extractors:** Reddit, BlueSky, Substack, Notion-public, Mirror. Add when there is an actual capture habit driving demand.

**HTTP endpoint:** `POST {url, vault_id}` for browser extensions and mobile shortcuts.

**Local summarisation:** llama.cpp or Ollama for offline summarisation. The transcription story is already local via whisper-svc; summarisation via OpenRouter costs ~$0.001/item and is not a meaningful expense at personal scale.

---

For the original full design and the executable plan that delivered v0.1.0, see Carlos's private Obsidian vault docs `vault-ingest-design.md` and `vault-ingest-plan-v1.md`. They are not in this repo because they include personal infrastructure decisions outside sift's public scope.
