# Local Hardening Refactor Progress

## Overview

Goal: harden PhotoTagger as a local-first Flask/SQLite + React application by adding resumable local jobs, safer API validation, idempotent processing, frontend job polling, and stronger tests.

Stable baseline: `3ebc94b` tagged as `stable-before-local-hardening`.

## Current Status

Phase: Step 12 added with a local runtime blocker. Playwright smoke coverage is in place, but Chromium launch is blocked by this desktop sandbox.

## Completed

- [x] Step 1: Created annotated Git tag `stable-before-local-hardening` at `3ebc94b`.
- [x] Step 2: Created `refactor_progress.md` with the implementation checklist.
- [x] Step 3: Added backend TDD tests for job persistence and `GET /api/jobs/<id>`.
- [x] Step 4: Implemented `processing_jobs` table, DB helpers, and `GET /api/jobs/<id>`.
- [x] Step 15: Committed job persistence checkpoint.
- [x] Step 5: Converted crawl, OCR, face detection, and clustering endpoints to return `job_id`.
- [x] Step 15: Committed job endpoint checkpoint.
- [x] Step 6: Added path and parameter validation hardening.
- [x] Step 15: Committed validation hardening checkpoint.
- [x] Step 7: Added face detection idempotency tests and implementation.
- [x] Step 15: Committed face idempotency checkpoint.
- [x] Step 8: Updated frontend API client for typed job polling and `VITE_API_BASE_URL`.
- [x] Step 9: Updated processing pages to poll job status.
- [x] Step 10: Consolidated app shell so `main.tsx` mounts `App.tsx`.
- [x] Step 15: Committed frontend job polling checkpoint.
- [x] Step 11: Added frontend tests for job states and confirmation flows.
- [x] Step 15: Committed frontend behavior test checkpoint.
- [x] Step 12: Added Playwright smoke test for core navigation/workflow.

## In Progress

- [ ] Step 13: Run full verification.

## Remaining

- [x] Step 3: Add backend TDD tests for job persistence and `GET /api/jobs/<id>`.
- [x] Step 4: Implement `processing_jobs` table and local job service.
- [x] Step 5: Convert long-running endpoints to return `job_id` for crawl, OCR, face detection, and clustering.
- [x] Step 6: Add path and parameter validation hardening.
- [x] Step 7: Add face detection idempotency tests and implementation.
- [x] Step 8: Update frontend API client for typed job polling and `VITE_API_BASE_URL`.
- [x] Step 9: Update processing pages to poll job status.
- [x] Step 10: Consolidate app shell so `main.tsx` mounts `App.tsx`.
- [x] Step 11: Add frontend tests for job states and confirmation flows.
- [x] Step 12: Add Playwright smoke test for core navigation/workflow.
- [ ] Step 13: Run full verification.
- [ ] Step 14: Update `CHANGELOG.md` with implementation commit ids.
- [ ] Step 15: Commit in small increments.

## Verification Log

- `./venv/bin/pytest tests/test_jobs.py -q` failed as expected before implementation: no jobs table, DB methods, or endpoint.
- `./venv/bin/pytest tests/test_jobs.py -q` passed after job persistence/status implementation.
- `./venv/bin/pytest tests/test_jobs.py -q` failed as expected before endpoint conversion: long-running endpoints still return synchronous `200` responses.
- `./venv/bin/pytest tests/test_jobs.py tests/test_api.py tests/test_api_phase2.py -q` passed after endpoint conversion and API test updates.
- `./venv/bin/pytest tests/test_validation.py -q` failed as expected before validation implementation: invalid numeric values raised server errors and unsafe crawl paths were accepted.
- `./venv/bin/pytest tests/test_validation.py -q` passed after validation implementation.
- `./venv/bin/pytest tests/test_validation.py tests/test_jobs.py tests/test_api.py tests/test_api_phase2.py -q` passed after Step 6 validation hardening.
- `./venv/bin/pytest tests/test_jobs.py::test_detect_faces_endpoint_is_idempotent -q` failed as expected before implementation: rerunning face detection duplicated stored faces.
- `./venv/bin/pytest tests/test_jobs.py::test_detect_faces_endpoint_is_idempotent -q` passed after skipping photos with existing face detections.
- `./venv/bin/pytest tests/test_jobs.py tests/test_db_phase2.py tests/test_api_phase2.py -q` passed after Step 7 idempotency implementation.
- `npm run lint` failed before all processing pages were updated: several components still expected synchronous processing results.
- `npm run lint` passed after typed job polling updates.
- `npm run build` passed after frontend job polling and app shell consolidation.
- `npm run test:frontend` passed after adding frontend behavior checks for polling and confirmation flows.
- `npm run build && PLAYWRIGHT_BROWSERS_PATH=0 npm run test:e2e` built successfully, then Playwright failed to launch Chromium in the desktop sandbox with `MachPortRendezvousServer ... Permission denied`.

## Known Issues

- `AGENTS.md` is untracked and intentionally excluded from commits.
- Backend process on port `5001` may need an external restart after backend changes.
- Playwright Chromium launch is blocked in this desktop sandbox by macOS Mach port permissions; run `PLAYWRIGHT_BROWSERS_PATH=0 npm run test:e2e` from a normal local shell or CI.

## Commit Log

- `808927c` docs: track local hardening progress
- `81a5024` feat: add local processing jobs
- `f41172b` feat: run processing endpoints as jobs
- `ce78cea` feat: harden api validation
- `3a2bc29` docs: record local hardening checkpoint
- `ea5f2be` feat: make face detection idempotent
- `01dd9e4` docs: record face idempotency checkpoint
- `5fcd314` feat: poll processing jobs in frontend
- `10a7c67` docs: record frontend jobs checkpoint
- `b231117` test: add frontend behavior checks
- `cf39cc3` docs: record frontend test checkpoint
- `408d305` test: add playwright smoke coverage
