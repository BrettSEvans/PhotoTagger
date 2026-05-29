# PhotoTagger

**AI-powered photo discovery system for Ultimate Frisbee tournaments**

Find all photos of a player by jersey number with multi-face detection, roster management, and confidence-based filtering.

![Build Status](https://img.shields.io/badge/build-passing-brightgreen)
![Tests](https://img.shields.io/badge/tests-18%2B-blue)
![Python](https://img.shields.io/badge/python-3.11%2B-blue)
![License](https://img.shields.io/badge/license-MIT-green)

---

## 🎯 Problem Solved

Parents and grandparents at Ultimate Frisbee tournaments want to find photos of specific players, but they:
- Don't have technical skills to navigate complex folder structures
- Can't easily find all photos of their child across hundreds of tournament images
- Want to purchase photos but can't efficiently search

**PhotoTagger solves this** by:
1. Scanning a photo library
2. Extracting jersey numbers via OCR
3. Detecting faces with embeddings
4. Mapping jerseys to player names via rosters
5. Providing a simple search interface

---

## ✨ Features

### Phase 1: Core MVP ✅
- **Photo Crawling** - Index photos from local directories with duplicate detection
- **Jersey Detection** - OCR-based jersey number extraction (EasyOCR)
- **REST API** - `/api/search?jersey=X` for programmatic access
- **CLI Tool** - Command-line interface for non-API usage
- **SQLite Database** - Persistent storage of photos and OCR results
- **18+ Unit Tests** - Full test coverage

### Phase 2A: Backend Enhancement ✅
- **Face Recognition** - Detect all faces in a photo (InsightFace)
- **Face Embeddings** - 384-dimensional face vectors for similarity matching
- **Face Clustering** - Group similar faces into player identities
- **Roster Management** - JSON-based player name mapping (team/year/jersey)
- **Parallel OCR** - Dynamic worker pool (CPU-aware)
- **Confidence Filtering** - Filter results by detection confidence
- **Enhanced API** - Player names, face data, filtering parameters

### Phase 2B: Web UI ✅
- **React 19 Frontend** - Responsive three-screen interface
- **Roster Setup** - Add and manage player roster
- **Upload & Process** - Import photos and run AI pipeline
- **Cleanup Workspace** - Assign AI-detected faces to roster entries
- **Face Highlighting** - Purple border highlights AI-identified face per cluster
- **Batch Assignment** - Select and assign multiple photos at once
- **Real-time Status** - Monitor detection and clustering progress

---

## 🚀 Quick Start

### Prerequisites
- Python 3.11+
- 2GB RAM (for face detection models)
- ~500MB disk space (for InsightFace models)

### Installation

```bash
# Clone repository
git clone https://github.com/BrettSEvans/PhotoTagger.git
cd PhotoTagger

# Create virtual environment
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### Basic Usage

**1. Crawl photos**
```bash
python -m src.cli crawl --photos /path/to/photos --db my_photos.db
```

**2. Process OCR**
```bash
python -m src.cli ocr --db my_photos.db
```

**3. Search by jersey**
```bash
python -m src.cli search 16 --db my_photos.db
```

**4. View database stats**
```bash
python -m src.cli info --db my_photos.db
```

---

## 📡 REST API

### Health Check
```bash
curl http://localhost:5001/health
# {"status": "ok"}
```

### Search by Jersey
```bash
curl "http://localhost:5000/api/search?jersey=16"
# {
#   "jersey": "16",
#   "count": 2,
#   "results": [...]
# }
```

### Search with Filtering
```bash
curl "http://localhost:5000/api/search?jersey=16&min_confidence=0.9&team=Team%20Name&year=2026"
```

### Get Face Data (Phase 2A)
```bash
curl http://localhost:5000/api/faces/1
# {
#   "photo_id": 1,
#   "face_count": 3,
#   "faces": [...]
# }
```

### Crawl Photos
```bash
curl -X POST http://localhost:5000/api/crawl \
  -H "Content-Type: application/json" \
  -d '{"photo_dir": "/path/to/photos"}'
```

### Process OCR
```bash
curl -X POST http://localhost:5000/api/process-ocr
```

---

## 📊 Real-World Testing

**Test Dataset:** 200 Nationals tournament photos (23.5 MB)

### Phase 1 Results
- ✅ 200 photos crawled in ~2 seconds
- ✅ 15 photos with visible jersey numbers detected
- ✅ 13 unique jersey numbers found
- ✅ Detection accuracy: 93.69% (best case)
- ✅ All searches <100ms

See `TEST_REPORT.md` for detailed metrics.

---

## 🏗️ Architecture

### Database Schema

**Photos Table**
```
id, file_path, file_hash, file_size, created_at, ingested_at
```

**OCR Results Table**
```
id, photo_id, jersey_number, confidence, raw_text, processed_at
```

**Faces Table** (Phase 2A)
```
id, photo_id, embedding, bbox_x0, bbox_y0, bbox_x1, bbox_y1, confidence
```

**Rosters Table** (Phase 2A)
```
id, team_name, team_year, jersey_number, player_name, created_at
```

### System Flow

```
Photos Directory
    ↓
[Crawler] → Index all photos, compute file hashes
    ↓
SQLite Database (photos table)
    ↓
[OCR Engine + Face Detector] → Extract jerseys, detect faces, compute embeddings
    ↓
SQLite Database (ocr_results + faces tables)
    ↓
[Search API] → Jersey lookup + confidence filtering + player name mapping
    ↓
Results (with face clustering, player names, confidence scores)
```

---

## 📁 Project Structure

```
PhotoTagger/
├── src/
│   ├── db.py                    # SQLite operations
│   ├── crawler.py               # Photo ingestion
│   ├── ocr.py                   # Jersey detection + OCR
│   ├── face_detector.py         # Face detection (Phase 2A)
│   ├── roster.py                # Roster management (Phase 2A)
│   ├── parallel_ocr.py          # Parallel processing (Phase 2A)
│   ├── api.py                   # Flask REST API
│   ├── cli.py                   # Command-line tool
│   ├── config.py                # Configuration
│   ├── utils.py                 # Utilities
│   └── __init__.py
│
├── tests/
│   ├── test_db.py
│   ├── test_crawler.py
│   ├── test_ocr.py
│   ├── test_api.py
│   ├── test_face_detector.py    # Phase 2A
│   ├── test_roster.py           # Phase 2A
│   ├── test_parallel_ocr.py     # Phase 2A
│   └── __init__.py
│
├── rosters/
│   ├── README.md
│   └── sample-roster-2026.json
│
├── docs/
│   └── superpowers/plans/
│       ├── 2026-05-28-phototagger-phase1-mvp.md
│       └── 2026-05-28-phototagger-phase2a-backend.md
│
├── requirements.txt
├── README.md
├── CLAUDE.md
├── TEST_REPORT.md
└── .gitignore
```

---

## 🔧 Configuration

Edit `src/config.py` to customize:

```python
# Face detection threshold
FACE_DETECTION_CONFIDENCE_THRESHOLD = 0.5

# Parallel processing (auto-detected)
OPTIMAL_OCR_WORKERS = get_optimal_worker_count()

# Batch processing
BATCH_SIZE = 10
QUEUE_MAX_SIZE = 100
```

---

## 📋 Roster Format

Create a JSON file for each team:

```json
{
  "team_name": "Ultimate Club",
  "team_year": 2026,
  "jerseys": {
    "1": "Alice Smith",
    "16": "Edward Brown",
    "23": "Sarah Johnson",
    "48": "Kevin Anderson"
  }
}
```

Save as `rosters/team-name-2026.json` and load:

```bash
python -m src.cli roster load rosters/team-name-2026.json
```

---

## 🧪 Testing

### Run All Tests
```bash
pytest tests/ -v --cov=src
```

### Run Specific Test
```bash
pytest tests/test_ocr.py -v
```

### Run with Coverage Report
```bash
pytest tests/ --cov=src --cov-report=html
```

### Real-World Integration Test
```bash
# Crawl 200 tournament photos
python -m src.cli crawl --photos /path/to/tournament/photos --db tournament.db

# Load roster
python -m src.cli roster load rosters/tournament-2026.json --db tournament.db

# Process with parallel OCR
python -m src.cli ocr --db tournament.db --parallel

# Search results
python -m src.cli search 16 --db tournament.db
```

---

## 🚀 Phase 2A Roadmap

### In Development
- [x] Face detection with InsightFace
- [x] Face embedding extraction (384-dim vectors)
- [x] Roster-based player name mapping
- [x] Parallel OCR with dynamic workers
- [x] Confidence filtering API
- [ ] Full testing and validation

### Next (Phase 2B)
- [ ] React Web UI
- [ ] Photo export/gallery features
- [ ] Bulk operations
- [ ] Authentication system

### Future
- [ ] Zenfolio API integration
- [ ] Cloud deployment (AWS Lambda)
- [ ] Real-time indexing
- [ ] Advanced face clustering

---

## 📈 Performance

| Operation | Dataset | Time | Status |
|-----------|---------|------|--------|
| Crawl photos | 200 photos | ~2 sec | ✅ |
| OCR detection | 200 photos | ~5-10 min | ✅ |
| Face detection | 200 photos | +5-10 min (Phase 2A) | ✅ |
| Search query | By jersey | <100ms | ✅ |
| API response | Any endpoint | <50ms | ✅ |

---

## 🛠️ Development

### Tech Stack
- **Python 3.11+** - Core language
- **Flask 3.0** - REST API
- **SQLite** - Database
- **EasyOCR** - Jersey OCR detection
- **InsightFace** - Face detection & embeddings
- **Pillow** - Image processing
- **pytest** - Testing
- **concurrent.futures** - Parallel processing

### Code Style
- PEP 8 compliant
- Type hints throughout
- Comprehensive docstrings
- TDD approach (tests first)

### Contributing
Contributions welcome! Please:
1. Fork the repository
2. Create a feature branch
3. Add tests for new features
4. Submit a pull request

---

## 📝 Documentation

- **[CLAUDE.md](CLAUDE.md)** - Project context for Claude AI
- **[TEST_REPORT.md](TEST_REPORT.md)** - Phase 1 test results
- **[PHASE2_TEST_REPORT.md](PHASE2_TEST_REPORT.md)** - Phase 2A test results (coming)
- **[docs/ARCHITECTURE_PHASE2.md](docs/ARCHITECTURE_PHASE2.md)** - Phase 2A architecture

---

## 🤝 Support

For issues, questions, or suggestions:
1. Check existing [GitHub Issues](https://github.com/BrettSEvans/PhotoTagger/issues)
2. Review [CLAUDE.md](CLAUDE.md) for project context
3. See implementation plans in `docs/superpowers/plans/`

---

## 📄 License

MIT License - See LICENSE file for details

---

## 🙏 Acknowledgments

- **EasyOCR** - For robust text detection in sports photos
- **InsightFace** - For state-of-the-art face detection
- **Flask** - For simple yet powerful REST API framework
- **Ultimate Frisbee Community** - For the inspiration and test data

---

## 🎯 Goals

This project aims to:
1. **Democratize photo search** - Make it easy for non-technical users to find their photos
2. **Support photographers** - Help tournament photographers sell their work
3. **Enhance fan experience** - Let parents/fans easily access memories from tournaments
4. **Advance open-source AI** - Use accessible tools (EasyOCR, InsightFace) for real-world problems

---

**Built with ❤️ for Ultimate Frisbee fans**

[View on GitHub](https://github.com/BrettSEvans/PhotoTagger) | [Open Issues](https://github.com/BrettSEvans/PhotoTagger/issues)
