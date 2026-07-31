# PhotoTagger

A local photo discovery system for Ultimate Frisbee tournaments. Find all photos of a player by jersey number and roster data.

## Setup

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## Project Structure

**Core Backend**
- `src/db.py` — SQLite schema and queries
- `src/crawler.py` — Ingest photos from local directory
- `src/ocr.py` — Jersey number extraction
- `src/api.py` — Flask REST API
- `src/photo_metadata.py` — Read and return sparse photo metadata (image properties, game data, people)
- `src/iptc_writer.py` — Embed/remove player names in JPEG IPTC metadata via exiftool
- `src/metadata_sidecar.py` — XMP sidecar writes (non-destructive metadata)

**Frontend**
- `web/src/utils/labelPlacement.ts` — Adaptive label placement solver (full names, numbered pins, leader lines)
- `web/src/components/MetadataPanel.tsx` — Right-side metadata panel for lightbox (file, image, game, people sections)
- `web/src/components/PhotoLightbox.tsx` — Full-screen photo viewer with overlay and toggle controls

**Testing & Documentation**
- `tests/` — Pytest tests
- `docs/superpowers/specs/` — Feature specification documents
- `photos/` — Local test photos (user-created)
- `rosters/` — JSON team/roster data

## Running

```bash
# Test
pytest tests/ -v

# Crawl local photos
python -m src.crawler --photos ./photos

# Start API
python -m src.api
```

## Phase 1 Goals

- [x] Local photo crawling
- [x] Jersey OCR extraction
- [x] Roster lookup
- [x] REST API (search by jersey)
- [ ] Face embedding (Phase 2)
- [ ] Web UI (Phase 2)
