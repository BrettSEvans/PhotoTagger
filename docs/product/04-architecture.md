# Architecture — PhotoTagger: Photo Metadata & Adaptive Labeling

> The technical architecture for features #1–#4 (photo lightbox, metadata panel,
> IPTC embedding, adaptive label placement, visibility toggles). Written by the
> architect from `docs/superpowers/specs/2026-07-30-photo-metadata-design.md`,
> which stands in for the skipped PM/UX/UI stages (requirements, flows, and
> visual design were validated there via the superpowers:brainstorming skill
> before this track entered Agent-C). Read by the engineer next.
> Product type: web app (Flask + React, local-first). Date: 2026-07-31

## 1. Architectural drivers & constraints

**Drivers this architecture optimizes for:**
- **Correctness under the existing concurrency model.** PhotoTagger's SQLite layer
  is a single connection + one `threading.RLock` shared by every repository
  (`docs/ARCHITECTURE.md` §7). Every statement — reads included — must serialize on
  that lock; this was the root cause of a prior production incident
  (`resolve_roster_candidates()` segfault). Any new repository code in this feature
  inherits that constraint with zero exceptions.
- **Non-destructive by default, destructive by explicit design.** PhotoTagger's
  existing convention (`docs/ARCHITECTURE.md` §1) is XMP sidecars — never touch the
  original file. This feature *deliberately reverses that* for player names: it
  embeds into the JPEG itself. That reversal is intentional (spec §5, approved by
  the user) but is the single biggest deviation from established project philosophy
  and must be flagged, backed up, and made robust to partial failure.
- **Local, synchronous UI responsiveness.** The label placement solver runs once
  per lightbox open/toggle, against ≤10s of face boxes, entirely client-side — no
  network round-trip for a visual recompute.
- **No new services, no new deployment topology.** This stays inside the existing
  `local-agent` monolith (Flask blueprints + React SPA). `cloud-ui` mode already
  disables ML entirely (`app.crawler = None` etc.), so it is unaffected by this
  feature's exiftool dependency.
- **Graceful degradation on missing exiftool.** The one new external dependency is
  a system binary. Every write path must be attempted, caught, logged, and never
  fail the parent HTTP request (spec §10).

**Hard constraints:**
- `src/repositories/_base.py`'s `self._lock` (RLock) — no new query method touches
  `self._conn` outside `with self._lock:`.
- No new tables, no schema migration (spec §2.3, confirmed against `src/schema.py`
  — `photo_batches` already has `team_name`/`team_year`/`tournament` columns).
- `exiftool` is required only for IPTC embedding; absence must not degrade
  features #1, #3, #4.
- Photos in `uploads/` are the *only* copies (435 files, ~47 MB) — the backup
  step is mandatory before any embedded write, not optional hardening.

## 2. System context & boundaries

**In scope (owned by this feature):**
- A read-only metadata projection (`src/photo_metadata.py`) composing existing
  repositories into one sparse response.
- An IPTC embedding module (`src/iptc_writer.py`) wrapping the `exiftool` binary.
- Modifications to the existing assign/deassign endpoints to trigger embedding.
- A client-side adaptive label placement solver (`web/src/utils/labelPlacement.ts`).
- A metadata side panel and a rewritten lightbox (`MetadataPanel.tsx`,
  `PhotoLightbox.tsx`), and wiring the lightbox into `PlayersPage.tsx` (which
  currently has no full-size photo view at all).

**Explicitly out of scope** (spec §8.1): per-photo game metadata overrides (batch-level
only), face re-clustering, bulk assignment, photo export, external sync.

**External system boundary — new:** `exiftool`, invoked as a local subprocess
(never a network call). This is the *only* new integration point in the entire
system context; everything else composes existing in-process modules.

**Systems this feature reads from but does not modify:** `face_cluster.py`,
`uniform_detector.py`, `jersey_recognition.py` — their outputs (`faces`,
`ocr_results`, `player_clusters` rows) are consumed read-only.

