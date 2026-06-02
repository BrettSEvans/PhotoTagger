# PhotoTagger Test Coverage & Recommendations

**Last Updated:** June 1, 2026  
**Phase:** 2 (Blueprint Refactoring)  
**Status:** ✅ 272/272 Tests Passing

---

## Current Test Coverage Summary

### Test Statistics
- **Total Test Files:** 28
- **Total Test Functions:** 272
- **Pass Rate:** 100%
- **Regressions:** 0
- **Average Test Execution:** ~2 minutes

### Test Organization by Module

| Module | Test File | Tests | Status | Coverage Focus |
|--------|-----------|-------|--------|-----------------|
| API Routes | `test_api.py` | 54 | ✅ | System routes, search, crawl, upload |
| API Routes (Phase 2) | `test_api_phase2.py` | 35 | ✅ | Assignment, metadata, face operations |
| Jobs/Async | `test_jobs.py` | 21 | ✅ | Job queuing, async execution, status |
| Crawler | `test_crawler.py` | 18 | ✅ | Photo ingestion, batch processing |
| OCR | `test_ocr.py` | 12 | ✅ | Jersey detection, confidence handling |
| Database | `test_db.py` | 22 | ✅ | Schema, queries, relationships |
| Roster | `test_roster.py` | 8 | ✅ | Roster operations, game context |
| Validation | `test_validation.py` | 10 | ✅ | Input validation, parameter parsing |
| Face Detection | `test_face_detector.py` | 8 | ✅ | Face detection, bounding boxes |
| Face Clustering | `test_face_cluster.py` | 18 | ✅ | Clustering algorithms, similarity |
| Others | 18 files | 66 | ✅ | Schema, imports, roster, security |

---

## Blueprint Test Coverage (Post-Phase 2)

### System Blueprint
**File:** `src/blueprints/system.py` (7 routes)
- ✅ Health check endpoint tested
- ✅ App config endpoint tested
- ✅ Job status retrieval tested
- ✅ Detection status tested
- ⚠️ **Gap:** Data reset endpoint tested but could use more destructive scenario testing

### Batches Blueprint
**File:** `src/blueprints/batches.py` (4 routes)
- ✅ List batches endpoint tested
- ✅ Get batch details tested
- ✅ Update batch metadata tested
- ⚠️ **Gap:** Delete batch cascade effects not thoroughly tested

### Roster Blueprint
**File:** `src/blueprints/roster.py` (11 routes)
- ✅ All CRUD operations tested
- ✅ Game context management tested
- ✅ Roster import (file & URL) tested
- ✅ Roster inference tested
- ⚠️ **Gap:** Concurrent import handling not tested
- ⚠️ **Gap:** Large roster (1000+) performance not tested

### Photos Blueprint
**File:** `src/blueprints/photos.py` (8 routes)
- ✅ Search endpoint tested
- ✅ Crawl endpoint tested
- ✅ Upload photos endpoint tested
- ✅ Process OCR endpoint tested
- ✅ Get photos list tested
- ⚠️ **Gap:** Concurrent uploads (10+) not tested
- ⚠️ **Gap:** Very large photo batch (500+) not tested
- ⚠️ **Gap:** Error recovery during partial uploads not tested

### Detection Blueprint
**File:** `src/blueprints/detection.py` (5 routes)
- ✅ Face detection endpoint tested
- ✅ Cluster players endpoint tested
- ✅ Get players tested
- ✅ Get player photos tested
- ✅ Face crop endpoint tested
- ⚠️ **Gap:** Cluster merge with conflicts not tested
- ⚠️ **Gap:** Large cluster (1000+ faces) performance not tested

### Review Blueprint
**File:** `src/blueprints/review.py` (6 routes)
- ✅ Processing summary tested
- ✅ Confirmed photos tested
- ✅ Review photos tested
- ✅ Face deassignment tested
- ✅ Cluster assignment tested
- ✅ Match similar tested
- ✅ XMP metadata writing tested
- ⚠️ **Gap:** Partial metadata write failures not tested
- ⚠️ **Gap:** Concurrent assignments to same cluster not tested

---

## Recommended Additional Tests

### High Priority (Add Within 2 Sprints)

1. **Concurrency Tests** (Blueprint Integration)
   - Concurrent photo uploads while crawling
   - Concurrent cluster assignments
   - Race condition handling in job queue
   - Expected: 8-12 new tests

2. **Performance Tests** (Blueprint Integration)
   - 500+ photo ingestion
   - 1000+ face clustering
   - Large roster import (5000+ rows)
   - Expected: 4-6 new tests

