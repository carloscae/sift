# sift

[![Build](https://github.com/carloscae/sift/actions/workflows/test.yml/badge.svg)](https://github.com/carloscae/sift/actions/workflows/test.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://python.org)

**The working bridge between social media and your second brain.**

Drop a link to a TikTok, an X thread, a YouTube short, an Instagram reel, a Reddit comment — or a voice note, screenshot, PDF — into your Obsidian vault. Get a clean, transcribed, summarized markdown note back. URL in, note out. Local-first, your own AI keys, opinionated.

We maintain extractors for the platforms that fight scraping the hardest, so you don't have to.

## Status

Pre-alpha. v0.1.1 ships:

- Extraction + transcription for YouTube and TikTok (audio via yt-dlp, transcribed locally via [whisper-svc](https://github.com/carloscae/whisper-svc))
- Extraction for generic article URLs (text)
- Summarisation + image captioning via OpenRouter (`/chat/completions`)

Roadmap → add X (video + text threads) and Instagram extractors, then a Telegram bridge.

## Quickstart

```bash
pip install sift
sift init ~/Documents/MyVault
export OPENROUTER_API_KEY=sk-or-...
sift add https://www.youtube.com/watch?v=jNQXAC9IVRw --vault ~/Documents/MyVault --now
```

Open `~/Documents/MyVault/captures/` — your note is there with title, summary, and full transcript.

**Note:** transcription requires [whisper-svc](https://github.com/carloscae/whisper-svc) running locally. Configure the endpoint in `vault-ingest.yaml` under `enricher.openrouter.whisper_svc_url`.

## Why not just use \<obvious alternative\>?

Most "save to second brain" tools either stop at clipping the URL (and leave you to actually read/watch the thing later) or work only for clean articles, breaking entirely on video platforms. Sift commits to maintaining the gnarly per-platform extraction layer — the part that breaks every few weeks when TikTok rotates its anti-scrape defenses. That maintenance commitment is the differentiator.

## Configuration

See `vault-ingest.yaml.example` for a full config. Defaults work for most users.

## Architecture + roadmap

- [ARCHITECTURE.md](ARCHITECTURE.md) — pipeline stages, registries, data contracts, how to add an extractor or enricher backend.
- [ROADMAP.md](ROADMAP.md) — what's coming next.
- [Issues](https://github.com/carloscae/sift/issues) — open work.

## License

MIT
