# sift — Claude project memory

> Single source of truth for any Claude session working in this repo. Read this first.

## What sift is

`sift` is a Python CLI that turns URLs (and files) into clean markdown notes in an Obsidian-style vault. URL in, note out: extract → transcribe/summarise → write capture with structured frontmatter. The differentiator is the extractor layer: per-platform handlers that survive when TikTok/YouTube/X rotate their anti-scrape defences. That maintenance commitment is the moat.

Vault-agnostic by design. Carlos's personal Telegram setup is one of N optional ingresses, not a private adapter. The public product must be a strict superset of Carlos's use.

## Owner + contact

Carlos Vargas — `carlos@carloscae.com` — GitHub `carloscae`.

## Repo state (verified 2026-11-05)

- **Tags:** `v0.1.0`, `v0.1.1` only (`git tag`). The v0.2.0 work is on `main` but untagged, and `src/sift/version.py` and `pyproject.toml` still say `0.1.0`. No GitHub release exists (`gh release list`).
- **CI:** GitHub Actions `test` workflow (ruff + pytest) runs on push/PR to `main`; latest run green 2026-11-05 (`gh run list`). Trunk-based development; no feature branches yet.
- **Tests:** 102 passing, ruff clean (`uv run pytest -q`, `uv run ruff check src tests`, 2026-11-05). Coverage focuses on contracts, not mocks.
- **Phases shipped:** v0.1.0 (Phases 0–3), v0.1.1 (transcription), v0.1.2 (Twitter), v0.2.0 work, untagged (SQLite queue, in-process watcher, budget guard, URL normalization, YtDlpAudioExtractor base, observability).

## What works end-to-end today

```bash
sift init <vault>
sift add https://example.com/some-article --now --vault <vault>
# Result: captures/<date>-<slug>-<id>.md with title, summary, full article text.
```

- Article URLs through `GenericUrlExtractor` (httpx + readability-lxml) and either enricher backend. Full pipeline.
- YouTube and TikTok URLs through yt-dlp: audio downloads, whisper-svc transcription, summarisation. Full pipeline.
- X/Twitter URLs through fxtwitter (text/photos) or yt-dlp (video tweets). t.co resolution. Playwright path for `x.com/i/article/` (declared in `pyproject.toml`, import guarded; Chromium needs `playwright install chromium`).
- Image captioning via OpenRouter Gemini Flash (`caption()`), reached with `sift add <image file>` (copied to `raw/`). openrouter backend only: `ClaudeCliEnricher.caption` raises `NotImplementedError`.
- Queue persistence at `<vault>/.vault-ingest/queue.db` (SQLite, WAL mode). URL dedup via normalization. Auto-prune >30 days.
- Budget guard: `monthly_budget_usd` in config enforced against `~/.sift/budget.json`.
- `sift status` lists pending items + last-run stats (timestamp, duration, processed/failed/dead-lettered).
- Telegram bridge: URL drop → `~/.sift-queue.d/*.json` → watcher → capture → Telegram confirmation.
- Dead-letter queue at `~/.sift-queue.d/.dead/` after 3 failures.

## What does NOT work / known gaps

- A failure is retried up to `Queue.MAX_ATTEMPTS` (3), then the row is terminal `failed`. `sift add <url>` resets a terminal-failed URL; a terminal-failed file in `raw/` stays `failed` with no CLI path to retry it (`scan_raw` returns it but `process_pending` only runs `pending` rows). Explicit `--retry-failed` is v0.3.0.
- No content filtering: `config.private_caption_keywords` is defined but never read.
- No rate-limit or backoff handling (retries are count-based only, 3 attempts). `httpx` is sync.
- `OCRResult` type is exported but never produced (the caption path uses `CaptionResult`).
- Queue has no per-step status — a failure marks the whole item failed, losing partial progress.

## Architecture (one-screen summary)

Full version in `ARCHITECTURE.md`.

