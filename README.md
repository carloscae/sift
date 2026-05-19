# sift

[![Build](https://github.com/carloscae/sift/actions/workflows/test.yml/badge.svg)](https://github.com/carloscae/sift/actions/workflows/test.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://python.org)

**The working bridge between social media and your second brain.**

Drop a link to a TikTok, an X thread, a YouTube short, an Instagram reel, a Reddit comment — or a voice note, screenshot, PDF — into your Obsidian vault. Get a clean, transcribed, summarized markdown note back. URL in, note out. Local-first, your own AI keys, opinionated.

We maintain extractors for the platforms that fight scraping the hardest, so you don't have to.

## Status

Pre-alpha. v0.1.0 ships:

- Extraction for YouTube, TikTok (audio), and generic article URLs (text)
- Summarisation + image captioning via OpenRouter (`/chat/completions`)
- ⚠️ Transcription is **not yet working** in v0.1.0 — OpenRouter does not currently expose an OpenAI-compatible Whisper endpoint. See [issue #1](https://github.com/carloscae/sift/issues/1). Article URLs still produce full summaries; video URLs land with extracted audio in `raw/` but no transcript.

Roadmap → fix transcription (v0.1.1), add Instagram, X (video + text threads), Reddit, BlueSky extractors, plus a local-model backend that runs fully offline.

## Quickstart

```bash
pip install sift
sift init ~/Documents/MyVault
export OPENROUTER_API_KEY=sk-or-...
# Article URLs work end-to-end today:
sift add https://example.com/some-article --vault ~/Documents/MyVault --now
```

Open `~/Documents/MyVault/captures/` — your note is there with title, summary, and full extracted text.

## Why not just use \<obvious alternative\>?

Most "save to second brain" tools either stop at clipping the URL (and leave you to actually read/watch the thing later) or work only for clean articles, breaking entirely on video platforms. Sift commits to maintaining the gnarly per-platform extraction layer — the part that breaks every few weeks when TikTok rotates its anti-scrape defenses. That maintenance commitment is the differentiator.

## Configuration

See `vault-ingest.yaml.example` for a full config. Defaults work for most users.

## License

MIT
