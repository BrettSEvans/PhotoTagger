# PhotoTagger Structural Refactor Plan
## Blueprints + Repository Split

**Branch:** `refactor/blueprints-repositories` ✓ Active  
**Test baseline:** 221 tests passing (212 original + 9 from schema/conftest/repos)

---

## Progress

### Phase 0 — Setup ✅ COMPLETE
- [x] Extract `src/schema.py` (freed 160 lines from db.py)
- [x] Create `tests/conftest.py` with shared fixtures
- [x] Add `tests/test_schema.py` and `tests/test_conftest_fixtures.py`
- [x] Baseline: 215 tests → 221 tests

### Phase 1 — Repository Split 🔄 IN PROGRESS
- [x] **Phase 1.0:** Create `src/repositories/` with `_base.py` (BaseRepository)
- [x] **Phase 1.1:** Extract JobRepository (3 methods, 3 tests, delegation stubs)
- [ ] **Phase 1.2:** Extract GameContextRepository (2 methods, 2 tests)
- [ ] **Phase 1.3:** Extract BatchRepository (8 methods, 8 tests)
- [ ] **Phase 1.4:** Extract FaceRepository (8 methods, 8 tests)
- [ ] **Phase 1.5:** Extract ClusterRepository (8 methods, 8 tests)
- [ ] **Phase 1.6:** Extract RosterRepository (9 methods, 9 tests)
- [ ] **Phase 1.7:** Extract PhotoRepository (18 methods, 18 tests)
- [ ] **Phase 1.8:** Extract ReviewService (3 methods from Photo, new module)
- [ ] **Phase 1.9:** Migrate all callers (api.py, crawler.py, ocr.py, face_cluster.py, tests)
- [ ] **Phase 1.10:** Delete delegation stubs, verify db.py ≤150 lines

### Phase 2 — Blueprint Split ⏳ PENDING
- [ ] Move routes to `src/blueprints/`
- [ ] Extract helpers to `src/utils.py`, `src/job_runner.py`
- [ ] Verify api.py ≤80 lines

### Phase 3 — Test Reorganization ⏳ PENDING
- [ ] Reorganize tests into `tests/test_repositories/` and `tests/test_blueprints/`

---

**Prerequisite:** All 212 tests passing before starting. Run `pytest tests/ -q` to confirm.

---

## Why This Refactor

### Current problems

| File | Lines | Methods/Routes | Problem |
|------|-------|----------------|---------|
| `src/api.py` | 1,274 | 41 routes, all closures inside `create_app()` | No route is importable or independently testable; adding a feature requires editing a 1,200-line file |
| `src/db.py` | 1,400 | 59 methods, 1 class | Eight different data domains in one class; mocking any one domain in tests requires mocking all of them |

### Target: zero change to public API URLs or DB schema
Blueprints is a routing reorganisation. Repositories is a code organisation. No URL changes, no schema changes, no behaviour changes. Every existing test must still pass after each phase.

---

## Phase 1 — Repository Split (`src/db.py` → `src/repositories/`)

### Target directory structure

```
src/
  repositories/
    __init__.py          # exports: PhotoRepo, FaceRepo, RosterRepo, ClusterRepo, BatchRepo, JobRepo, GameContextRepo
    _base.py             # BaseRepository (shared connection + lock)
    photo.py             # PhotoRepository
    face.py              # FaceRepository
    roster.py            # RosterRepository
    cluster.py           # ClusterRepository
    batch.py             # BatchRepository
    job.py               # JobRepository
    game_context.py      # GameContextRepository
  db.py                  # KEPT — thin coordinator, backwards-compatible façade
```

`src/db.py` is **not deleted**. It becomes a thin class that instantiates all repositories and delegates to them so that all existing callers (`api.py`, `face_cluster.py`, `ocr.py`, etc.) continue working without change during the transition.

---

### `_base.py` — shared infrastructure

```python
# src/repositories/_base.py
import sqlite3
import threading
from typing import Optional

class BaseRepository:
    def __init__(self, conn: sqlite3.Connection, lock: threading.RLock):
        self._conn = conn
        self._lock = lock
```

Every repository receives the shared `conn` and `lock` from the coordinator. No repository opens its own connection.

---

### Method → Repository mapping

#### `PhotoRepository` (`src/repositories/photo.py`)

