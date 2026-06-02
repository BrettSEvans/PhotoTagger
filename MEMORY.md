# PhotoTagger Project Memory & Documentation Index

This file indexes key project documentation and references.

## Phase 2 Completion (June 1, 2026)

- [PHASE2_WRAP_SUMMARY.md](PHASE2_WRAP_SUMMARY.md) — Complete Phase 2 refactoring summary (41/41 routes extracted, 272 tests passing)
- [PHASE2_CONTINUATION.md](PHASE2_CONTINUATION.md) — Detailed blueprint refactoring checklist used during Phase 2
- [CHANGELOG.md](CHANGELOG.md) — Project changelog with all refactoring milestones
- [TESTING.md](TESTING.md) — Test coverage analysis and recommendations for Phase 3+

## Project Setup

- [CLAUDE.md](CLAUDE.md) — PhotoTagger project instructions
- [requirements.txt](requirements.txt) — Python dependencies

## Current Architecture

**API Structure:** 6 blueprints + 1 utility module
- `src/blueprints/system.py` — System health, job status, data reset (7 routes)
- `src/blueprints/batches.py` — Photo batch management (4 routes)
- `src/blueprints/roster.py` — Roster CRUD and import (11 routes)
- `src/blueprints/photos.py` — Photo search, crawl, OCR (8 routes)
- `src/blueprints/detection.py` — Face detection, clustering (5 routes)
- `src/blueprints/review.py` — Assignment and review workflows (6 routes)
- `src/utils.py` — Shared helper functions

**Database:** SQLite with repository pattern (5 repositories: roster, photos, faces, clusters, review)

**Core Services:**
- Photo crawling and ingest (`src/crawler.py`)
- Jersey number OCR (`src/ocr.py`)
- Job queue and async task execution (`src/job_runner.py`)
- XMP metadata writing (`src/metadata_sidecar.py`)
- Roster import from files/URLs (`src/roster_import.py`)

## Key Metrics

- **Total Routes:** 41 (all extracted to blueprints)
- **Test Coverage:** 272/272 tests passing
- **Code Reduction:** `src/api.py` from ~1100 → 257 lines (79% reduction)
- **Blueprint Files:** 6 blueprints, all ≤250 lines
- **Regressions:** 0

## Next Steps (Phase 3+)

See [TESTING.md](TESTING.md) for comprehensive test coverage recommendations.

Phase 3 will focus on:
1. Face embedding generation and storage
2. Web UI implementation
3. Additional test coverage for concurrency, performance, and edge cases

---

**Last Updated:** June 1, 2026  
**Status:** Phase 2 Complete ✅
