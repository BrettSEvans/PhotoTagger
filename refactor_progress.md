# Local Hardening Refactor Progress

## Overview

Goal: harden PhotoTagger as a local-first Flask/SQLite + React application by adding resumable local jobs, safer API validation, idempotent processing, frontend job polling, and stronger tests.

Stable baseline: `3ebc94b` tagged as `stable-before-local-hardening`.

## Current Status

Phase: Step 4 complete. Job persistence and status endpoint implemented.

## Completed

- [x] Step 1: Created annotated Git tag `stable-before-local-hardening` at `3ebc94b`.
- [x] Step 2: Created `refactor_progress.md` with the implementation checklist.
- [x] Step 3: Added backend TDD tests for job persistence and `GET /api/jobs/<id>`.
- [x] Step 4: Implemented `processing_jobs` table, DB helpers, and `GET /api/jobs/<id>`.

## In Progress

- [ ] Step 5: Convert long-running endpoints to return `job_id` for crawl, OCR, face detection, and clustering.

## Remaining

- [x] Step 3: Add backend TDD tests for job persistence and `GET /api/jobs/<id>`.
- [x] Step 4: Implement `processing_jobs` table and local job service.
- [ ] Step 5: Convert long-running endpoints to return `job_id` for crawl, OCR, face detection, and clustering.
- [ ] Step 6: Add path and parameter validation hardening.
- [ ] Step 7: Add face detection idempotency tests and implementation.
- [ ] Step 8: Update frontend API client for typed job polling and `VITE_API_BASE_URL`.
- [ ] Step 9: Update processing pages to poll job status.
- [ ] Step 10: Consolidate app shell so `main.tsx` mounts `App.tsx`.
- [ ] Step 11: Add frontend tests for job states and confirmation flows.
- [ ] Step 12: Add Playwright smoke test for core navigation/workflow.
- [ ] Step 13: Run full verification.
- [ ] Step 14: Update `CHANGELOG.md` with implementation commit ids.
- [ ] Step 15: Commit in small increments.

## Verification Log

- `./venv/bin/pytest tests/test_jobs.py -q` failed as expected before implementation: no jobs table, DB methods, or endpoint.
- `./venv/bin/pytest tests/test_jobs.py -q` passed after job persistence/status implementation.

## Known Issues

- `AGENTS.md` is untracked and intentionally excluded from commits.
- Backend process on port `5001` may need an external restart after backend changes.

## Commit Log

- `808927c` docs: track local hardening progress
