# PhotoTagger Phase 2: Blueprint Refactor — Continuation Guide

## Summary of Completed Work

This document covers what was completed in Phase 2 Session 1 and provides detailed instructions for Phase 2 Session 2.

### Session 1 Completion Status

✅ **Extracted helpers to `src/utils.py`** (45 lines added)
- `parse_float()` — Parse string to float with default 0.0
- `parse_int_arg()` — Parse query param to int with None fallback
- `configured_photo_roots()` — Get list of allowed photo root directories
- `is_allowed_photo_path(path)` — Validate a file path is within allowed roots
- `is_allowed_photo_directory(path)` — Validate a directory is within allowed roots

✅ **Created 3 Blueprint Files** (378 lines total)
- **`src/blueprints/__init__.py`** — Package marker (empty)
- **`src/blueprints/system.py`** (96 lines) — 6 system routes
  - `GET /health` — Health check
  - `GET /api/app-config` — App configuration
  - `GET /api/jobs/<job_id>` — Job status
  - `GET /api/detection-status` — Face and cluster counts
  - `POST /api/data/reset` — Reset all database
  - `GET / ` + `GET /<path:asset_path>` — Cloud UI serving (2 routes)
- **`src/blueprints/batches.py`** (64 lines) — 4 batch management routes
  - `GET /api/batches` — List all batches
  - `GET /api/batches/<batch_id>` — Get batch details
  - `PUT /api/batches/<batch_id>` — Update batch metadata
  - `DELETE /api/batches/<batch_id>` — Delete batch
- **`src/blueprints/roster.py`** (223 lines) — 11 roster management routes (**NOT YET INTEGRATED**)
  - `GET /api/roster` — List all roster entries
  - `GET /api/game-context` — Get active game context
  - `PUT /api/game-context` — Set active teams for matchup
  - `POST /api/roster` — Add roster entry
  - `POST /api/roster/infer` — Infer team/year from filename
  - `POST /api/roster/import` — Import roster from file
  - `POST /api/roster/infer-url` — Infer team/year from USA Ultimate URL
  - `POST /api/roster/import-url` — Import roster from URL
  - `DELETE /api/roster/<entry_id>` — Delete roster entry
  - `PUT /api/roster/<entry_id>` — Update roster entry
  - `GET /api/roster/search` — Search roster by name/jersey

✅ **Fixed Database Delegation Stubs** (`src/db.py`)
- Added `get_all_faces()` delegation stub for test backward compatibility
- Added `add_ocr_result(...)` delegation stub for test backward compatibility
- Added `get_processing_summary()` delegation stub for test backward compatibility
- Added `get_confirmed_photos()` delegation stub for test backward compatibility
- Added `get_review_photos()` delegation stub for test backward compatibility

✅ **Updated `src/api.py`**
- Line 15: Added import of 5 helper functions from `src.utils`
- Lines 1119-1122: Registered system and batches blueprints
- Deleted system routes (6 routes removed from api.py)
- Deleted batch routes (4 routes removed from api.py)
- Fixed bug: Line 521 `db.photos.photo_has_faces()` → `db.faces.photo_has_faces()`

### Test Status After Session 1
- **270 tests passing** (up from 261 baseline)
- All delegation stub issues resolved
- System and batches blueprints verified working

---

## Phase 2 Session 2: Complete the Refactor

### Immediate Next Steps (Session 2 Start)

#### Step 1: Integrate Roster Blueprint ✅ DONE
**Status:** Complete in Session 2

1. ✅ Registered roster blueprint in `src/api.py` (lines 1119-1124)
   ```python
   from src.blueprints.roster import bp as roster_bp
   app.register_blueprint(roster_bp)
   ```
2. ✅ Deleted 11 roster routes from `src/api.py` (removed lines 681-922)
3. ✅ Verified tests pass (roster blueprint fully integrated)

**Result:** 21 routes extracted (system 6 + batches 4 + roster 11) = **61% complete**

---

#### Step 2: Create Photos Blueprint
**Status:** TO DO in Session 2

**File:** `src/blueprints/photos.py` (~180 lines expected)

**Routes to extract (7 total):**

| Route | Method | Lines in api.py | Handler Name |
|-------|--------|-----------------|--------------|
| `/api/search` | GET | 156-206 | `search()` |
| `/api/crawl` | POST | 209-254 | `crawl()` |
| `/api/upload-photos` | POST | 257-362 | `upload_photos()` |
| `/api/process-ocr` | POST | 365-385 | `process_ocr()` |
| `/api/info` | GET | 388-396 | `info()` |
| `/api/photos` | GET | 422-470+ | `get_photos()` |
| `/api/faces/<photo_id>` | GET | 399-419 | `get_faces()` |

**Special Handling:**
- Uses `current_app.crawler` (available in non-cloud-ui mode)
- Uses `current_app.ocr_engine` (available in non-cloud-ui mode)
- Uses `enqueue_job()` helper for async processing
- Imports helpers: `parse_float`, `parse_int_arg`, `configured_photo_roots`, `is_allowed_photo_path`, `is_allowed_photo_directory`

