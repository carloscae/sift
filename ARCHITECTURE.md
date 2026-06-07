# Architecture

`sift` is a four-stage pipeline with two pluggable registries. Each stage has one responsibility and a typed contract with the next.

## Data flow

```
Telegram bot → ~/.sift-queue.d/*.json → sift-queue-watcher.py (in-process)
                                              ↓
                                       SQLite queue (queue.db)
                                              ↓
                               pipeline.py (process_pending)
                                    ↙         ↘
                             extract         enrich
                                    ↘         ↙
                                      write
                                        ↓
                                  captures/*.md
```

For direct CLI use: `sift add <url> --now` skips the file-drop step and runs the pipeline in-process.

## Pipeline

```
classify  →  queue  →  extract  →  enrich  →  write
```

1. **Classify** (`src/sift/classify.py`). Detect what kind of thing came in. URL? Audio file? Image? PDF? URLs get a `platform` label from hostname (tiktok, youtube, instagram, x, reddit, bluesky, generic). Files get a `kind` from extension. Returns an `Item`.

2. **Queue** (`src/sift/queue.py`). Persist intent in SQLite (WAL mode). Adding a URL produces an entry with a stable SHA256-prefix ID derived from the *normalized* URL (tracking params stripped, youtu.be resolved, x.com canonicalized to twitter.com). State lives at `<state_dir>/queue.db`. Three statuses: `pending`, `processed`, `failed`. Auto-prunes processed/failed rows older than 30 days on every instantiation. The queue also scans `<vault>/raw/` for files dropped externally (shortcuts, Telegram bridge, manual drag-and-drop).

3. **Extract** (`src/sift/extractors/`). For URL items, route to the right extractor by hostname and produce an `ExtractResult` (downloaded media path + metadata) or an `ExtractFailure` (typed error class + diagnostic text + suggested user fallback). Four built-ins ship: YouTube (yt-dlp), TikTok (yt-dlp), Twitter/X, and a generic article extractor (httpx + readability-lxml). File items skip extraction.

4. **Enrich** (`src/sift/enricher/`). Audio gets transcribed via whisper-svc. Text gets summarised. Images get captioned + OCR'd. All operations return a typed result with `cost_usd` stamped, so the writer can record what each capture cost. Monthly budget is enforced before enrichment starts (checked against `~/.sift/budget.json`). If the budget is exceeded, the enricher is not instantiated and items are written without enrichment.

5. **Write** (`src/sift/writer.py`). Emit `captures/{YYYY-MM-DD}-{slug}-{item_id[:6]}.md` with YAML frontmatter and a markdown body. Frontmatter captures source, platform, ingestion version (`sift@{__version__}`), enrichment metadata, cost, and the backend that produced the enrichment (`enriched_by: openrouter` or `enriched_by: claude-cli`).

The orchestrator (`src/sift/pipeline.py`) ties the stages together. It catches exceptions per-item and routes them to `mark_failed`, so one bad URL doesn't sink the batch.

## Registries

Two registries make sift extensible:

### Extractor registry

```python
# src/sift/extractors/base.py
_REGISTRY: list[Extractor] = []

def register_extractor(extractor: Extractor) -> None: ...
def get_extractor(hostname: str) -> Extractor | None: ...
def clear_registry() -> None: ...   # test isolation
```

Built-ins register at package import time:

```python
# src/sift/extractors/__init__.py
def _register_builtins() -> None:
    register_extractor(TikTokExtractor())     # specific first
    register_extractor(YouTubeExtractor())
    register_extractor(TwitterExtractor())    # x.com, twitter.com, t.co
    register_extractor(GenericUrlExtractor()) # catch-all LAST

_register_builtins()
```

**Order matters.** `GenericUrlExtractor.can_handle()` returns `True` for everything; it must be registered last or it will swallow every URL.

`pipeline.py` triggers registration via a side-effect import:

```python
import sift.extractors  # noqa: F401 — registers built-in extractors
```

Test isolation: `tests/conftest.py` has an autouse fixture that calls `clear_registry()` before each test, preventing module-level state from leaking.

### Extractor class hierarchy