**Systems this feature retires:** the XMP-sidecar write path
(`metadata_sidecar.py` → `write_xmp_sidecar()`) as invoked from
`write_assignment_metadata()` in `src/api.py`. That function is deleted, not just
unused (spec §5.4) — see ADR-3.

## 3. Architecture style & major components

No new architecture style — this extends the existing full-stack monolith
(Flask blueprints ↔ single SQLite connection ↔ React SPA) additively. No new
process, no new deployment mode.

### 3.1 Module dependencies

| Module | Depends on | Exports | Purpose |
|---|---|---|---|
| `src/photo_metadata.py` (new) | `PhotoRepository`, `FaceRepository`/cluster queries, `BatchRepository`, OCR query methods — all via the `Database` facade | `read(photo_id) -> dict` (sparse) | Compose a read-only, populated-fields-only metadata projection for one photo |
| `src/iptc_writer.py` (new) | filesystem, `subprocess` (exiftool binary), `src/utils.is_allowed_photo_path` | `write_iptc(filepath, names_to_add, names_to_remove)`, `backup_directory(src, dest)`, `IptcWriteError` | Embed/remove `XMP-iptcExt:PersonInImage` in a JPEG via exiftool; one-time backup |
| `src/blueprints/photos.py` (modified) | `photo_metadata` | new route `GET /api/photos/<id>/metadata` | Serve the sparse metadata dict |
| `src/blueprints/review.py` (modified) | `iptc_writer`, `PhotoRepository` (resolve file paths for a cluster) | modified `POST /api/players/<cluster_id>/assign`, `POST /api/faces/deassign` | Trigger embed/remove unconditionally on assign/unassign |
| `src/blueprints/batches.py` (unchanged) | — | existing `PUT /api/batches/<id>` | Reused as-is for Game section writes (see ADR-5) |
| `src/api.py` (modified) | — | `write_assignment_metadata()` **removed** | Retires the XMP-sidecar call path |
| `web/src/utils/labelPlacement.ts` (new) | none (pure TS, no React, no network) | `placeLabels(bboxes, names, width, height)` | Adaptive label/pin/leader-line geometry solver |
| `web/src/components/MetadataPanel.tsx` (new) | `photoTaggerClient`, `types/index.ts` | `MetadataPanel` component | Right-side panel: toggles, file/image/library/game/people sections |
| `web/src/components/PhotoLightbox.tsx` (rewritten) | `labelPlacement.ts`, `MetadataPanel.tsx`, `bboxUtils.ts` (existing, reused), `photoTaggerClient` | `PhotoLightbox` component | Two-column lightbox: image+overlay left, metadata panel right |
| `web/src/pages/PlayersPage.tsx` (modified) | `PhotoLightbox` | — | Wires click-to-open lightbox (currently absent on this page) |

`iptc_writer.py` and `labelPlacement.ts` have **zero dependencies on each other or
on any other new module** — they are independently implementable and testable in
parallel. `photo_metadata.py` depends only on existing repositories (read-only),
so it can also be built in parallel with the other two.

## 4. Runtime behavior & key scenarios