3. **Error Recovery Tests** (Blueprint Integration)
   - Partial upload failures and cleanup
   - Job cancellation and state recovery
   - XMP write failures and rollback
   - Database connection loss handling
   - Expected: 6-8 new tests

4. **Blueprint Integration Tests** (Cross-blueprint)
   - Photos → Detection → Review workflow
   - Roster changes affecting assignments
   - Batch operations across all blueprints
   - Expected: 5-7 new tests

### Medium Priority (Add Within 3-4 Sprints)

5. **Edge Case Tests**
   - Empty database operations
   - Malformed file uploads
   - Unicode/special character handling in names
   - Extremely large bounding boxes
   - Expected: 8-10 new tests

6. **Security Tests** (Enhancement)
   - Unauthorized access attempts per blueprint
   - SQL injection attempts on search/filter endpoints
   - Path traversal in file operations
   - Token validation on protected routes
   - Expected: 6-8 new tests

7. **API Contract Tests**
   - Response schema validation
   - HTTP status code correctness
   - Header validation
   - Content-type verification
   - Expected: 4-6 new tests

### Low Priority (Add Within 5-6 Sprints)

8. **Load Tests**
   - 100+ concurrent photo uploads
   - 1000+ face clustering
   - Simultaneous review operations
   - Expected: 3-4 new tests

9. **Stress Tests**
   - Out-of-memory handling
   - Disk space exhaustion
   - Network timeout recovery
   - Expected: 3-4 new tests

---

## Test Execution Times (Current)

```
Fastest: test_conftest_fixtures.py (0.3s)
Slowest: test_parallel_ocr.py (45s - uses OCR, expected)

Total Suite: ~2 minutes at 100% baseline
  - Phase 1 tests: ~45s
  - Phase 2 tests: ~35s
  - Integration tests: ~40s
```

**Recommendation:** Keep suite under 3 minutes for developer velocity.

---

## Testing Best Practices for Blueprints

### 1. **Test Organization**
- One test file per blueprint (`test_<blueprint>.py`)
- Group related tests in test classes
- Use fixtures for common setup (app, db, test data)

### 2. **Test Pattern**
```python
def test_endpoint_happy_path(client, db_fixture):
    """Test successful operation with valid inputs."""
    # Setup
    response = client.post('/api/endpoint', json={...})
    
    # Assert
    assert response.status_code == 200
    assert response.json['success'] == True
    
def test_endpoint_missing_param_returns_400(client):
    """Test validation error on missing required parameter."""
    response = client.post('/api/endpoint', json={})
    assert response.status_code == 400
```

### 3. **Async Job Testing**
```python
def test_endpoint_enqueues_job(client, db_fixture):
    """Test that async endpoint returns job ID."""
    response = client.post('/api/async-endpoint')
    job_id = response.json['job_id']
    
    # Wait for job
    job = db_fixture.jobs.get_processing_job(job_id)
    assert job['status'] == 'succeeded'
```

### 4. **Database Isolation**
- Use `in-memory:` SQLite for tests (current setup)
- Create fixtures for test data
- Clean up after each test
- Current approach is working well ✅

---

## Coverage Goals for Phase 3+

### Phase 3 (Face Embedding & Web UI)
- Add tests for embedding generation
- Add tests for clustering algorithms
- Add API endpoint tests for new features
- **Goal:** Maintain 100% pass rate, <5% regression

### Phase 3 UI Tests
- Add Playwright/Cypress E2E tests
- Add component tests for React UI
- Add visual regression tests
- **Goal:** 50+ E2E test scenarios

---

## Continuous Improvement

### Metrics to Monitor
- Test pass rate (target: 100%)
- Test execution time (target: <3 minutes)
- Code coverage (target: >85% for new blueprints)
- Regression rate (target: 0%)

### Review Strategy
- Run full test suite before each commit
- Run relevant blueprint tests on each file save
- Run integration tests before PR merge
- Monthly coverage analysis

---

## Summary

✅ **Phase 2 Testing Status:**
- 272 tests passing
- All blueprints have basic coverage
- Zero regressions in refactoring
- Ready for Phase 3 development

⚠️ **Recommended Additions for Production:**
- Concurrency testing (8-12 tests)
- Performance testing (4-6 tests)
- Error recovery testing (6-8 tests)
- Cross-blueprint integration (5-7 tests)

**Estimated effort:** 2-3 sprints to achieve >95% coverage with recommended tests.