```
Extractor (ABC)
├── YtDlpAudioExtractor   src/sift/extractors/ytdlp_base.py
│   ├── YouTubeExtractor  src/sift/extractors/youtube.py
│   └── TikTokExtractor   src/sift/extractors/tiktok.py
├── TwitterExtractor      src/sift/extractors/twitter.py  (independent)
└── GenericUrlExtractor   src/sift/extractors/generic_url.py  (independent)
```

`YtDlpAudioExtractor` is the shared base for platforms that yield audio via yt-dlp. It owns the yt-dlp options, the ffmpeg post-processor config, and the `can_handle` pattern (`self._HOSTS` set). Subclasses only need to declare `platform` and `_HOSTS`.

`TwitterExtractor` is independent because its extraction strategy is more complex: fxtwitter API first (fast, no auth), yt-dlp only for video tweets, Playwright for `x.com/i/article/` URLs. Playwright is a soft dependency — a clear `RuntimeError` is raised if it's not installed.

### Enricher registry

Simpler: a single factory function.

```python
# src/sift/enricher/registry.py
def build_enricher(config: Config) -> Enricher:
    backend = config.enricher.backend  # Literal["openrouter", "claude-cli", "local"]
    if backend == "openrouter":
        return OpenRouterEnricher(...)
    if backend == "claude-cli":
        return ClaudeCliEnricher(...)   # summarise via `claude -p`; transcribe via whisper-svc
    if backend == "local":
        raise NotImplementedError("v1.1")
    raise ValueError(...)
```

The `backend` field is `Literal["openrouter", "claude-cli", "local"]` — typos are caught at config load time by Pydantic. The pipeline calls `build_enricher(config)` once per `process_pending` run and reuses the instance.

## Data contracts

All data flowing between stages is typed via Pydantic v2 models.

```python
# Classify output
class Item(BaseModel):
    kind: ItemKind            # StrEnum: URL/AUDIO/VIDEO/IMAGE/DOCUMENT/TEXT
    source: str               # URL string or file path string
    platform: str | None      # for URL items
    local_path: Path | None   # for file items

# Queue persistence
class QueueEntry(BaseModel):
    id: str                   # sha256(normalized_source)[:12]
    source: str
    kind: str
    platform: str | None
    local_path: str | None
    enqueued_at: str          # ISO 8601

# Extract output
class ExtractResult(BaseModel):
    platform: str
    media_type: Literal["audio", "video", "image", "text", "mixed"]
    media_path: Path | None   # downloaded media, moves to vault/raw/
    text_content: str | None  # for article extractors
    title: str
    metadata: dict            # may include extraction_warning for degraded results
    cost_usd: float

class ExtractFailure(BaseModel):
    url: str
    platform: str
    error_class: Literal["anti-scrape", "auth-wall", "rate-limited",
                         "site-changed", "network", "unknown"]
    error_detail: str
    suggested_t2: str | None  # user-facing fallback hint

# Enrich outputs (all carry cost)
class TranscriptResult(BaseModel): text, model, cost_usd, duration_sec
class CaptionResult(BaseModel):    caption, ocr_text, model, cost_usd, tags
class SummaryResult(BaseModel):    title, summary, tags, model, cost_usd
class OCRResult(BaseModel):        text, model, cost_usd  # reserved, unused in v0.1.0

# Write input
class CaptureData(BaseModel):
    item_id, source, platform, subtype, title, summary,
    transcript_or_ocr, tags, enriched_by, cost_usd, models, raw_file
```

## Persistence layout

```
~/.sift/
├── budget.json       # monthly enrichment spend, keyed by YYYY-MM
├── last-run.json     # written by sift-queue-watcher after each drain
│                     # {timestamp, processed, failed, dead_lettered, duration_sec}
└── .env              # optional; injected into watcher process env

~/.sift-queue.d/
├── <uuid>.json       # pending items written by Telegram bot
└── .dead/
    └── <uuid>.json   # dead-lettered after MAX_RETRIES=3 failures

~/Library/Logs/sift/
└── watcher.log       # LaunchAgent stdout/stderr

<vault>/
├── vault-ingest.yaml
├── raw/              # downloaded media (7-day TTL, configurable)
│   └── <item-id>-<filename>.mp3
├── captures/         # produced markdown notes
│   └── 2026-05-19-some-title-abc123.md
└── .vault-ingest/
    ├── queue.db      # SQLite WAL; pending/processed/failed rows
    └── work/         # scratch space, cleaned after each item
```

