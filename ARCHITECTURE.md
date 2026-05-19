# Architecture

`sift` is a four-stage pipeline with two pluggable registries. Each stage has one responsibility and a typed contract with the next.

## Pipeline

```
classify  →  queue  →  extract  →  enrich  →  write
```

1. **Classify** (`src/sift/classify.py`). Detect what kind of thing came in. URL? Audio file? Image? PDF? URLs get a `platform` label from hostname (tiktok, youtube, instagram, x, reddit, bluesky, generic). Files get a `kind` from extension. Returns an `Item`.

2. **Queue** (`src/sift/queue.py`). Persist intent. Adding a URL or file produces an entry with a stable SHA256-prefix ID. State lives at `<vault>/.vault-ingest/queue.json` and has three buckets: `pending`, `processed`, `failed`. The queue also scans `<vault>/raw/` for files dropped externally (shortcuts, Telegram bridge, manual drag-and-drop).

3. **Extract** (`src/sift/extractors/`). For URL items, route to the right extractor by hostname and produce an `ExtractResult` (downloaded media path + metadata) or an `ExtractFailure` (typed error class + diagnostic text + suggested user fallback). Three built-ins ship in v0.1.0: YouTube (yt-dlp), TikTok (yt-dlp), and a generic article extractor (httpx + readability-lxml). File items skip extraction.

4. **Enrich** (`src/sift/enricher/`). Audio gets transcribed. Text gets summarised. Images get captioned + OCR'd. All three operations return a typed result with `cost_usd` stamped, so the writer can record what each capture cost. Backend abstraction lets v1.1 swap in a local model that runs fully offline.

5. **Write** (`src/sift/writer.py`). Emit `captures/{YYYY-MM-DD}-{slug}-{item_id[:6]}.md` with YAML frontmatter and a markdown body. Frontmatter captures source, platform, ingestion version (`sift@{__version__}`), enrichment metadata, and cost.

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
    register_extractor(GenericUrlExtractor()) # catch-all LAST

_register_builtins()
```

**Order matters.** `GenericUrlExtractor.can_handle()` returns `True` for everything; it must be registered last or it will swallow every URL.

`pipeline.py` triggers registration via a side-effect import:

```python
import sift.extractors  # noqa: F401 — registers built-in extractors
```

Test isolation: `tests/conftest.py` has an autouse fixture that calls `clear_registry()` before each test, preventing module-level state from leaking.

### Enricher registry

Simpler: a single factory function.

```python
# src/sift/enricher/registry.py
def build_enricher(config: Config) -> Enricher:
    backend = config.enricher.backend
    if backend == "openrouter":
        return OpenRouterEnricher(...)
    if backend == "local":
        raise NotImplementedError("v1.1")
    raise ValueError(...)
```

The pipeline calls `build_enricher(config)` once per `process_pending` run and reuses the instance.

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
    id: str                   # sha256(source)[:12]
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
    metadata: dict
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

## Filesystem layout (user-side)

For a vault at `~/MyVault`:

```
~/MyVault/
├── vault-ingest.yaml          # config (written by `sift init`)
├── raw/                       # downloaded media + user-dropped files
│   └── <item-id>-<filename>.mp3
├── captures/                  # produced markdown notes
│   └── 2026-05-19-some-title-abc123.md
└── .vault-ingest/             # internal state (gitignored by users)
    ├── queue.json             # pending/processed/failed lookup
    └── work/                  # scratch space, cleaned after each item
```

`raw/` files have a 7-day TTL (configurable via `raw_ttl_days`). Capture notes never expire; the user owns them.

## Failure path

```
URL → dispatch_extract → ExtractFailure
                              ↓
                  _write_failure_stub
                              ↓
        captures/<date>-extraction-failed-<id>.md
        (subtype: url-failed, status: pending-enrichment)
```

The capture file always exists. The user always sees what was attempted. Re-runs can pick up the failed item later when the underlying platform or extractor is fixed.

## Cost tracking

Every enricher call stamps a `cost_usd` on its result. The pipeline sums these across the operations it ran (`transcribe` + `summarise` for a video; just `summarise` for an article). The total lands in frontmatter as `enrich-cost-usd: 0.0011`. Constants for per-token / per-second pricing live in `src/sift/enricher/openrouter.py` (`_STT_COST_PER_SEC` + inline summarise/caption coefficients). These will drift as OpenRouter changes pricing; refresh from OR's docs and bump them in a v0.X commit.

A future `monthly_budget_usd` knob in config (already in the schema, not yet enforced) will let users cap spending.

## Adding a new extractor

1. Create `src/sift/extractors/<platform>.py` with a class inheriting `Extractor`.
2. Implement `can_handle(hostname)` and `extract(url, work_dir) -> ExtractResult`.
3. Raise on failure; the dispatcher wraps exceptions in `ExtractFailure`.
4. Register it in `src/sift/extractors/__init__.py::_register_builtins`, **before** `GenericUrlExtractor`.
5. Write tests in `tests/extractors/test_<platform>.py`. Mock the network layer (httpx via respx; yt-dlp via `unittest.mock.patch("sift.extractors.<platform>.YoutubeDL")`).
6. Update `src/sift/classify.py::_PLATFORM_HOSTS` if the platform should produce a typed `Item.platform` label.

## Adding a new enricher backend

1. Create `src/sift/enricher/<backend>.py` with a class inheriting `Enricher`.
2. Implement `transcribe`, `caption`, `summarise`. Return the corresponding `Result` types with `cost_usd` populated.
3. Add a branch in `src/sift/enricher/registry.py::build_enricher`.
4. Extend `sift/config.py` with any backend-specific config (nested under `EnricherConfig`).
5. Tests in `tests/enricher/test_<backend>.py`.

The local-model backend (v1.1) will live at `src/sift/enricher/local.py`.

## Known design trade-offs (worth knowing if you're refactoring)

- **The extractor registry is a module-level global.** Could be a `Pipeline.with_extractors(...)` builder; intentionally avoided for v0.1.0 because the global keeps the API surface smaller. If multi-tenancy ever matters, replace it.
- **Side-effect imports trigger registration.** Acceptable but unusual. Test isolation works because of the autouse `clear_registry` fixture. Subtle for new contributors.
- **`httpx.Client` is synchronous.** Fine for a personal CLI; will need `AsyncClient` once an HTTP-endpoint mode lands (Phase 7).
- **Queue has no per-step status.** A failure currently marks the whole item failed, losing the partial success of "extraction worked, enrichment didn't." For retry sanity in Phase 6+, the `QueueEntry` will probably grow a `stage_status` field.
- **No backpressure / batching.** `process_pending` processes everything in the pending bucket sequentially. A 200-item backlog will hammer OpenRouter. v0.4.0 + will add a rate-limit + budget guard.