**Scenario A — Open lightbox (feature #1, #3):**
1. Client fires `GET /api/photos/:id/metadata` (new), `GET /api/faces/:id`,
   `GET /api/photos/:id/jersey-detections` in parallel (`Promise.all`, matching
   the existing pattern already in `PhotoLightbox.tsx`).
2. On image load, client runs `labelPlacement.placeLabels()` synchronously against
   the loaded image's natural dimensions — no additional network call.
3. SVG renders bboxes (if `showBoxes`) and labels/pins/lines (if `showNames`).

**Scenario B — Assign a face to a player (feature #2):**
1. `POST /api/players/<cluster_id>/assign` (existing route) runs the existing
   `assign_cluster_to_player()` DB write (inside the lock, as today).
2. **New, unconditional:** after the DB write commits, resolve the photo file
   paths for every face in the cluster (a locked read), release the lock, then
   call `iptc_writer.write_iptc(path, names_to_add=[player_name])` for each file
   **outside** the lock.
3. Any `IptcWriteError` is caught and logged per-file; the HTTP response still
   returns `200` (spec §10 — non-fatal).

**Scenario C — Deassign a face (feature #2):**
Currently `POST /api/faces/deassign` only touches the DB (`db.faces.deassign_faces`)
and never talks to metadata. New behavior: **before** deassigning, resolve each
face's current `player_name` (via its cluster) and file path (locked read);
after the DB deassignment commits, call `iptc_writer.write_iptc(path,
names_to_remove=[player_name])` outside the lock. Same non-fatal error handling.

**Scenario D — First write in a process lifetime (feature #2 safety):**
Before the *first* `write_iptc()` call, check for `uploads_backup/` on disk; if
absent, copy all JPEGs from `uploads/` there (idempotent — an in-memory flag
short-circuits repeat checks within the same process, but the on-disk check is
the source of truth across restarts).

**Concurrency note (why this matters here specifically):** exiftool subprocess
calls take ~100–300 ms and do no DB I/O. They **must never run while holding
`self._lock`** — doing so would serialize every other DB read/write app-wide
(including the dashboard's continuous polling) for the duration of the subprocess
call, reproducing the same class of stall the roster-import incident already
taught this codebase to avoid. The lock is acquired only for the brief read
(resolve file paths / player names) before the subprocess call, and released
before it runs.

## 5. Data model & state

**No new tables** (confirmed against `src/schema.py`). `photo_batches` already
carries `team_name`, `team_year`, `tournament` — the Game section and its "+ Add
teams & tournament" button read/write these existing columns via the *existing*
`PUT /api/batches/<id>` endpoint (see ADR-5), not a new one.

**Source-of-truth split (new, and worth naming explicitly):** player-identity-in-photo
now has two representations:
1. **SQL — canonical for the app.** `faces.cluster_id` → `player_clusters.player_name`.
   This is what every PhotoTagger UI reads and what search/review pages trust.
2. **Embedded JPEG XMP — a derived projection for external consumers** (Lightroom,
   Finder, any downstream tool that reads the file directly). Written best-effort
   from (1); can silently drift behind SQL truth if exiftool is missing or a write
   fails (see Deltas — this is an accepted, documented risk, not a bug to "fix" in
   this feature).

`photo_metadata.read()` is a **read-time projection**, not a stored view — computed
fresh from `photos`, `ocr_results`, `player_clusters`, `photo_batches`, `faces` on
every call, mirroring `review_service.py`'s existing pattern of composing repository
reads rather than maintaining a denormalized cache.

## 6. Interfaces & contracts

| Endpoint | Change | Contract |
|---|---|---|
| `GET /api/photos/<id>/metadata` | **New** | 200 → sparse JSON (only populated sections per spec §3 table); 404 if photo not found |
| `PUT /api/batches/<id>` | **Reused, unchanged** | Existing `team_name`/`team_year`/`tournament`/`name` body; MetadataPanel's Game button targets this directly |
| `POST /api/players/<cluster_id>/assign` | **Modified** | `write_metadata` request param **removed**; embed is now unconditional and silent-on-failure (see ADR-2) |
| `POST /api/faces/deassign` | **Modified** | Now also resolves + removes IPTC names for affected photos before/around the existing DB deassignment |

`iptc_writer.write_iptc(filepath: str, names_to_add: list[str] = [], names_to_remove: list[str] = []) -> None`
— raises `IptcWriteError` on failure; callers catch and log, never propagate as a
500. Internally: read current `XMP-iptcExt:PersonInImage` values via exiftool,
merge in `names_to_add`, drop `names_to_remove`, write to a temp file, verify, then
atomically replace the original (spec §5.2).

`labelPlacement.placeLabels(bboxes, names, imageWidth, imageHeight): { labels, pins, lines }`
— pure function, TypeScript interface mirrors spec §4.1's pseudocode:

```ts
interface FaceBox { id: number; x: number; y: number; width: number; height: number }
interface PlacedLabel { id: number; name: string; x: number; y: number; width: number; height: number }
interface PlacedPin   { id: number; number: number; x: number; y: number }
interface LeaderLine  { fromId: number; toX: number; toY: number }

function placeLabels(
  bboxes: FaceBox[],
  names: Record<number, string>,
  imageWidth: number,
  imageHeight: number,
): { labels: PlacedLabel[]; pins: PlacedPin[]; lines: LeaderLine[] }
```

## 7. Key technical decisions

| Decision | Choice | Rationale | Alternatives considered | Consequences |
|---|---|---|---|---|
| IPTC embedding mechanism | `exiftool` subprocess, invoked with an argument list (never `shell=True`) | Industry-standard tool for exactly this field (`XMP-iptcExt:PersonInImage` repeating bag); already named as the dependency in the approved spec; no new Python package to vendor | `piexif` (pure Python, but weak/manual XMP-RDF bag support — not built for repeating IPTC-Ext fields); `pyexiv2` (powerful but adds a compiled C++ binding with a worse cross-platform install story than one `brew install exiftool`) | Adds ~100–300 ms subprocess latency per write and an external-binary install prerequisite; gains atomic `-o`-to-tempfile writes and correct XMP bag semantics for free |
| Unconditional vs. opt-in embed on assign/unassign | **Unconditional** — remove the existing `write_metadata` boolean param | Matches the user-approved UX decision from brainstorming ("Immediately on assign/unassign"); a client-side opt-in flag would re-introduce the ambiguity that decision resolved | Keep `write_metadata` as an opt-in flag (status quo shape) | Simpler client (no toggle to wire); removes the ability to skip a write even when exiftool is known-flaky — mitigated entirely by non-fatal error handling (§10) |
| Retire XMP-sidecar call path | Delete `write_assignment_metadata()` from `src/api.py`; stop calling `write_xmp_sidecar()` from the assign flow | Spec §5.4: the two mechanisms would otherwise disagree about which is authoritative | Keep both, sidecar as a "fallback" | One clear write path instead of two competing ones; `metadata_sidecar.py` itself is left in place (module has no other confirmed callers at analysis time — **engineer must grep for other callers/tests before deleting the file itself**, deleting only the call site is the safe minimal change) |
| Label placement runs client-side (TS), not server-side (Python) | **Client-side**, pure function | No network round-trip per toggle/re-render; placement depends on the client's already-rendered SVG viewBox/natural image dimensions; matches the existing precedent of `bboxUtils.ts`'s background-color analysis already running against the loaded `<img>` client-side | Server computes and returns pre-positioned labels in the metadata endpoint | Solver and its tests live entirely in the frontend; requires a frontend test runner (see below — none exists yet) |
| Game metadata endpoint | **Reuse existing** `PUT /api/batches/<id>` | It already accepts `team_name`/`team_year`/`tournament` — the spec's proposed new `PUT /api/batches/<id>/game` endpoint would be a duplicate | Add the new endpoint as the spec originally proposed | Zero backend change needed for this piece of feature #1 — only frontend wiring; **explicit deviation from spec §2.1**, flagged here per Decision quality practice |
| Frontend test runner | **Adopt Vitest** | `web/package.json` currently has no test script or test runner at all; Vitest is the Vite-native, near-zero-config choice and is what the spec's own test plan (§7.1) assumes | Jest (works, but needs a separate transform/config layer on top of Vite that Vitest doesn't) | Engineer's first frontend task is `npm install -D vitest` + a minimal config, before `labelPlacement.test.ts` can run |

**Implementation timeline estimate** (from architect handoff):
- **Standard Mode (with approval gates):** ~2.5–3 weeks — architect → engineer →
  QA → QC with a human gate between each (1–2 days/gate).
- **Beast Mode (auto-accept, no inter-stage gates):** ~1–1.5 weeks — engineer, QA,
  QC run back-to-back; final ship decision still requires human approval.

## 8. Cross-cutting concerns

- **Security:** `iptc_writer` invokes exiftool via an argument list, never shell
  string interpolation — player names (roster-sourced, low-risk but still
  external-ish input) must never be concatenated into a shell command. Every file
  path touched by the new endpoints (`write_iptc`, backup) is checked against
  `src/utils.is_allowed_photo_path()` before use, matching the existing
  `serve_image` / SSRF-hardening conventions already documented in
  `docs/ARCHITECTURE.md` §13.
- **Error handling:** the new `GET /api/photos/<id>/metadata` route follows the
  existing blueprint convention (`try/except Exception → 500 {"error": str(e)}`).
  IPTC write failures inside assign/deassign are the one deliberate exception to
  that convention — caught, logged server-side only, never surfaced as a failed
  request (spec §10).
- **Observability:** recommend (open question, not required by spec) extending
  `GET /health`'s existing `ocr_ok` self-test pattern
  (`docs/ARCHITECTURE.md` §5.3) with an analogous `iptc_ok` flag — a one-line
  `exiftool -ver` self-test at startup, so a missing exiftool install is visible
  immediately instead of manifesting as silently-skipped writes discovered later.
- **Testability:** the pure-function solver is unit-testable without a DOM;
  `iptc_writer` tests operate on `tmp_path` copies of a real JPEG, matching the
  existing `conftest.py` fixture style (`app`/temp-DB fixtures already present in
  `tests/conftest.py`).

## 9. Deployment, distribution & operations

No new deployment topology. This feature only exists in `local-agent` mode — the
mode that already owns the crawler/OCR/filesystem access; `cloud-ui` mode has
`app.crawler = None` etc. and never touches ML or exiftool, so it's unaffected.

**New operational prerequisite:** `exiftool` must be installed on whatever
machine runs `local-agent` mode (`brew install exiftool` on macOS, package
manager equivalent on Linux). This is a manual, user-run install step — nothing
in this feature installs it automatically. Document in `README.md`'s
Prerequisites section (currently lists Python 3.11+, RAM, disk — exiftool is
missing from that list and should be added as part of the engineer's doc pass).

## Risks, NFR gaps & open technical questions

- **Exact exiftool invocation for list-type XMP fields is unverified.** Whether
  `-XMP-iptcExt:PersonInImage+=Name` / `-=Name` incremental syntax behaves
  correctly for repeating bags on the installed exiftool version, versus a
  read-full-list/modify/write-full-list round-trip, needs empirical verification
  against a real photo during implementation — flagged for the engineer, not
  resolved here (this is exactly the kind of fast-moving/version-specific fact the
  best-practices discipline says to verify against a live source rather than guess).
- **SQL-vs-embedded-JPEG drift is an accepted, permanent risk**, not something
  this feature closes. If exiftool silently fails on some photos, PhotoTagger's UI
  stays correct (SQL is canonical) but any external tool reading the JPEG directly
  will disagree. No reconciliation/backfill job is in scope.
- **`metadata_sidecar.py` disposition:** confirmed as no-longer-called from the
  assign/unassign flow; whether the module file itself should be deleted depends
  on whether anything else (tests, docs) still references it — engineer must grep
  before deleting.
- **Silent IPTC failure UX:** spec and this architecture both choose fully-silent
  server-side-only failure logging. If that later proves too invisible in
  practice (user can't tell "did the name actually get embedded?"), a follow-up
  could surface a soft warning in the assign response — explicitly deferred, not
  designed here.

## Diagrams

Declined — none produced. This feature is additive to an already-diagrammed
system (`docs/ARCHITECTURE.md` already has architecture/deployment/pipeline/data-model
diagrams); the module dependency table in §3.1 and the runtime scenarios in §4
are sufficient to convey the new structure without a redundant diagram set.

## Deltas (required quality improvements)

| Risk (P0/P1) | Recommendation | Rationale | Prerequisite for next stage? |
|---|---|---|---|
| P1 — Reversal of project's non-destructive-by-default philosophy | Ship the mandatory one-time `uploads_backup/` (spec §5.1) as a hard precondition of the *first* embedded write, verified by a test that asserts no write proceeds without a successful backup | This is the one place this feature diverges from `docs/ARCHITECTURE.md`'s stated design goal ("Non-destructive… tags written to XMP sidecars, never the image file"). The backup is what makes that reversal safe | Yes — engineer must implement backup-then-write ordering, not write-then-backup |
| P1 — exiftool subprocess latency inside a request path | Confirm (via the concurrency note in §4) that `write_iptc()` calls happen strictly outside `self._lock`, and add the structural test pattern already used for lock discipline (`tests/test_db_connection_locking.py`) to also assert the new review.py code paths never call `iptc_writer` while holding the lock | Prevents reproducing the exact class of dashboard-polling stall this codebase already suffered once (roster import incident) | Yes — blocks engineer; extend the existing lock-discipline test suite rather than trusting code review alone |
| P1 — No frontend test infrastructure exists today | Adopt Vitest before writing `labelPlacement.ts`'s tests (ADR in §7) | Spec §7.1 assumes unit tests for the solver; `web/package.json` has zero test tooling currently | Yes — blocks the solver's test-driven implementation |
| P0 — exiftool XMP list-field syntax unverified | Engineer must empirically verify the exact exiftool invocation against a real photo (spec §5.2, §10) before wiring it into the assign/deassign flow | An untested assumption about incremental `+=`/`-=` syntax could silently corrupt or fail to update the `PersonInImage` bag | Yes — first engineer task on the backend slice |

---

## Decisions (confirmed)

- exiftool subprocess (not a Python XMP library) for IPTC embedding.
- IPTC embed/remove is unconditional on assign/unassign — no client opt-in flag.
- `write_assignment_metadata()` and its XMP-sidecar call are deleted from
  `src/api.py`; `metadata_sidecar.py` module itself is left in place pending an
  unused-reference check.
- Label placement solver runs client-side as a pure TypeScript function.
- Game metadata reuses the existing `PUT /api/batches/<id>` endpoint — no new
  endpoint is added (deviation from spec §2.1, approved here).
- No new database tables or schema migrations.
- Vitest adopted as the frontend test runner (none existed before).

## Assumptions

- Diagrams declined (Beast Mode, non-interactive architect run) — the module
  table and runtime scenarios are treated as sufficient; can be revisited on
  request.
- `metadata_sidecar.py` is assumed safe to leave in place (not delete) absent
  confirmation that nothing else references it.
- The health-check `iptc_ok` extension (§8) is a recommendation, not a
  requirement — spec did not ask for it; engineer/QA may defer it to backlog.

## Open questions

- Exact exiftool CLI invocation for incremental list-field writes — verify
  empirically during implementation (see Risks).
- Whether `metadata_sidecar.py` has any other callers/tests that would block
  deleting the file entirely (only its *call site* is confirmed removable).
- Whether silent-only IPTC failure logging needs a client-visible signal later
  (explicitly deferred, not designed in this pass).

## Next handoff

Engineer → reads this document plus
`docs/superpowers/specs/2026-07-30-photo-metadata-design.md` (requirements/UX/UI
source) and implements features #1–#4 per §3.1's module table, starting with the
two dependency-free modules (`iptc_writer.py`, `labelPlacement.ts`) that can be
built in parallel, then `photo_metadata.py`, then the endpoint/UI wiring that
depends on all three.