```
sift add <target>            sift run
        │                        │
        v                        v
   ┌────────────────────────────────────┐
   │ classify (URL kind / file kind)    │
   └────────────────────────────────────┘
                 │
                 v
   ┌────────────────────────────────────┐
   │ queue (.vault-ingest/queue.db)     │
   │   pending / processed / failed     │
   └────────────────────────────────────┘
                 │
                 v   ┌──────────────────────────┐
                 ├──>│ extractor.dispatch (URL) │ → yt-dlp / readability
                 │   └──────────────────────────┘
                 │
                 v
   ┌────────────────────────────────────┐
   │ enricher (openrouter | claude-cli) │
   │   transcribe → summarise → caption │
   └────────────────────────────────────┘
                 │
                 v
   ┌────────────────────────────────────┐
   │ writer (markdown + YAML frontmat)  │
   │   captures/YYYY-MM-DD-slug-id.md   │
   └────────────────────────────────────┘
```

Two registries underpin the pluggability:

- **Extractor registry** (`src/sift/extractors/`): module-level `_REGISTRY` populated at import time via `__init__.py`'s side-effect `_register_builtins()` call. Order is load-bearing: specific extractors before `GenericUrlExtractor` (catch-all). Test isolation handled by an autouse `_clear_extractor_registry` fixture in `tests/conftest.py`.
- **Enricher registry** (`src/sift/enricher/registry.py`): `build_enricher(config)` reads the backend name (`Literal["openrouter", "claude-cli", "local"]`) and returns the right `Enricher` subclass. Both `openrouter` and `claude-cli` are wired; `local` raises `NotImplementedError` (v1.1 target).

## File map

| Path | Purpose |
|---|---|
| `src/sift/cli.py` | Click CLI: `init`, `add`, `run`, `status`. `--vault` resolves from arg, `$SIFT_VAULT`, or cwd. `--config <path>` (or `$SIFT_CONFIG`) overrides the default `<vault>/vault-ingest.yaml` location, so the config can live in a hidden sub-folder. |
| `src/sift/config.py` | Pydantic `Config` model loaded from `vault-ingest.yaml`. `OpenRouterConfig` + `ClaudeCliConfig` + `EnricherConfig` nested. `EnricherConfig.backend` is `Literal["openrouter", "claude-cli", "local"]`. |
| `src/sift/classify.py` | `classify_url(url)` and `classify_path(path)` returning typed `Item`. Hostname → platform mapping. |
| `src/sift/queue.py` | SQLite-backed queue (WAL mode). SHA256-prefix item IDs derived from normalized URLs. `scan_raw` is batched. Auto-prunes processed/failed rows >30 days on init. |
| `src/sift/writer.py` | Markdown emission. python-slugify for non-Latin title safety. Frontmatter: `type`, `subtype`, `date`, `source`, `platform`, `status`, `tags` (+ `summary_status` when degraded). No version or cost stamp (tests assert `enrich-cost-usd` is absent). |
| `src/sift/pipeline.py` | Orchestrator. URL → dispatch_extract → enrich → write. File → enrich-file → write. Cleans work_dir in a `finally`. |
| `src/sift/extractors/base.py` | `Extractor` ABC, `ExtractResult` / `ExtractFailure`, `_REGISTRY` + helpers. |
| `src/sift/extractors/dispatch.py` | `dispatch_extract(url, work_dir)` parses hostname, routes to extractor, wraps exceptions in `ExtractFailure`. |
| `src/sift/extractors/ytdlp_base.py` | `YtDlpAudioExtractor` base class. Owns yt-dlp options + ffmpeg post-processor. Subclasses declare `platform` + `_HOSTS`. |
| `src/sift/extractors/{youtube,tiktok}.py` | Thin subclasses of `YtDlpAudioExtractor`. |
| `src/sift/extractors/twitter.py` | fxtwitter first (text/photo), yt-dlp for video tweets, Playwright for article URLs. Import guarded; raises `RuntimeError` if Playwright is missing. |
| `src/sift/extractors/generic_url.py` | httpx + readability-lxml catch-all. Must be registered last. |
| `src/sift/extractors/__init__.py` | Side-effect: `_register_builtins()` registers TikTok → YouTube → Twitter → Generic (order matters). |
| `src/sift/enricher/base.py` | `Enricher` ABC + `TranscriptResult` / `CaptionResult` / `OCRResult` / `SummaryResult`. |
| `src/sift/enricher/openrouter.py` | OpenRouter-backed enricher. `_raise_with_body` surfaces response body in HTTPStatusError. |
| `src/sift/enricher/claude_cli.py` | claude-cli-backed enricher. Summarisation via `claude -p`. Transcription via whisper-svc. `cost_usd=0.0`. |
| `src/sift/enricher/registry.py` | `build_enricher(config)` factory. Raises `RuntimeError` if API key env var unset. |
| `sift-queue-watcher.py` | LaunchAgent script. Drains `~/.sift-queue.d/*.json` in-process. Writes `~/.sift/last-run.json`. Dead-letters after 3 failures. |
| `src/sift/version.py` | Single source of truth for `__version__`. |
| `tests/conftest.py` | `tmp_vault` fixture + autouse `_clear_extractor_registry`. |
| `vault-ingest.yaml.example` | Full config example at repo root. |
| `.github/workflows/test.yml` | CI: ruff + pytest with coverage. |

