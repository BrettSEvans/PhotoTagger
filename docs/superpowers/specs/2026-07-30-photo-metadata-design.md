# Photo Metadata & Adaptive Labeling Design

**Date:** 2026-07-30  
**Scope:** Features #1–#4 for PhotoTagger photo-viewing experience

## 1. Overview

Four interconnected features enable full-screen photo viewing with embedded player identification:

1. **Feature #1** — Click a photo to open full-size lightbox with a right-side metadata panel displaying image properties, game data, and identified faces
2. **Feature #2** — Embed player names into photo IPTC metadata (`XMP-iptcExt:PersonInImage`) when faces are assigned to roster players; remove on unassign
3. **Feature #3** — Display player names on full-size photos using adaptive label placement (full names where space permits, numbered pins with leader lines in crowds)
4. **Feature #4** — Toggle buttons to show/hide names and bounding boxes on the photo

All features persist data to embedded JPEG IPTC metadata via `exiftool`, with a one-time backup of the `uploads/` directory before any writes.

## 2. Architecture

### 2.1 Backend Changes

**New module: `src/photo_metadata.py`**
- Reads and returns *only populated* metadata fields for a single photo
- Returns dict with these keys if present:
  - `exif` — empty dict (all photos are web derivatives with zero EXIF)
  - `image` — `dimensions`, `size`, `format`, `mode`
  - `library` — `ingested` (ISO 8601), `batch`
  - `jersey_ocr` — `detected_numbers`, `confidence` (if any detected)
  - `game` — `team_a`, `team_b`, `year`, `tournament` (batch-level metadata)
  - `people` — `[{id, name, cluster_id, assigned}, ...]` (faces detected in photo, with names where assigned)
- Never includes a key whose value would be null, empty list, or empty dict
- Callable from endpoint and frontend; no side effects

**New module: `src/iptc_writer.py`**
- Wraps `exiftool` subprocess to embed/remove IPTC metadata in JPEG files
- Single entry point: `write_iptc(filepath, names_to_add=[], names_to_remove=[])`
- Names are plain strings; stored as `XMP-iptcExt:PersonInImage` (repeating field)
- Writes to temp file, atomically replaces original (no truncation on failure)
- Raises `IptcWriteError` if exiftool missing, file unreadable, or write fails
- Method `backup_directory(source_dir, dest_dir)` copies all JPEGs to backup location before first write in a session

**New endpoint: `GET /api/photos/<id>/metadata`**
- Returns result of `photo_metadata.read(id)`
- HTTP 200 with sparse dict; HTTP 404 if photo not found

**Existing endpoint: `PUT /api/batches/<id>/game`**
- Accept JSON body: `{team_a: str, team_b: str, year: int, tournament: str}`
- Update batch record in database
- Return updated batch (including new metadata)
- Idempotent; all fields optional

**Modified endpoint: `PUT /api/photos/<id>/assign-face`**
- On success, call `iptc_writer.write_iptc(photo.filepath, names_to_add=[player_name])`
- Return response same as before; catch and log `IptcWriteError`, do not fail the request

**Modified endpoint: `PUT /api/photos/<id>/unassign-face`**
- On success, call `iptc_writer.write_iptc(photo.filepath, names_to_remove=[player_name])`
- Return response same as before; catch and log `IptcWriteError`, do not fail the request

### 2.2 Frontend Changes

**New module: `web/src/utils/labelPlacement.ts`**
- Pure function: `placePlaceholders(bboxes, names, imageWidth, imageHeight) → {labels, pins, lines}`
- Input:
  - `bboxes` — `[{id, x, y, width, height}, ...]` (face detection boxes)
  - `names` — `{id: "Player Name", ...}` (cluster_id → assigned player name)
  - `imageWidth`, `imageHeight` — viewport dimensions in image space
- Output:
  - `labels` — `[{id, name, x, y, width, height}, ...]` (positioned text labels, full names)
  - `pins` — `[{id, number, x, y}, ...]` (numbered circles, cluster IDs only)
  - `lines` — `[{from_id, to_x, to_y}, ...]` (leader lines from face center to pin)
