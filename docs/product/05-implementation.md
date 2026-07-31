# Implementation — PhotoTagger: Photo Metadata & Adaptive Labeling

> What was actually built for features #1–#4, against
> `docs/product/04-architecture.md` and the source spec
> `docs/superpowers/specs/2026-07-30-photo-metadata-design.md`.
> Read by QA next. Date: 2026-07-31

## What was built

**Backend (Python/Flask):**
- `src/iptc_writer.py` (new) — `write_iptc()`, `backup_directory()`, `is_backup_ready()`, `IptcWriteError`. Wraps `exiftool` via subprocess, argument-list only (no shell). Serialized by a process-wide lock (critic finding, §7 below).
- `src/photo_metadata.py` (new) — `read(db, photo_id)`, the sparse metadata projection.
- `src/repositories/face.py` — added `get_faces_with_player_info_by_photo()`.
- `src/db.py` — added `get_player_names_and_paths_for_faces()` (resolves player names before a deassign clears the cluster link).
- `src/blueprints/photos.py` — new `GET /api/photos/<id>/metadata`.
- `src/blueprints/review.py` — `assign_cluster` and `deassign_faces` now call the new `_embed_names()` helper unconditionally (no `write_metadata` flag); gated on `is_backup_ready()` and `is_allowed_photo_path()`; failures logged, never propagated.
- `src/api.py` — `write_assignment_metadata()` deleted (both the module-level definition and a dead duplicate closure inside `create_app()` that was never called). One-time `uploads_backup/` copy now dispatched as an async job at startup via the existing `LocalJobRunner`.
- `src/blueprints/batches.py` — unchanged; reused as-is for the Game section (see Deviations).

**Frontend (React/TypeScript):**
- `web/src/utils/labelPlacement.ts` (new) — pure adaptive placement solver.
- `web/src/components/MetadataPanel.tsx` (new) — right-side panel: toggles, file/image/library/jersey/game/people sections, inline `AssignPlayerPanel` reuse for the "Assign" action.
- `web/src/components/PhotoLightbox.tsx` (rewritten) — two-column layout, calls the solver, renders labels/pins/leader-lines, wires the two visibility toggles.
- `web/src/pages/PlayersPage.tsx` — wired the lightbox in (previously absent); fixed a pre-existing bug where the hover-actions overlay's `pointer-events-auto` silently swallowed clicks meant for the photo underneath.
- `web/src/api/photoTaggerClient.ts` — added `getPhotoMetadata()`; removed the `write_metadata` param from `assignCluster()`.
- `web/src/pages/ReviewPage.tsx` — removed the "Write clear data back to photo" checkbox and its state (embedding is now unconditional, no user-facing toggle).
- `web/src/types/index.ts` — added `PhotoMetadata`/`PhotoMetadataPerson`; removed `MetadataWriteSummary`; simplified `AssignClusterResponse`.
- `web/tests/frontend-behavior.test.mjs` — updated the one test asserting the retired `write_metadata`/XMP behavior.
- `web/vite.config.ts` — added `test.include` scoping (Vitest was picking up Playwright and `node:test` files without it).
- `web/package.json` — added Vitest (`npm run test`).

## Test suite and results

**Backend — pytest:**
- `tests/test_iptc_writer.py` (new, 12 tests) — write/read/remove/dedup/atomicity/backup, against a real JPEG fixture and real exiftool (installed via Homebrew during this session).
- `tests/test_photo_metadata.py` (new, 12 tests) — sparse output, each section's presence/absence, people filtering, game-section team_a/team_b derivation.
- `tests/test_api_phase2.py`, `test_blueprints_review_photos.py`, `test_error_recovery.py` — 5 pre-existing tests that exercised the retired `write_metadata`/XMP mechanism were rewritten to exercise the new unconditional IPTC path (real JPEGs, `is_backup_ready` monkeypatched, asserting via `iptc_writer.read_person_in_image`).
- Full suite: 660+ tests passing before this change; targeted re-runs after every backend change stayed green throughout. Final full-suite confirmation run in progress at hand-off (see QA note below).