## Conventions

- **Python 3.11+.** No legacy code paths.
- **uv** for everything. `uv sync`, `uv run pytest`, `uv run ruff check src tests`. Never call `pip` directly.
- **TDD discipline.** Write a failing test, watch it fail for the right reason, implement, watch it pass, commit. Every feature commit on this repo so far followed this. Don't break the pattern.
- **Pydantic v2 for all data models.** No dicts-as-types. No dataclasses.
- **structlog for logging.** Event-name first arg, kwargs for context. Example: `logger.warning("extractor-failed", url=url, platform=p, error=str(e))`.
- **Ruff config in `pyproject.toml` is authoritative.** Selected rules: E, F, I, B, UP, SIM. Line length 100. Target py311.
- **No `requirements.txt`.** Deps live in `pyproject.toml`. `uv.lock` is committed for reproducibility.
- **No `--no-verify` on commits.** No `--force` pushes. New commits, never amend published commits.
- **Filename pattern for captures:** `{YYYY-MM-DD}-{slug}-{item_id[:6]}.md`. Slug via python-slugify with `word_boundary=True, save_order=True`.
- **Extractor registration order is load-bearing.** When adding a new platform extractor, `register_extractor(NewPlatform())` MUST be inserted BEFORE `GenericUrlExtractor` in `src/sift/extractors/__init__.py::_register_builtins`. Otherwise the catch-all will swallow it.
- **Side-effect imports are intentional.** `import sift.extractors  # noqa: F401` in `pipeline.py` triggers `_register_builtins`. Don't refactor this without redesigning the registration mechanism.
- **No em dashes in user-facing strings** (CLI messages, README, docs). This is Carlos's personal style rule. Inside docstrings and code comments it doesn't matter.

## Sub-skills to use

- For multi-task feature work: `superpowers:subagent-driven-development` (one fresh subagent per task, with spec + quality reviews between). The v0.1.0 plan was executed this way.
- For any new code: `superpowers:test-driven-development`.
- Before claiming work is done: `superpowers:verification-before-completion` (run the actual command, paste the actual output).
- When dispatching fix/implementation agents: always include "run `uv run pytest -q` and fix any failures before returning" in the agent prompt. Agents that edit Python without running tests predictably break passing tests.
- When dispatching any agent that touches `sift-queue-watcher.py` or `~/Library/LaunchAgents/`: add explicit constraint "do NOT run `launchctl load/unload/reload` — apply the plist change and stop; flag it for user confirmation."

## How to develop

```bash
cd ~/Projects/sift
export PATH="$HOME/.local/bin:$PATH"   # if uv isn't on PATH
uv sync                                 # install deps + dev deps
uv run pytest -q                        # 102 tests, ~7s
uv run ruff check src tests             # lint
uv run sift --help                      # try the CLI
```

To run sift against a throwaway vault:

```bash
export OPENROUTER_API_KEY="$(~/Projects/secrets/bin/secret OPENROUTER_API_KEY)"
mkdir /tmp/sift-test
uv run sift init /tmp/sift-test
uv run sift add https://example.com/some-article --vault /tmp/sift-test --now
cat /tmp/sift-test/captures/*.md
```

To keep the config out of the vault root (e.g. for Obsidian users who want a clean sidebar):

```bash
uv run sift init /tmp/sift-test --config /tmp/sift-test/.config/sift.yaml
# Then for subsequent commands:
export SIFT_CONFIG=/tmp/sift-test/.config/sift.yaml
uv run sift add https://example.com/some-article --now
```