- Algorithm:
  1. For each face: try to place full-name label in nearest cardinal position (below → above → right → left) that overlaps no face box and no placed label. Accept if found.
  2. Else: emit numbered pin in nearest open space beside (not on) the face. Compute 16 candidate positions around perimeter; choose first unoccupied.
  3. For each pin: emit leader line if the pin is not clearly closer to its own face than any neighbour's (distance from pin to own face < distance to nearest other face by < 8 px).
  4. Never place any label or pin on a face; prioritize proximity over centering.

**New module: `web/src/components/MetadataPanel.tsx`**
- Right-side panel for lightbox, 300px wide, scrollable
- Sections (omitted if empty):
  - **Toggles** (always present) — two buttons: "Names" / "Boxes", toggle `showNames` and `showBoxes` state
  - **File** — filename only
  - **Image** — dimensions, size, format
  - **EXIF** — omitted (all photos are derivatives with zero EXIF)
  - **Library** — ingested date, batch name
  - **Jersey/OCR** — detected numbers and confidence
  - **Game** — team A, team B, year, tournament; if any missing, show "\+ Add teams & tournament" button with reminder text
  - **People** — "X of Y identified"; list all faces as rows: pin number, name or "Unassigned", "Assign" link; on hover, highlight corresponding pin on photo
- All text and styling pulled from mockup (metadata-panel.html in brainstorm)

**Rewrite: `web/src/components/PhotoLightbox.tsx`**
- Full-screen modal, two-column layout: image left, metadata panel right
- Left pane: image + SVG overlay
  - Display face detection bboxes (purple `#9333EA` or orange `#FF6600` on low contrast)
  - Display labels, pins, lines from solver
  - Hide labels/pins/lines if `showNames` is false; always show bboxes (controlled separately by `showBoxes`)
- Right pane: `MetadataPanel` component
- On assign/unassign via panel, call endpoint, refresh metadata, recompute placement
- Close on Escape or click outside
- Responsive: stack to single column on mobile (`max-width: 860px`)

**Updated: `web/src/pages/PlayersPage.tsx`**
- Add lightbox to photo grid (currently no full-size view exists)
- Clicking a photo opens lightbox at that photo's metadata

### 2.3 Data Model — No Schema Changes

All metadata and IPTC data are read-only to the frontend (sourced from photos and batch records). No new database tables. The `photos.exif_data` column (currently unused) is not touched.

## 3. Metadata Scope

**What appears in feature #1's metadata panel:**

| Section | Fields | Source | Notes |
|---------|--------|--------|-------|
| File | filename | photo record | Basename only |
| Image | dimensions, size, format, mode | Pillow inspection | size in KB, format "JPEG · RGB" |
| EXIF | (none) | (omitted) | All photos are web derivatives, zero EXIF |
| Jersey/OCR | detected_numbers, confidence | ocr_results table | Omitted if no detections |
| Library | ingested, batch | photo record | ISO 8601 date; batch name from upload |
| Game | team_a, team_b, year, tournament | batch record | Batch-level; reminder if missing |
| People | cluster_id, name (if assigned), assign link | clusters + assignments | "X of Y identified" header |