| Method | Moved from `db.py` |
|--------|-------------------|
| `add_photo()` | line 180 |
| `count_photos()` | line 236 |
| `get_all_photos(limit, offset)` | line 243 |
| `get_photo_by_id()` | line 262 |
| `get_photo_ocr()` | line 270 |
| `get_latest_ocr_by_photo_ids()` | line 280 |
| `get_photo_by_jersey()` | line 222 |
| `photo_exists()` | line 302 |
| `add_ocr_result()` | line 205 |
| `get_assigned_player_for_photo()` | line 550 |
| `get_photos_by_face_ids()` | line 864 |
| `get_processing_summary()` | line 886 |
| `get_confirmed_photos()` | line 907 |
| `get_review_photos()` | line 930 |
| `_get_latest_ocr_rows()` | line 951 (private helper) |
| `resolve_roster_candidates()` | line 968 |
| `_color_match_score()` | line 1025 (static helper) |
| `_compute_file_hash()` | line 1403 (static, keep on Database too) |

> **Note:** `resolve_roster_candidates` and `_color_match_score` deal with roster data but are called in photo-display loops. Keep them on `PhotoRepository` but accept a pre-fetched `game_context` list to avoid cross-repository queries inside the method.

---

#### `FaceRepository` (`src/repositories/face.py`)

| Method | Moved from `db.py` |
|--------|-------------------|
| `add_face()` | line 383 |
| `get_faces_by_photo()` | line 408 |
| `get_all_faces()` | line 568 |
| `get_face_by_id()` | line 592 |
| `get_face_count()` | line 688 |
| `get_face_photo_location()` | line 1125 |
| `photo_has_faces()` | line 430 |
| `deassign_faces()` | line 1050 |

---

#### `RosterRepository` (`src/repositories/roster.py`)

| Method | Moved from `db.py` |
|--------|-------------------|
| `add_roster_entry()` | line 437 |
| `roster_entry_exists()` | line 485 |
| `import_roster_entries()` | line 495 |
| `get_all_roster_entries()` | line 697 |
| `delete_roster_entry()` | line 726 |
| `update_roster_entry()` | line 733 |
| `search_roster()` | line 826 |
| `get_roster_entry_by_id()` | line 843 |
| `get_player_name()` | line 539 |

---

#### `ClusterRepository` (`src/repositories/cluster.py`)

| Method | Moved from `db.py` |
|--------|-------------------|
| `add_player_cluster()` | line 621 |
| `assign_face_to_cluster()` | line 632 |
| `get_all_player_clusters()` | line 639 |
| `get_photos_by_cluster()` | line 663 |
| `clear_clusters()` | line 613 |
| `get_cluster_by_id()` | line 1102 |
| `get_cluster_face_embeddings()` | line 1146 |
| `get_unidentified_clusters_with_embeddings()` | line 1155 |
| `assign_cluster_to_player()` | line 1176 |

---

#### `BatchRepository` (`src/repositories/batch.py`)

| Method | Moved from `db.py` |
|--------|-------------------|
| `create_batch()` | line 1194 |
| `get_batch()` | line 1223 |
| `get_all_batches()` | line 1247 |
| `update_batch()` | line 1271 |
| `delete_batch()` | line 1299 |
| `get_photos_by_batch()` | line 1310 |
| `get_batch_by_source_folder()` | line 1334 |
| `update_batch_photo_count()` | line 1358 |

---

#### `JobRepository` (`src/repositories/job.py`)

| Method | Moved from `db.py` |
|--------|-------------------|
| `create_processing_job()` | line 309 |
| `update_processing_job()` | line 320 |
| `get_processing_job()` | line 357 |

---

#### `GameContextRepository` (`src/repositories/game_context.py`)

| Method | Moved from `db.py` |
|--------|-------------------|
| `set_game_context()` | line 454 |
| `get_game_context()` | line 471 |

---

#### `Database` coordinator — what stays in `src/db.py`

