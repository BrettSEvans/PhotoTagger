# PhotoTagger Web UI

React 19 + TypeScript frontend for PhotoTagger tournament photo discovery system. Discover all photos of tournament players by jersey number and AI-powered face recognition.

## Quick Start

```bash
cd web
npm install
npm run dev
```

Opens at **http://localhost:3000** (requires backend at http://127.0.0.1:5001)

## Development

```bash
npm run dev       # Start dev server with live reload
npm run build     # Production build
npm run lint      # Type check
npm run preview   # Preview production build locally
```

## Architecture

- **Vite 5** — Fast build tool with HMR
- **React 19** — UI framework
- **TypeScript** — Type safety
- **Tailwind CSS 3.4** — Utility-first styling
- **Axios** — HTTP client for API calls
- **PostCSS + Autoprefixer** — CSS processing

## Three-Screen Interface

### 1. **Roster Setup**
Build a roster of players with jersey numbers. Import from CSV or manually add entries for easy lookup during photo processing.

- Add/edit player roster
- Search and import roster data
- Jersey number to player mapping

### 2. **Upload & Process**
Import tournament photos and run AI processing pipeline (face detection, clustering).

- Crawl photos from local directory
- Run face detection on all photos
- Cluster detected faces into player groups
- Monitor processing progress

### 3. **Cleanup Workspace**
Assign detected face clusters to roster entries. Review and refine AI groupings, then persist assignments.

- Browse detected face clusters
- Assign clusters to players
- Highlight the AI-identified face in each cluster (purple border)
- Manage bulk selections for assignments
- Hover-zoom lens for detailed inspection
- Full-size modal view for precision review

## Key Features

- **Face Detection** — Detects all faces in photos using InsightFace
- **Face Clustering** — Groups similar faces into probable player identities
- **Jersey Recognition** — Extracts jersey numbers via OCR
- **Batch Assignment** — Assign multiple photos at once to roster entries
- **Live Preview** — See confidence scores and face boundaries in real time
- **Responsive Design** — Works on desktop browsers with touch-friendly UI

## API Integration

Frontend communicates with Flask backend at `http://127.0.0.1:5001`:

**Photo Management**
- `POST /api/crawl` — Import photos from directory
- `GET /api/photos` — List all photos (paginated)
- `GET /api/image/<id>` — Fetch full photo

**Face Detection & Clustering**
- `POST /api/detect-faces` — Run face detection on photos
- `GET /api/faces/<photo_id>` — Get all detected faces for a photo
- `GET /api/face-crop/<face_id>` — Get cropped face thumbnail
- `POST /api/cluster-players` — Cluster faces into groups
- `GET /api/players` — List all clusters

**Roster & Assignment**
- `GET /api/roster` — Fetch roster
- `POST /api/roster` — Add roster entry
- `DELETE /api/roster/<id>` — Remove roster entry
- `GET /api/roster/search` — Search roster
- `POST /api/players/<cluster_id>/assign` — Assign cluster to player
- `POST /api/faces/deassign` — Remove faces from assignment

**Info & Status**
- `GET /api/info` — Database statistics
- `GET /api/health` — Health check
- `GET /api/detection-status` — Detection and clustering progress
- `GET /api/processing-summary` — Summary of tagged vs. pending photos
