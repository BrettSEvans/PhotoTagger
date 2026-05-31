# PhotoTagger

A local photo discovery system for Ultimate Frisbee tournaments. Find all photos of a player by jersey number and roster data.

## Setup

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## Project Structure

- `src/db.py` — SQLite schema and queries
- `src/crawler.py` — Ingest photos from local directory
- `src/ocr.py` — Jersey number extraction
- `src/api.py` — Flask REST API
- `tests/` — Pytest tests
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