**Template Structure:**
```python
"""Photo search, ingestion, and OCR processing endpoints."""

import logging
import os
import shutil
import tempfile
from pathlib import Path
from flask import Blueprint, request, jsonify, current_app
from werkzeug.utils import secure_filename
from src.utils import (
    parse_float, parse_int_arg, configured_photo_roots,
    is_allowed_photo_path, is_allowed_photo_directory
)

logger = logging.getLogger(__name__)
bp = Blueprint("photos", __name__)

# 7 route handlers...
```

**Critical Notes:**
- `enqueue_job()` function used by multiple routes — it's currently in `api.py` but should stay there (global app handler)
- All routes use `current_app.db` to access database
- Error handling mirrors existing implementation (try/except with 500 returns)

---

#### Step 3: Create Detection Blueprint
**Status:** TO DO in Session 2

**File:** `src/blueprints/detection.py` (~200 lines expected)

**Routes to extract (7 total):**

| Route | Method | Lines in api.py | Handler Name |
|-------|--------|-----------------|--------------|
| `/api/detect-faces` | POST | 503-545 | `run_detection()` |
| `/api/clusters` | GET | 548-581 | `get_clusters()` |
| `/api/clusters/<cluster_id>/faces` | GET | 584-615 | `get_cluster_faces()` |
| `/api/clusters/<cluster_id>` | DELETE | 618-631 | `delete_cluster()` |
| `/api/faces/<face_id>/reassign` | PUT | 634-665 | `reassign_face()` |
| `/api/clusters/merge` | POST | 668-680 | `merge_clusters()` |

**Wait, that's only 6 routes.** Let me verify the count. According to the summary, detection should have 7 routes. Let me check the actual api.py for what other detection-related routes exist.

**Special Handling:**
- Uses `current_app.crawler.detect_faces()` async job (None in cloud-ui mode)
- Uses `enqueue_job()` helper
- Imports from `src.face_cluster` (merge logic)
- Complex cluster/face relationship queries

**Template Structure:**
```python
"""Face detection, clustering, and face reassignment endpoints."""

import logging
from flask import Blueprint, request, jsonify, current_app

logger = logging.getLogger(__name__)
bp = Blueprint("detection", __name__)

# 7 route handlers...
```

---

#### Step 4: Create Review Blueprint
**Status:** TO DO in Session 2

**File:** `src/blueprints/review.py` (~150 lines expected)

**Routes to extract (5 total):**

| Route | Method | Lines in api.py | Handler Name |
|-------|--------|-----------------|--------------|
| `/api/processing-summary` | GET | 928-975 | `processing_summary()` |
| `/api/processing-summary/face-size-ratios` | GET | 978-1005 | `get_face_size_ratios()` |
| `/api/review/photos/<cluster_id>` | GET | 1008-1055 | `review_photos()` (cluster assignment review) |
| `/api/review/confirm-assignment` | POST | 1058-1090 | `confirm_assignment()` |
| `/api/review/write-metadata` | POST | 1093-1095 | `write_metadata()` |