**Frontend — Vitest (new) + node:test (existing):**
- `web/src/utils/__tests__/labelPlacement.test.ts` (new, 7 tests) — isolated-face labeling, face-avoidance invariant, dense-cluster pin degradation, leader-line ambiguity, unassigned-face pins, bounds-checking, two-separated-faces case.
- `web/tests/frontend-behavior.test.mjs` (existing, 8 tests, 1 rewritten) — all passing.
- `npx tsc --noEmit` — clean.
- `npm run build` — succeeds.

**Live verification (browser, not just tests):** started both dev servers, opened Players → a multi-face photo, and confirmed against real data (photo with 5 faces, one already assigned to "Declan Miller"): the assigned face got a name label, the four unassigned faces got numbered pins matching the panel's People list numbers exactly, the Names/Boxes toggles each independently hid/showed their layer, and the inline "Assign" flow opened correctly. No console errors. Screenshots taken during the session.

## Deviations from the architecture / spec (synced here per the artifact-sync requirement)

1. **Game section source corrected.** The architecture assumed `team_a`/`team_b` both live on `photo_batches`. They don't — that table has one `team_name` column; the second team comes from the pre-existing global `game_context_teams` table (`GET/PUT /api/game-context`), using the same opponent-derivation logic already in the codebase (`write_assignment_metadata`'s old opponent lookup). `photo_metadata.py`'s `_read_game_section()` now composes both sources. This is a correction to the architecture doc's assumption, not a new design choice — `photo_batches.team_name` = `team_a`, and `team_b` is the other `game_context_teams` entry if exactly one exists.
2. **`library.batch_id` added** to the metadata response (not in the original spec's field list) — needed so the MetadataPanel's "+ Add teams & tournament" button knows which batch to call `PUT /api/batches/<id>` on.
3. **exiftool clear+add must be two separate subprocess invocations.** Empirically verified (architecture flagged this as an open question): combining `-TAG=` and `-TAG+=value` in one exiftool command does not clear before adding on exiftool 13.55 — the old values survive. `write_iptc()` issues a clear call, then a separate add-all call.
4. **Pin-search algorithm strengthened beyond the architecture's description.** While building `labelPlacement.ts`'s test suite, found that the originally-planned single bounded search could fall through to a fallback that didn't check face-overlap at all — a real violation of the spec's hard "never on a face" rule under extreme density. Replaced with a two-pass search (soft: avoid all placed elements, bounded; hard: avoid faces only, unbounded up to the image diagonal) so the face-avoidance invariant holds regardless of density.
5. **Unassigned faces get numbered pins, not nothing.** The architecture's algorithm description (mirroring the spec's pseudocode) said to skip faces with no name. The approved visual mockups from the design session show pins on *every* detected face, assigned or not — so a user can correlate "pin #3" with the panel's "Assign" link before a name exists. Implemented to match the mockups; the pseudocode was the stale artifact here.

## Backlog (deferred, not implemented)

Carried from the architect stage plus this stage's additions — see `docs/product/backlog.md`:
- `iptc_ok` health-check self-test (mirroring the existing `ocr_ok` pattern).
- Soft client-visible warning if silent IPTC-write failure logging proves too invisible in practice.
- Guard the in-memory backup-done flag with a lock (low-impact under `threaded=True`).
- Remove the now-vestigial `write_metadata` reference, if any remains, from `photoTaggerClient.ts` — confirmed removed during this stage.
- Cross-reference the `people` array shape directly in `04-architecture.md` §6 (currently only in the spec) — documentation polish, not functional.

## Notes for QA

- `exiftool` is now installed in this dev environment (Homebrew, v13.55) — QA's environment needs it too, or the IPTC-embedding tests/flows will hit the graceful-degradation path (silently skipped) rather than actually verifying embedding.
- `uploads_backup/` was created during this session's live verification (432 files copied from the real `uploads/` directory) — this is expected, one-time, and safe; QA should not need to reset it.
- The full backend test suite (660+ tests, ~7 min due to ML model loading) was re-confirmed passing after every backend change in this session; a final full run was kicked off at hand-off time to catch any interaction effects from the last few edits (`batch_id` addition).