```python
class Database:
    def __init__(self, db_path):
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.RLock()

        # Repository instances — all share the same conn + lock
        self.photos   = PhotoRepository(self._conn, self._lock)
        self.faces    = FaceRepository(self._conn, self._lock)
        self.roster   = RosterRepository(self._conn, self._lock)
        self.clusters = ClusterRepository(self._conn, self._lock)
        self.batches  = BatchRepository(self._conn, self._lock)
        self.jobs     = JobRepository(self._conn, self._lock)
        self.context  = GameContextRepository(self._conn, self._lock)

    def init_schema(self): ...   # kept here — touches all tables
    def reset_all_data(self): ...
    def close(self): ...

    # Backwards-compatible delegation so existing callers don't change during transition
    def add_photo(self, *a, **kw):       return self.photos.add_photo(*a, **kw)
    def get_photo_by_id(self, *a, **kw): return self.photos.get_photo_by_id(*a, **kw)
    # ... one delegation stub per method ...
```

**Migration strategy:** Add the delegation stubs first. All existing callers continue working. Then migrate callers one Blueprint at a time to use `db.photos.add_photo()` directly. Once all callers are migrated, delete the stubs.

---

### Schema management stays in `Database.init_schema()`

The `init_schema()` method and all its `ALTER TABLE` migrations remain on the `Database` coordinator — it's the only place that knows the full schema. Do not split it across repositories.

---

### `_compute_file_hash()` placement