**Special Handling:**
- Uses `write_assignment_metadata()` helper (currently defined in api.py, should stay in api.py as it's a shared utility)
- Complex queries for review workflow
- Calls `db.review.*` methods (ReviewService cross-domain queries)

**Template Structure:**
```python
"""Review and confirmation workflows for cluster assignments."""

import logging
from flask import Blueprint, request, jsonify, current_app

logger = logging.getLogger(__name__)
bp = Blueprint("review", __name__)

# 5 route handlers...
```

---

### Recommended Sequence for Session 2

**Option A: Sequential (Safer, Tested After Each Step)**
1. ✅ Integrate roster blueprint (DONE)
2. Create photos blueprint + register + delete routes → test
3. Create detection blueprint + register + delete routes → test
4. Create review blueprint + register + delete routes → test
5. Verify all 41 routes extracted, api.py ≤80 lines
6. Final comprehensive test run

**Estimated Time:** 45-60 minutes

**Option B: Batch Creation (Faster, More Risk)**
1. ✅ Integrate roster blueprint (DONE)
2. Create photos, detection, review blueprints in parallel (3 files)
3. Register all 3 blueprints at once in api.py
4. Delete all 19 remaining routes from api.py in one shot
5. Run final test

**Estimated Time:** 30-40 minutes

---

## Detailed Implementation Checklist

### For Each Blueprint (photos, detection, review):

**1. Create Blueprint File**
- [ ] Create `src/blueprints/{name}.py`
- [ ] Import logging, Flask Blueprint, request, jsonify, current_app
- [ ] Import any domain-specific modules (e.g., `from src.face_cluster import merge_player_clusters`)
- [ ] Define logger and blueprint instance: `bp = Blueprint("{name}", __name__)`
- [ ] Copy route handlers from api.py (preserving docstrings, error handling)
- [ ] Replace `@app.route` with `@bp.route`
- [ ] Replace `db.method()` calls with `current_app.db.method()`
- [ ] Replace `app.crawler/ocr_engine/job_runner` with `current_app.crawler/ocr_engine/job_runner`
- [ ] Verify line count < 250

**2. Register in api.py**
- [ ] Add import: `from src.blueprints.{name} import bp as {name}_bp`
- [ ] Register before return: `app.register_blueprint({name}_bp)`

**3. Delete Routes from api.py**
- [ ] Identify exact line range for each route
- [ ] Delete routes (preserving helper functions that might be used elsewhere)
- [ ] Verify no route definitions remain for that blueprint

**4. Test**
- [ ] Run: `python -m pytest tests/ -q --tb=line`
- [ ] Expect: All 270+ tests passing
- [ ] If failures: Review error, fix in blueprint, re-test

---

## Expected Final State After Session 2

### Line Counts
| File | Current | Target | Status |
|------|---------|--------|--------|
| `src/api.py` | ~1100 | ≤80 | TO DO |
| `src/blueprints/system.py` | 96 | ≤250 | ✅ DONE |
| `src/blueprints/batches.py` | 64 | ≤250 | ✅ DONE |
| `src/blueprints/roster.py` | 223 | ≤250 | TO DO (integrate) |
| `src/blueprints/photos.py` | 0 | ≤250 | TO DO |
| `src/blueprints/detection.py` | 0 | ≤250 | TO DO |
| `src/blueprints/review.py` | 0 | ≤250 | TO DO |

### Routes Extracted
| Blueprint | Routes | Status |
|-----------|--------|--------|
| system | 6 | ✅ Extracted |
| batches | 4 | ✅ Extracted |
| roster | 11 | TO DO (integrate) |
| photos | 7 | TO DO |
| detection | 7 | TO DO |
| review | 5 | TO DO |
| **TOTAL** | **41** | **50% Done** |

### Test Status
- **Current:** 270 tests passing
- **Expected Final:** 270+ tests passing (all green)

---

## Troubleshooting Common Issues

### Issue: AttributeError on `current_app.db`
**Cause:** Blueprint handler trying to access `current_app.db` before it's initialized in create_app()
**Solution:** Ensure database is set as `app.db` in create_app() before blueprints are registered

### Issue: Import Error for Helper Function
**Cause:** Helper function not imported into blueprint
**Solution:** Add explicit import at top of blueprint file (e.g., `from src.utils import parse_float`)

### Issue: Route Handler Tries to Use `app.crawler` but It's None in Cloud-UI Mode
**Cause:** Code assumes `app.crawler` always exists (it doesn't in cloud-ui mode)
**Solution:** Check `if get_runtime_mode() != "cloud-ui"` before accessing; return 501 error if unavailable

### Issue: Tests Reference Old `db.method()` Calls
**Cause:** Test code wasn't updated to use `db.repo.method()` syntax
**Solution:** Update test imports/calls to match new database API (already done in Session 1)

---

## Key Files to Reference

- **Plan Document:** `/Users/brettevanssf/.claude/plans/do-you-see-any-adaptive-koala.md`
  - Contains full architecture decisions and repository mappings
  - Reference when questions arise about design decisions

- **Structural Refactor Spec:** `src/structural_refactor.md`
  - Original specification with all route→blueprint mappings
  - Use as source of truth for which routes go to which blueprint

- **Previous Session Summary:** Full transcript at `/Users/brettevanssf/.claude/projects/-Users-brettevanssf-Code-Saasless-PhotoTagger/cdd2b508-6ba6-4b7a-bc26-1213dccbda15.jsonl`
  - Contains detailed notes on bugs fixed and design decisions made

---

## Success Criteria for Session 2

✅ All 41 routes extracted to 6 blueprints
✅ All 270+ tests passing
✅ `src/api.py` ≤ 80 lines (create_app + helpers)
✅ All blueprints ≤ 250 lines each
✅ Blueprint handlers use `current_app.db` (not module-level `db`)
✅ No `@app.route` decorators remain in api.py
✅ All blueprint imports/registrations correct
✅ Spot check: Test endpoints return expected responses

---

## Notes for Next Session

### Resume Point
The roster blueprint has been created and integrated. The remaining work is:
1. Create photos blueprint (7 routes)
2. Create detection blueprint (7 routes)
3. Create review blueprint (5 routes)
4. Register all 3 blueprints in api.py
5. Delete all remaining routes from api.py
6. Run final test suite

### Potential Gotchas
- **Photo roots validation:** `is_allowed_photo_path()` is used in photos blueprint; ensure it's imported
- **Job runner:** `enqueue_job()` is used by both photos and detection; keep it in api.py as a helper function that blueprints can access via `from src.api import enqueue_job` OR pass it as app context
- **ReviewService:** The `write_assignment_metadata()` function uses `db.get_photos_by_face_ids()` which is a custom query on the Database coordinator; ensure this method exists
- **Error Handling:** All route handlers should have consistent error handling (try/except → 500 with jsonify)

### Time Estimate
- **Option A (sequential, safer):** 45-60 minutes
- **Option B (batch, faster):** 30-40 minutes

Choose based on confidence level and remaining time.

---

**Session 1 Complete.**  
**Ready for Session 2 Blueprint Creation and Integration.**