The OPENROUTER_API_KEY lives in the SOPS store (`~/Projects/secrets/`); the watcher reads it (and `TELEGRAM_BOT_TOKEN`) through `~/Projects/secrets/bin/secret`, with `~/.sift/.env` as an optional override. Never use the Keychain, never commit it.

## Pick up here — next priorities

In priority order:

1. **v0.3.0: Instagram + failure handling.**
   - Instagram (yt-dlp via cookie file).
   - Add a `--retry-failed` flag to `sift run` so terminal-failed items (including files in `raw/`) can be retried explicitly.
   - Per-stage status on `QueueEntry` so "extraction worked, enrichment didn't" is distinguishable.
   - Failure log surfaced via `sift status --verbose` with per-entry error_class.
2. **Quality items deferred from earlier reviews:**
   - `_clear_extractor_registry` fixture should be `clear → yield → clear` to handle test errors mid-execution.
   - Remove `OCRResult` from `enricher/base.py` or wire it through the vision path.
   - Remove `Config.private_caption_keywords` or implement the filter.
   - Add a `priority` field to `Extractor` ABC so registration order isn't positional.
3. **Bump `version.py` + `pyproject.toml` to 0.2.0, tag `v0.2.0`, and publish the GitHub release.** Not done as of 2026-11-05 (`git tag` shows v0.1.0, v0.1.1; `gh release list` is empty).

For the full long-form roadmap see `ROADMAP.md`. The vault plan (`personal/projects/vault-ingest-plan-v1`, no longer in the vault as of 2026-11-05) covered Phases 0–3 exhaustively; Phases 4–12 are still in the spec ([[personal/projects/vault-ingest-design]]) but haven't been turned into TDD task lists yet.

## Vault cross-references (Carlos only)

These paths only resolve in Carlos's private Obsidian vault. External contributors: ignore.

- `personal/projects/vault-ingest-design.md` — full spec (Phases 0–12).
- `personal/projects/vault-ingest-plan-v1.md` — executable plan for Phases 0–3 (delivered as v0.1.0). File not found in the vault as of 2026-11-05.
- `personal/projects/oss-clout-strategy.md` — selective OSS publishing strategy. sift is in the portfolio.
- `_internal/log.md` — append-only session log. Entry for the 2026-05-19 v0.1.0 build is filed under `## [2026-05-19] implementation`.
- `CLAUDE.md` (vault root) — OSS portfolio bullet under "Who is Carlos" references this repo.

## Resume protocol for new sessions

1. Read this file (CLAUDE.md). You're doing that now.
2. Run `git log --oneline -10` to see the last 10 commits.
3. Run `git tag` to see release tags.
4. Check `gh issue list --state open` for any new bug reports.
5. Run `uv run pytest -q` to confirm green starting state.
6. If picking up next-priority work from the list above, read the relevant source file plus any related test before changing anything.
7. Use `superpowers:subagent-driven-development` for any work that spans multiple files / requires a plan.

If there's a `handoff.md` at the repo root, read it. Otherwise the priority list in this file IS the handoff.

## Code intelligence: codanna

This repo has a local symbol index in `.codanna/` (gitignored). It is a **CLI, not an MCP server**:
run it from the repo root with Bash. There is no shared endpoint and no `repo_root` argument.
`code-review-graph` was retired on 2026-09-16: it reported 37 affected files for a script with zero
importers and returned 388 KB per call. codanna is correct, 118x smaller and 100x faster.

```
codanna mcp search_symbols query:<text> [kind:function] [limit:10]
codanna mcp find_symbol <ExactName>
codanna mcp find_callers <name>
codanna mcp get_calls <name>
codanna mcp analyze_impact <name>
codanna mcp semantic_search_with_context query:"<concept>" limit:5
codanna mcp get_index_info
```

Add `--watch` to reindex changed files before the query, `--json` for machine output.

Use it instead of a discovery grep for "where is X defined", "what calls X", "what breaks if I change
X". Grep stays right for line-level facts once you know the file, and for anything that is not a
symbol (config values, strings, comments). An empty `analyze_impact` result means nothing imports the
symbol: that is a finding, not a miss. Rebuild after a bulk refactor: `codanna index . --force`.