For iCloud vaults: `raw_dir` and `state_dir` accept absolute paths so scratch files can stay on local disk outside iCloud Drive.

## Config file resolution

sift looks for the config file in this order:

1. `--config <path>` CLI flag
2. `$SIFT_CONFIG` environment variable
3. `<vault>/vault-ingest.yaml` where `<vault>` comes from `--vault`, `$SIFT_VAULT`, or the current working directory.

## Budget guard

When `monthly_budget_usd` is set in config, `process_pending` reads `~/.sift/budget.json` before building the enricher. If the current month's spend meets or exceeds the cap, the enricher is not instantiated and all items in the batch are written without enrichment (note is saved, but no transcript or summary). After each item, spend is accumulated back to `budget.json`.

The budget only applies to API-cost backends (`openrouter`). `claude-cli` and future `local` backends always report `cost_usd=0.0`.

## Failure path

```
URL → dispatch_extract → ExtractFailure
                              ↓
                  queue.mark_failed(item_id)
                              ↓
               (no capture file written for extraction failures)
```

For watcher-driven runs: after `MAX_RETRIES=3` failures on the same `.sift-queue.d/*.json` file, the watcher moves it to `~/.sift-queue.d/.dead/` and sends a Telegram notification. The SQLite queue entry remains `failed` and can be retried via `sift add <url>`.

## Cost tracking

Every enricher call stamps a `cost_usd` on its result. The pipeline sums these and writes the total to frontmatter as `enrich-cost-usd: 0.0001`. Spend is also accumulated to `~/.sift/budget.json` for the monthly cap.

- **whisper-svc transcription:** always `0.0` (local model, no API cost).
- **claude-cli summarisation:** always `0.0` (uses Claude subscription).
- **openrouter summarisation/caption:** calculated from token usage at model rates. Constants live in `src/sift/enricher/openrouter.py`.

The `enriched_by` field in capture frontmatter records the actual backend (`openrouter` or `claude-cli`), not a hardcoded string.

## Adding a new extractor

1. Create `src/sift/extractors/<platform>.py` with a class inheriting `Extractor` (or `YtDlpAudioExtractor` if it's an audio platform served by yt-dlp).
2. Implement `can_handle(hostname)` and `extract(url, work_dir) -> ExtractResult`.
3. Raise on failure; the dispatcher wraps exceptions in `ExtractFailure`.
4. Register it in `src/sift/extractors/__init__.py::_register_builtins`, **before** `GenericUrlExtractor`.
5. Write tests in `tests/extractors/test_<platform>.py`. Mock the network layer (httpx via respx; yt-dlp via `unittest.mock.patch("sift.extractors.<platform>.YoutubeDL")`).
6. Update `src/sift/classify.py::_PLATFORM_HOSTS` if the platform should produce a typed `Item.platform` label.

## Adding a new enricher backend

1. Create `src/sift/enricher/<backend>.py` with a class inheriting `Enricher`.
2. Implement `transcribe`, `caption`, `summarise`. Return the corresponding `Result` types with `cost_usd` populated.
3. Add a branch in `src/sift/enricher/registry.py::build_enricher`.
4. Add the backend name to the `Literal` type in `EnricherConfig.backend` in `src/sift/config.py`.
5. Extend `EnricherConfig` with any backend-specific config (nested model).
6. Tests in `tests/enricher/test_<backend>.py`.

## Known design trade-offs

- **The extractor registry is a module-level global.** Could be a `Pipeline.with_extractors(...)` builder; intentionally avoided for v0.1.0 because the global keeps the API surface smaller.
- **Side-effect imports trigger registration.** Acceptable but unusual. Test isolation works because of the autouse `clear_registry` fixture.
- **`httpx.Client` is synchronous.** Fine for a personal CLI; will need `AsyncClient` once an HTTP-endpoint mode lands.
- **Queue has no per-step status.** A failure marks the whole item failed, losing the partial success of "extraction worked, enrichment didn't." A `stage_status` field on `QueueEntry` is planned for v0.3.0.
- **No backpressure / batching.** `process_pending` processes everything in the pending bucket sequentially.
- **Playwright is a soft dependency.** Only required for `x.com/i/article/` URLs. Missing Playwright produces a clear error message rather than an import error at startup.