Keep as a `@staticmethod` on `Database` AND add it to `PhotoRepository` (both can hold it since it's pure computation with no DB access). `PhotoCrawler` currently calls `Database._compute_file_hash()` — that call site does not need to change.

---

## Phase 2 — Blueprint Split (`src/api.py` → `src/blueprints/`)

### Target directory structure

```
src/
  blueprints/
    __init__.py       # exports all blueprints for registration in create_app()
    system.py         # health, app-config, jobs, detection-status, data-reset, cloud-ui
    photos.py         # crawl, upload-photos, /api/photos, /api/image, /api/info
    detection.py      # detect-faces, cluster-players, /api/players (all), face-crop, faces/deassign
    roster.py         # all /api/roster/*, /api/game-context
    batches.py        # all /api/batches/*
    review.py         # processing-summary, confirmed-photos, review-photos, assign, match-similar
  api.py              # KEPT — create_app() registers blueprints, holds shared helpers only
```

---

### Route → Blueprint mapping

#### `system.py` blueprint — prefix `/`

| Route | Handler |
|-------|---------|
| `GET /health` | `health()` |
| `GET /api/app-config` | `app_config()` |
| `GET /api/jobs/<job_id>` | `get_job()` |
| `GET /api/detection-status` | `detection_status()` |
| `POST /api/data/reset` | `reset_all_data()` |
| `GET /` and `GET /<path>` | `serve_cloud_ui()` |

---

#### `photos.py` blueprint — prefix `/api`

| Route | Handler |
|-------|---------|
| `POST /api/crawl` | `crawl()` |
| `POST /api/upload-photos` | `upload_photos()` |
| `POST /api/process-ocr` | `process_ocr()` |
| `GET /api/photos` | `get_photos()` |
| `GET /api/image/<photo_id>` | `serve_image()` |
| `GET /api/info` | `info()` |
| `GET /api/search` | `search()` |

---

#### `detection.py` blueprint — prefix `/api`

| Route | Handler |
|-------|---------|
| `POST /api/detect-faces` | `detect_faces_endpoint()` |
| `POST /api/cluster-players` | `cluster_players()` |
| `GET /api/players` | `get_players()` |
| `GET /api/players/<cluster_id>/photos` | `get_player_photos()` |
| `GET /api/face-crop/<face_id>` | `serve_face_crop()` |
| `GET /api/faces/<photo_id>` | `get_faces()` |
| `POST /api/faces/deassign` | `deassign_faces()` |

---

#### `roster.py` blueprint — prefix `/api`

| Route | Handler |
|-------|---------|
| `GET /api/roster` | `get_roster()` |
| `POST /api/roster` | `add_roster()` |
| `DELETE /api/roster/<entry_id>` | `delete_roster()` |
| `PUT /api/roster/<entry_id>` | `update_roster()` |
| `GET /api/roster/search` | `search_roster()` |
| `POST /api/roster/infer` | `infer_team_and_year()` |
| `POST /api/roster/import` | `import_roster_file()` |
| `POST /api/roster/infer-url` | `infer_roster_url()` |
| `POST /api/roster/import-url` | `import_roster_url()` |
| `GET /api/game-context` | `get_game_context()` |
| `PUT /api/game-context` | `set_game_context()` |

---

#### `batches.py` blueprint — prefix `/api`

| Route | Handler |
|-------|---------|
| `GET /api/batches` | `list_batches()` |
| `GET /api/batches/<batch_id>` | `get_batch()` |
| `PUT /api/batches/<batch_id>` | `update_batch()` |
| `DELETE /api/batches/<batch_id>` | `delete_batch()` |

---

#### `review.py` blueprint — prefix `/api`

| Route | Handler |
|-------|---------|
| `GET /api/processing-summary` | `processing_summary()` |
| `GET /api/confirmed-photos` | `confirmed_photos()` |
| `GET /api/review-photos` | `review_photos()` |
| `POST /api/players/<cluster_id>/assign` | `assign_cluster()` |
| `POST /api/players/<cluster_id>/match-similar` | `match_similar_clusters()` |

---

### Shared helpers in `create_app()` — what stays in `api.py`

These are cross-cutting concerns that all blueprints need. They stay in `api.py` and are passed into blueprints via `app` config or `current_app`:

| Helper | How to share |
|--------|-------------|
| `enqueue_job()` | Move to `src/job_runner.py` as a free function; blueprints call it directly |
| `is_allowed_photo_path()` | Move to `src/utils.py`; import in any blueprint that needs it |
| `is_allowed_photo_directory()` | Same as above |
| `write_assignment_metadata()` | Move to `src/metadata_sidecar.py` or `src/review_service.py` |
| `valid_agent_token()` / `@before_request` | Keep in `api.py`; Flask applies `before_request` to all blueprints registered on the same app |
| `after_request` (CORS) | Keep in `api.py` |
| `parse_float()` / `parse_int_arg()` | Move to `src/utils.py` |
| `configured_photo_roots()` | Move to `src/utils.py` |
| `allowed_cors_origins()` | Keep in `api.py` |

---

### Blueprint registration in `create_app()`

```python
# src/api.py (after refactor)
def create_app(db_path="photo_catalog.db"):
    app = Flask(__name__)
    db = Database(db_path)
    db.init_schema()
    app.db = db

    # ... component init (crawler, ocr_engine, job_runner) ...

    from src.blueprints.system    import bp as system_bp
    from src.blueprints.photos    import bp as photos_bp
    from src.blueprints.detection import bp as detection_bp
    from src.blueprints.roster    import bp as roster_bp
    from src.blueprints.batches   import bp as batches_bp
    from src.blueprints.review    import bp as review_bp

    app.register_blueprint(system_bp)
    app.register_blueprint(photos_bp)
    app.register_blueprint(detection_bp)
    app.register_blueprint(roster_bp)
    app.register_blueprint(batches_bp)
    app.register_blueprint(review_bp)

    # before_request, after_request (CORS) defined here — apply to all blueprints
    ...
    return app
```

Each blueprint accesses shared objects via `current_app`:

```python
# Inside any blueprint handler
from flask import current_app
db = current_app.db
crawler = current_app.crawler
job_runner = current_app.job_runner
```

---

## Phase 3 — Test Migration

### Current test file → target test file mapping

| Current | Target | What changes |
|---------|--------|-------------|
| `tests/test_api.py` | `tests/test_blueprints/test_system.py` | Same tests, import path changes |
| `tests/test_api_phase2.py` | Split across `test_detection.py`, `test_roster.py`, `test_review.py` | Group by blueprint |
| `tests/test_api_coverage.py` | Split across blueprint test files | Group by blueprint |
| `tests/test_critical_fixes.py` | Keep as-is or merge into relevant files | No change needed |
| `tests/test_jobs.py` | `tests/test_blueprints/test_system.py` | Jobs endpoint is in system blueprint |
| `tests/test_validation.py` | Keep as-is | Cross-cutting validation; no move needed |
| `tests/test_db.py` | `tests/test_repositories/test_photo_repo.py` | Per-repo test files |
| `tests/test_db_phase2.py` | `tests/test_repositories/test_face_repo.py` | Per-repo test files |

### New test files to create

```
tests/
  test_repositories/
    __init__.py
    test_photo_repo.py    # PhotoRepository in isolation (no Flask)
    test_face_repo.py     # FaceRepository
    test_roster_repo.py   # RosterRepository
    test_cluster_repo.py  # ClusterRepository
    test_batch_repo.py    # BatchRepository
    test_job_repo.py      # JobRepository
    test_game_context_repo.py
  test_blueprints/
    __init__.py
    test_system.py
    test_photos.py
    test_detection.py
    test_roster.py
    test_batches.py
    test_review.py
```

**Repository tests** use only `sqlite3` and the repository class — no Flask client. This is the primary payoff: each domain's DB logic becomes independently testable without spinning up the whole app.

**Blueprint tests** use the Flask test client (`create_app(db_path=":memory:")`) exactly as current tests do. URLs are identical.

---

## Migration Order and Safety

### Recommended sequence (each step = one commit + all tests green)

1. **Create `src/repositories/_base.py`** with `BaseRepository` — no callers yet
2. **Extract `JobRepository`** (smallest, no cross-repo deps) — add delegation stub to `Database`
3. **Extract `GameContextRepository`** — same pattern
4. **Extract `BatchRepository`**
5. **Extract `FaceRepository`**
6. **Extract `ClusterRepository`** (depends on FaceRepository for some queries — keep queries in their own repo, pass results across)
7. **Extract `RosterRepository`**
8. **Extract `PhotoRepository`** (largest; depends on roster context) — add `resolve_roster_candidates()` last
9. **Remove delegation stubs from `Database`** once all direct callers have been migrated to use `db.photos.method()` syntax
10. **Create blueprint stubs** — empty blueprints registered in `create_app()`, all routes still in `api.py` (tests still pass)
11. **Move `system.py` routes** — smallest blast radius
12. **Move `batches.py` routes**
13. **Move `roster.py` routes**
14. **Move `photos.py` routes**
15. **Move `detection.py` routes**
16. **Move `review.py` routes** — most complex (uses `write_assignment_metadata`, numpy)
17. **Delete remaining dead code from `api.py`** — should be near-empty except `create_app()`
18. **Migrate test files** to new directory layout

---

## Cross-Cutting Dependencies to Watch

### `write_assignment_metadata()` in `api.py` (line 127)
Currently a closure inside `create_app()`. It calls `db`, `is_allowed_photo_path()`, and `write_xmp_sidecar()`. Move to `src/review_service.py` as a free function that takes `db` as a parameter. Both the `assign_cluster` and `match_similar_clusters` handlers import it.

### `_cosine_similarity()` in `match_similar_clusters` (line 1114)
Currently a nested function. Move to `src/utils.py` as a module-level function — it's reusable and belongs with other math helpers.

### `resolve_roster_candidates()` calls `get_game_context()`
This cross-repo call (photo logic depending on game context) should be handled by passing the pre-fetched context in rather than having `PhotoRepository` call `GameContextRepository`. The caller (confirmed-photos, review-photos, processing-summary) pre-fetches context once and passes it down.

### `face_cluster.py` calls `db.get_all_faces()`, `db.clear_clusters()`, etc.
After the repository split, `face_cluster.py` will call `db.faces.get_all_faces()`, `db.clusters.clear_clusters()`, etc. Update these call sites in step 9 of the migration sequence.

---

## Files That Do NOT Change

| File | Reason |
|------|--------|
| `src/crawler.py` | Standalone, no DB dependency beyond `add_photo` |
| `src/ocr.py` | Standalone |
| `src/face_detector.py` | Standalone |
| `src/face_cluster.py` | DB call sites updated in step 9, but file structure unchanged |
| `src/config.py` | Pure config |
| `src/metadata_sidecar.py` | Pure file I/O |
| `src/roster_import.py` | Pure parsing |
| `src/job_runner.py` | Standalone; only `update_progress()` was added in the critical-fix branch |
| All frontend files (`web/`) | No changes — API URLs are identical |

---

## Definition of Done

- [ ] `src/db.py` ≤ 150 lines (coordinator + schema only, no business logic)
- [ ] `src/api.py` ≤ 80 lines (`create_app()` + CORS + auth hooks only)
- [ ] Each repository file ≤ 250 lines
- [ ] Each blueprint file ≤ 250 lines
- [ ] All 212 existing tests still pass with zero modifications to test assertions
- [ ] Each repository is testable without instantiating Flask
- [ ] `pytest tests/ -q` green on the final commit
