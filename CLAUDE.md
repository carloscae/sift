# sift — Claude project memory

> Single source of truth for any Claude session working in this repo. Read this first.

## What sift is

`sift` is a Python CLI that turns URLs (and files) into clean markdown notes in an Obsidian-style vault. URL in, note out: extract → transcribe/summarise → write capture with structured frontmatter. The differentiator is the extractor layer: per-platform handlers that survive when TikTok/YouTube/X rotate their anti-scrape defences. That maintenance commitment is the moat.

Vault-agnostic by design. Carlos's personal Telegram setup is one of N optional ingresses, not a private adapter. The public product must be a strict superset of Carlos's use.

## Owner + contact

Carlos Vargas — `carlos@carloscae.com` — GitHub `carloscae`.

## Repo state (as of v0.1.0, 2026-05-19)

- **Tag:** `v0.1.0` pushed.
- **GitHub release:** **DRAFT** (intentionally). Do not publish until [issue #1](https://github.com/carloscae/sift/issues/1) is fixed (real audio transcription).
- **CI:** GitHub Actions green on every push to `main`. Trunk-based development; no feature branches yet.
- **Tests:** 51 passing, ruff clean. Coverage focuses on contracts, not mocks.
- **Phases shipped:** 0 through 3 of `personal/projects/vault-ingest-plan-v1.md` in Carlos's vault (private). The 4-phase plan delivered: scaffolding → core pipeline → extractor framework + 3 platforms → OpenRouter enricher + v0.1.0 tag.

## What works end-to-end today

```bash
sift init <vault>
sift add https://example.com/some-article --now --vault <vault>
# Result: captures/<date>-<slug>-<id>.md with title, summary, full article text.
```

- Article URLs through `GenericUrlExtractor` (httpx + readability-lxml) and `OpenRouterEnricher.summarise()`. Full pipeline.
- YouTube and TikTok URLs through yt-dlp: audio downloads land in `vault/raw/`, the note is written, but **the transcript is empty** until issue #1 is fixed.
- Image captioning via OpenRouter Gemini Flash (`caption()`). Wired but no CLI surface yet for "add this png".
- Queue persistence at `<vault>/.vault-ingest/queue.json` (pydantic-serialised). Failure path writes a stub capture with `subtype: url-failed`.
- `sift status` lists pending items. `sift run --upgrade-extractors` ships yt-dlp upgrade.

## What does NOT work

- **Audio transcription via OpenRouter.** OR does not currently expose an OpenAI-compatible `/audio/transcriptions` endpoint and has no Whisper models in its catalogue. Unit tests mock the call so they pass; production returns HTTP 500. This is the v0.1.1 blocker. See [issue #1](https://github.com/carloscae/sift/issues/1) and `ROADMAP.md`.
- Re-running a failed item silently re-enqueues it from `raw/` on the next `sift run` (no `failed` items in `seen_sources`). Latent until transcription actually works.
- No content filtering: `config.private_caption_keywords` is defined but never read.
- No retry / rate-limit handling. `httpx` is sync.
- `OCRResult` type is exported but never produced (the caption path uses `CaptionResult`).

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
   │ queue (.vault-ingest/queue.json)   │
   │   pending / processed / failed     │
   └────────────────────────────────────┘
                 │
                 v   ┌──────────────────────────┐
                 ├──>│ extractor.dispatch (URL) │ → yt-dlp / readability
                 │   └──────────────────────────┘
                 │
                 v
   ┌────────────────────────────────────┐
   │ enricher (OpenRouter)              │
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
- **Enricher registry** (`src/sift/enricher/registry.py`): `build_enricher(config)` reads the backend name from config and returns the right `Enricher` subclass. Today only `openrouter` works; `local` raises `NotImplementedError` (v1.1 target).

## File map

| Path | Purpose |
|---|---|
| `src/sift/cli.py` | Click CLI: `init`, `add`, `run`, `status`. `--vault` option resolves from arg, env (`SIFT_VAULT`), or cwd. |
| `src/sift/config.py` | Pydantic `Config` model loaded from `vault-ingest.yaml`. `OpenRouterConfig` + `EnricherConfig` nested. |
| `src/sift/classify.py` | `classify_url(url)` and `classify_path(path)` returning typed `Item`. Hostname → platform mapping. |
| `src/sift/queue.py` | JSON-backed queue. SHA256-prefix item IDs. `scan_raw` is batched (one write per call). |
| `src/sift/writer.py` | Markdown emission. python-slugify for non-Latin title safety. `ingested-via: sift@{__version__}`. |
| `src/sift/pipeline.py` | Orchestrator. URL → dispatch_extract → enrich → write. File → enrich-file → write. Cleans work_dir in a `finally`. |
| `src/sift/extractors/base.py` | `Extractor` ABC, `ExtractResult` / `ExtractFailure`, `_REGISTRY` + helpers. |
| `src/sift/extractors/dispatch.py` | `dispatch_extract(url, work_dir)` parses hostname, routes to extractor, wraps exceptions in `ExtractFailure`. |
| `src/sift/extractors/{youtube,tiktok,generic_url}.py` | Three built-in extractors. |
| `src/sift/extractors/__init__.py` | Side-effect: `_register_builtins()` registers TikTok → YouTube → Generic (order matters). |
| `src/sift/enricher/base.py` | `Enricher` ABC + `TranscriptResult` / `CaptionResult` / `OCRResult` / `SummaryResult`. |
| `src/sift/enricher/openrouter.py` | OR-backed enricher. `_raise_with_body` surfaces response body in HTTPStatusError. |
| `src/sift/enricher/registry.py` | `build_enricher(config)` factory. Raises `RuntimeError` if API key env var unset. |
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

## How to develop

```bash
cd ~/Projects/sift
export PATH="$HOME/.local/bin:$PATH"   # if uv isn't on PATH
uv sync                                 # install deps + dev deps
uv run pytest -q                        # 51 tests, < 1s
uv run ruff check src tests             # lint
uv run sift --help                      # try the CLI
```

To run sift against a throwaway vault:

```bash
export OPENROUTER_API_KEY="$(security find-generic-password -a "$USER" -s OPENROUTER_API_KEY -w)"
mkdir /tmp/sift-test
uv run sift init /tmp/sift-test
uv run sift add https://example.com/some-article --vault /tmp/sift-test --now
cat /tmp/sift-test/captures/*.md
```

The OPENROUTER_API_KEY is in Carlos's macOS keychain on the laptop (saved 2026-05-19, source: `~/Projects/AkiraProject/.env`). Never commit it.

## Pick up here — next priorities

In priority order:

1. **Fix transcription (issue #1, v0.1.1).** Switch `OpenRouterEnricher.transcribe()` from the non-existent `/audio/transcriptions` to a `/chat/completions` audio-input flow. Models to try: `openai/gpt-audio-mini`, `google/gemini-2.5-flash` with audio attachment, `google/gemini-2.5-pro`. Update `_STT_COST_PER_SEC` table. Keep the `transcribe()` signature stable.
2. **Re-publish the GitHub release.** Once transcription works, update the draft release at https://github.com/carloscae/sift/releases, tag v0.1.1, and publish.
3. **README + Quickstart update.** Drop the issue-#1 warning, restore a YouTube quickstart that actually works.
4. **Quality items deferred from v0.1.0 reviews:**
   - `scan_raw` should include `failed` items in `seen_sources` so re-dropped files don't silently retry. Add a `--retry-failed` flag to `sift run` for explicit retry. (Phase 2 quality review item.)
   - `_subtype_from_media` accepts `platform` but never uses it. Either use it (per-platform subtype routing) or drop the parameter. (Phase 2 review item.)
   - `_clear_extractor_registry` fixture should be `clear → yield → clear` to handle test errors mid-execution. (Phase 2 review item.)
   - Remove `OCRResult` from `enricher/base.py` or wire it through the vision path. (Final review item.)
   - Remove `Config.private_caption_keywords` or implement the filter. (Final review item.)
   - Add a `priority` field to `Extractor` ABC so registration order isn't positional. (Phase 4 prep.)
5. **Phase 4 (v0.2.0): more extractors + failure handling.** Instagram, X (video + text via fxtwitter), Reddit, BlueSky. Failure log + retry-on-next-run + T2 fallback UX.

For the full long-form roadmap see `ROADMAP.md`. The vault plan ([[personal/projects/vault-ingest-plan-v1]] in Carlos's Obsidian vault) covered Phases 0–3 exhaustively; Phases 4–12 are still in the spec ([[personal/projects/vault-ingest-design]]) but haven't been turned into TDD task lists yet.

## Vault cross-references (Carlos only)

These paths only resolve in Carlos's private Obsidian vault. External contributors: ignore.

- `personal/projects/vault-ingest-design.md` — full spec (Phases 0–12).
- `personal/projects/vault-ingest-plan-v1.md` — executable plan for Phases 0–3 (delivered as v0.1.0).
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
