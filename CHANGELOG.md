# Changelog

## 2026-06-01 (Phase 2 Refactoring Complete)

**Major Refactoring: Blueprint Architecture Implementation**

- Completed Phase 2 blueprint refactoring: Extracted all 41 API routes from monolithic `src/api.py` into 6 specialized blueprints
  - `src/blueprints/system.py` - 7 system/health routes (6 API + root)
  - `src/blueprints/batches.py` - 4 batch management routes
  - `src/blueprints/roster.py` - 11 roster management routes
  - `src/blueprints/photos.py` - 8 photo search/ingestion routes
  - `src/blueprints/detection.py` - 5 face detection/clustering routes
  - `src/blueprints/review.py` - 6 review/assignment routes
- Code reduction: `src/api.py` reduced from ~1100 lines to 257 lines (79% reduction)
- Extracted 5 shared utility functions to `src/utils.py` (path validation, parameter parsing)
- Fixed Flask application context handling for async job task functions
- All 272 tests passing with zero regressions
- Architecture improvements:
  - Blueprint handlers use `current_app.db` for clean dependency injection
  - Shared helpers properly scoped to prevent circular imports
  - Job task closures capture app/db references before async execution
  - Database delegation stubs for backward-compatible test migration
  - Commits: This session (Session 2 of Phase 2 refactoring)

## 2026-06-01 (continued — 2)

- Added a bright red "Danger zone" banner at the top of the Roster page with a "🗑 Delete All Data" CTA. Clicking opens a confirmation modal that lists exactly what will be deleted. Confirming calls the new `POST /api/data/reset` endpoint, which wipes all photos, OCR results, detected faces, player clusters, photo batches, rosters, game context, and processing jobs in a single transaction and returns per-table row counts. The roster list reloads (empty) after a successful reset.
  - Commit: 5d62444

## 2026-06-01 (continued)

- Added post-assignment face similarity scan on the Review tab. After tagging a cluster, the backend computes cosine similarity between the assigned cluster's face centroid and every remaining unidentified cluster. Clusters with ≥85% similarity are auto-tagged immediately (reflected live in the cluster list). Clusters with 70–85% similarity appear as interactive suggestion cards in the assignment drawer — each shows a face thumbnail, match %, and "Yes, tag" / "Skip" buttons. New backend helpers: `get_cluster_by_id`, `get_cluster_face_embeddings`, `get_unidentified_clusters_with_embeddings`; new endpoint `POST /api/players/<id>/match-similar`.
  - Commit: bef5791

## 2026-06-01

- Fixed "Local agent disconnected" error on fresh installs by moving the default API base URL from a hardcoded constant to `VITE_LOCAL_AGENT_URL` env var (set via `web/.env.local` for local dev); Railway deployments continue to use relative URLs. Also fixed a sidebar crash when photo batches have no `team_year` set. Added `*.pid` and `.env.local` to `.gitignore`.
  - Commit: 949f681
- Refactored Roster tab layout: replaced the large "Add Roster" placeholder card with a compact `+ Add Roster` CTA button in the page header; promoted Bulk Import to the primary left card slot; moved Add Player to the right slot alongside it; All Players table remains full-width at the bottom.
  - Commit: fd6ed6c

## 2026-05-29

- Added Railway hybrid hosting support with a cloud UI mode, protected local-agent settings, Railway Docker config, and local photo-root hardening.
  - Commit: e8ce6e5
- Added Review assignment XMP sidecar export for IPTC-compatible player, team, year, opponent, event, and keyword metadata.
  - Commit: aa1103b
- Filtered the Review workspace so face-cluster photos below 60% face match confidence are not shown.
  - Commit: c19ef9d
- Restored the Playful Geometric UI styling pipeline so Tailwind utilities compile into the app CSS again.
  - Commit: 0e34ef5
- Hid ambiguous duplicate confirmed cards in the Upload UI when the same photo and jersey are returned with multiple player names.
  - Commit: c2dd21b
- Added active game context and team uniform colors so duplicate jersey numbers across teams are not auto-confirmed without a matching uniform color.
  - Commit: eb7a12e
- Made Flask backend debug mode opt-in so `python -m src.api` starts cleanly on port `5001` in restricted local environments.
  - Commit: 46f3c9e
- Started the local-hardening refactor with a stable baseline tag, resumable local processing jobs, job-returning processing endpoints, and stricter API validation for numeric inputs and crawl paths.
  - Commits: 808927c, 81a5024, f41172b, ce78cea, ea5f2be, 5fcd314, b231117, 408d305
- Linked cleanup assignments to stable roster entry IDs so roster faces populate from identified photos even when uniform colors or jersey numbers change across photo sets.
  - Commit: 416dc85
- Added confirmation prompts before Search and Cleanup removals, and delete empty cleanup clusters after their last face is removed.
  - Commit: 7cb3d46
- Updated the Search tab to hide face boxes and confidence percentages, and added controls to remove face-tagged photos from the current player.
  - Commit: fcf5871
- Added backend roster importing for CSV, TXT, Markdown, XLSX, PDF, and roster URLs; updated the Roster tab import UI and added player face thumbnails to roster rows.
  - Commit: 3bd3bd4