**What goes into IPTC metadata (feature #2):**

- Key: `XMP-iptcExt:PersonInImage`
- Value: repeating field (one entry per assigned player name)
- Written on assign, removed on unassign
- Embedded in JPEG via exiftool (no XMP sidecar)
- Backup: first write creates `uploads_backup/` copy of all originals

## 4. Label Placement Algorithm (Feature #3)

### 4.1 Pseudocode

```
function placePlaceholders(bboxes, names, width, height):
  labels = []
  pins = []
  lines = []
  occupied = bboxes.copy()  # Regions to avoid

  for bbox in bboxes:
    if bbox.id not in names:
      continue  # Face not yet assigned

    name = names[bbox.id]

    # Try cardinal positions for full-name label
    for direction in [BELOW, ABOVE, RIGHT, LEFT]:
      pos = cardinal_position(bbox, name, direction, width, height)
      if not overlaps_any(pos, occupied) and not overlaps_any(pos, labels):
        labels.append({id: bbox.id, name, x: pos.x, y: pos.y, ...})
        occupied.append(pos)
        continue NEXT_BBOX

    # No label fit; fall back to numbered pin
    pin_pos = nearest_open_space_beside_face(bbox, occupied, width, height)
    pins.append({id: bbox.id, number: bbox.id, x: pin_pos.x, y: pin_pos.y})

    # Add leader line if ambiguous
    distance_to_own_face = distance(pin_pos, bbox.center)
    distance_to_nearest_other = min(
      distance(pin_pos, other_bbox.center)
      for other_bbox in bboxes if other_bbox.id != bbox.id
    )
    if distance_to_nearest_other - distance_to_own_face < 8:
      lines.append({from_id: bbox.id, to_x: pin_pos.x, to_y: pin_pos.y})

  return {labels, pins, lines}
```

### 4.2 Rules

1. **Try full-name label** — positions tried in order: below, above, right, left. Accept first that clears all face boxes and all placed labels.
2. **Fall back to numbered pin** — placed in nearest unoccupied space beside the face (16 candidate positions around perimeter at 12 px distance).
3. **Leader line on ambiguity** — draw if pin is not clearly closer to its own face than any neighbour's (delta < 8 px). Purple `#9333EA`, 1.1 px stroke, 0.8 opacity.
4. **Never cover a face** — both labels and pins have hard constraints; never relax this for proximity.
5. **Color** — both use purple `#9333EA`; fallback to orange `#FF6600` on low-contrast backgrounds (existing logic in `PhotoLightbox`).

### 4.3 Edge Cases

- **Single face** — label placed adjacent to face; no leader line.
- **Dense cluster (8+ faces)** — all degrade to numbered pins with leader lines; feature #4 toggle hides all.
- **Face at edge of frame** — label positioned inside frame, or pin placed at nearest in-bounds position.
- **Long player names** — label width grows; collision detection accounts for full bounding box.
- **Hover interactions** — hovering a pin in metadata panel highlights the corresponding pin on photo; hovering a pin on photo reveals full name in tooltip.

## 5. Feature #2 — IPTC Metadata Writing

### 5.1 Backup Strategy

Before the first `write_iptc()` call in a session:
1. Check if `uploads_backup/` exists; skip if so (idempotent)
2. Copy all `.jpg` / `.jpeg` files from `uploads/` to `uploads_backup/` preserving directory structure
3. Total size: ~47 MB for 435 photos
4. Happens once per process; subsequent assigns/unassigns write directly to originals

### 5.2 Write Semantics

- Call `write_iptc(filepath, names_to_add=[], names_to_remove=[])`
- On assign: `names_to_add=[player_name]`
- On unassign: `names_to_remove=[player_name]`
- Reads current metadata, merges changes, writes atomically:
  1. Write to temporary file
  2. Verify temp file integrity (exiftool exit code, file size > 0)
  3. Atomic rename temp → original
  4. Return success
- Any failure raises `IptcWriteError`; caller logs and continues (non-fatal)

### 5.3 Implementation Dependency

- **Requires:** `brew install exiftool` on macOS, or system package on Linux
- **Check:** On first call, verify exiftool present; raise `IptcWriteError("exiftool not found")` if missing
- **User setup:** Installation is user's responsibility; API gracefully skips if missing (features #1, #3, #4 still work)

### 5.4 Supersedes Existing Code

The current `write_assignment_metadata()` in `api.py` writes XMP sidecars (`.xmp` files). This design replaces it entirely:
- Remove `write_assignment_metadata()` call from `PUT /api/photos/<id>/assign-face`
- Remove `write_assignment_metadata()` call from `PUT /api/photos/<id>/unassign-face`
- Remove `write_assignment_metadata()` function from `api.py`
- Remove unused imports

## 6. Feature #4 — Toggle Controls

### 6.1 State

Two independent boolean toggles, persisted to component state (lost on close):
- `showNames` — controls visibility of labels and pins on photo
- `showBoxes` — controls visibility of face detection bounding boxes

### 6.2 UI

Located at top of `MetadataPanel`, two buttons side-by-side:
- Background: `#33333a` when off, `#9333EA` when on
- Text: "Names", "Boxes"
- Dot indicator: filled when on, unfilled when off
- Click toggles respective state; SVG overlay updates immediately

### 6.3 Rendering

In `PhotoLightbox` SVG:
- `showBoxes && <g stroke="#9333EA" ...>` (face bboxes)
- `showNames && <g>` (labels + pins + lines)

## 7. Testing

### 7.1 Label Placement Solver

Unit tests in `web/src/utils/__tests__/labelPlacement.test.ts`:

1. **Isolated face** — single bbox, assigned name
   - Assert: full-name label positioned below face, no pin, no line
2. **Dense cluster** — 8 bboxes touching, all assigned
   - Assert: all degrade to numbered pins; all have leader lines; zero overlaps
3. **Edge of frame** — face within 40 px of boundary
   - Assert: label positioned away from edge; within frame bounds
4. **Ambiguous adjacency** — two faces 25 px apart, one assigned
   - Assert: pin at nearest position; leader line drawn to own face

### 7.2 IPTC Writer

Unit tests in `tests/test_iptc_writer.py`:

1. **Write single name** — copy real JPEG to `tmp_path`, write one name
   - Assert: exiftool reads name back correctly
2. **Add multiple names** — call write twice with different names
   - Assert: both names present; order preserved
3. **Remove name** — write name, then remove it
   - Assert: name absent; other names unchanged
4. **Pixel integrity** — before/after file hash of pixel data
   - Assert: hashes match (no re-encoding)
5. **Atomic failure** — mock exiftool to fail; assert temp file cleaned up
   - Assert: original unchanged

### 7.3 Metadata Reader

Unit tests in `tests/test_photo_metadata.py`:

1. **Sparse output** — photo with only image metadata
   - Assert: dict has only `image` key; no `exif`, `jersey_ocr`, `game`
2. **All sections** — photo with all metadata populated
   - Assert: all relevant keys present; ordering stable
3. **Jersey OCR present** — photo with detected jersey numbers
   - Assert: `jersey_ocr` section present with `detected_numbers` and `confidence`

## 8. Scope & Constraints

### 8.1 Out of Scope

- Editing game metadata on individual photos (batch-level only via feature #1 button)
- Face re-clustering or re-detection
- Bulk assignment (one face at a time)
- Exporting photos with embedded metadata
- Metadata sync to external services

### 8.2 Known Constraints

- All 435 photos are web derivatives (576×384, zero EXIF)
- 184 face clusters, currently all unassigned
- No original files with EXIF exist
- Features #2 and #3 only activate once faces are assigned to players (currently silent on unassigned)

## 9. User Flows

### 9.1 Assigning a Face

1. User clicks a photo in Players view → opens lightbox
2. Metadata panel shows people section with "Unassigned" faces and "Assign" links
3. User clicks "Assign" for a face
4. Assignment dialog shows roster candidates (name, jersey, photo)
5. User selects a player
6. API updates database, embeds name in JPEG via exiftool
7. Lightbox refreshes metadata and label placement
8. Photo now shows player's name instead of numbered pin; name written to IPTC

### 9.2 Setting Game Metadata

1. User opens any photo in the tournament batch
2. Metadata panel shows Game section with "\+ Add teams & tournament" button
3. User clicks button
4. Modal prompts for Team A, Team B, Year, Tournament
5. User submits
6. API updates batch record
7. Metadata panel updates; reminder text disappears
8. Same metadata appears on all other photos in batch

### 9.3 Toggling Labels

1. User opens photo in lightbox
2. Both "Names" and "Boxes" toggles are on (default)
3. User clicks "Names" toggle
4. SVG overlay hides labels, pins, and leader lines; face boxes still visible
5. User clicks "Boxes" toggle
6. SVG overlay hides face detection boxes; names still visible
7. User closes lightbox; toggles reset to default on next photo

## 10. Error Handling

- **exiftool missing** — `IptcWriteError` caught at endpoint, logged, request succeeds (metadata write skipped silently)
- **JPEG corrupt** — exiftool fails; same as above
- **File permissions** — backup fails → request rejected with 500; user fixes and retries
- **Label placement collision** — should never happen; test extensively before launch
- **Metadata endpoint 404** — return HTTP 404 if photo not found

## 11. Success Criteria

✅ User can click a photo and see full-size lightbox with right-side panel  
✅ Metadata panel shows only populated fields (sparse dict)  
✅ Game section shows reminder if team data missing; button opens editor  
✅ People section lists unassigned faces; "Assign" links work  
✅ Assigning a face embeds name in JPEG IPTC and displays on photo  
✅ Labels placed adaptively: full names if space permits, numbered pins in crowds  
✅ Leader lines drawn when adjacent faces are ambiguous  
✅ No labels or pins cover any face  
✅ Names and boxes have independent toggles  
✅ Backup created before first IPTC write; all writes atomic  
✅ All unit tests pass; solver tested against real photo's face boxes
