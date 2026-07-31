// Adaptive label placement solver for the photo lightbox (feature #3).
//
// Rules (docs/superpowers/specs/2026-07-30-photo-metadata-design.md §4):
//   1. Try a full-name label in the nearest position that clears every face
//      box and every already-placed label (below -> above -> right -> left).
//   2. Otherwise drop to a numbered pin in the nearest open space beside the
//      face, never on it.
//   3. Add a leader line whenever a pin isn't clearly closer to its own face
//      than to a neighbour's (ambiguous adjacency).
//   4. Unassigned faces produce neither a label nor a pin.
//
// Pure function: no DOM, no React, no network — safe to call synchronously on
// every render/toggle.

export interface FaceBox {
  id: number;
  x: number;
  y: number;
  width: number;
  height: number;
}

export interface PlacedLabel {
  id: number;
  name: string;
  x: number;
  y: number;
  width: number;
  height: number;
}

export interface PlacedPin {
  id: number;
  number: number;
  x: number;
  y: number;
}

export interface LeaderLine {
  fromId: number;
  toX: number;
  toY: number;
}

export interface PlacementResult {
  labels: PlacedLabel[];
  pins: PlacedPin[];
  lines: LeaderLine[];
}

interface Rect {
  x: number;
  y: number;
  width: number;
  height: number;
}

const LABEL_HEIGHT = 13;
const LABEL_CHAR_WIDTH = 6.2; // approx px/char at font-size 9 bold (Inter/Arial)
const LABEL_PADDING = 6;
const GAP = 3; // clearance between a face box and its label/pin
const PIN_RADIUS = 8;
const LEADER_AMBIGUITY_PX = 8;
// Pass 1 (avoid every occupied rect, for visual clarity) gives up after this
// many radius steps and falls back to pass 2. Pass 2 (face-avoidance only,
// the hard invariant) has no fixed step count — see findPinCenter.
const PIN_SEARCH_STEPS_SOFT = 12;
// Cardinal directions first, then diagonals, then finer angles — nearest-looking first.
const PIN_SEARCH_ANGLES_DEG = [270, 90, 0, 180, 315, 225, 45, 135, 300, 240, 60, 120, 330, 210, 30, 150];

function rectsOverlap(a: Rect, b: Rect): boolean {
  return a.x < b.x + b.width && a.x + a.width > b.x && a.y < b.y + b.height && a.y + a.height > b.y;
}

function withinBounds(rect: Rect, imageWidth: number, imageHeight: number): boolean {
  return rect.x >= 0 && rect.y >= 0 && rect.x + rect.width <= imageWidth && rect.y + rect.height <= imageHeight;
}

function labelWidthFor(name: string): number {
  return Math.round(name.length * LABEL_CHAR_WIDTH + LABEL_PADDING);
}

function candidateLabelPositions(face: FaceBox, labelWidth: number, labelHeight: number): Rect[] {
  return [
    { x: face.x, y: face.y + face.height + GAP, width: labelWidth, height: labelHeight }, // below
    { x: face.x, y: face.y - labelHeight - GAP, width: labelWidth, height: labelHeight }, // above
    { x: face.x + face.width + GAP, y: face.y, width: labelWidth, height: labelHeight }, // right
    { x: face.x - labelWidth - GAP, y: face.y, width: labelWidth, height: labelHeight }, // left
  ];
}

function pinRect(center: { x: number; y: number }): Rect {
  return { x: center.x - PIN_RADIUS, y: center.y - PIN_RADIUS, width: PIN_RADIUS * 2, height: PIN_RADIUS * 2 };
}

/**
 * Find a pin center beside `face`, expanding the search radius outward.
 *
 * Pass 1 (bounded, soft): avoids every occupied rect — faces AND
 * already-placed labels/pins — for visual clarity. Gives up after
 * PIN_SEARCH_STEPS_SOFT radius steps if nothing opens up.
 *
 * Pass 2 (unbounded up to the image diagonal, hard): avoids only faces.
 * Face-avoidance is never relaxed — a pin must never sit on a face, even in
 * extreme density — so this pass keeps expanding the radius until it exceeds
 * the image diagonal (at which point every candidate is guaranteed out of
 * bounds and the loop terminates naturally) rather than giving up early.
 */
function findPinCenter(
  face: FaceBox,
  faceRects: Rect[],
  occupied: Rect[],
  imageWidth: number,
  imageHeight: number,
): { x: number; y: number } {
  const cx = face.x + face.width / 2;
  const cy = face.y + face.height / 2;
  const baseRx = face.width / 2 + PIN_RADIUS + GAP;
  const baseRy = face.height / 2 + PIN_RADIUS + GAP;
  const radiusStep = PIN_RADIUS + GAP;
  const maxRadius = Math.hypot(imageWidth, imageHeight) + radiusStep;

  const search = (avoidSet: Rect[], maxSteps: number): { x: number; y: number } | null => {
    for (let step = 0; step < maxSteps; step++) {
      const rx = baseRx + step * radiusStep;
      const ry = baseRy + step * radiusStep;
      if (rx > maxRadius && ry > maxRadius) break;
      for (const deg of PIN_SEARCH_ANGLES_DEG) {
        const rad = (deg * Math.PI) / 180;
        const center = { x: cx + rx * Math.cos(rad), y: cy + ry * Math.sin(rad) };
        const rect = pinRect(center);
        if (!withinBounds(rect, imageWidth, imageHeight)) continue;
        if (avoidSet.some((r) => rectsOverlap(rect, r))) continue;
        return center;
      }
    }
    return null;
  };

  const soft = search(occupied, PIN_SEARCH_STEPS_SOFT);
  if (soft) return soft;

  const hard = search(faceRects, Math.ceil(maxRadius / radiusStep) + 1);
  if (hard) return hard;

  // Truly unreachable: no in-bounds point at any radius clears every face.
  // Only possible if a face itself doesn't fit inside the image bounds.
  // Clamping here can't guarantee face-avoidance, but there is no valid
  // position left to return.
  return {
    x: Math.min(Math.max(cx + baseRx, PIN_RADIUS), imageWidth - PIN_RADIUS),
    y: Math.min(Math.max(cy, PIN_RADIUS), imageHeight - PIN_RADIUS),
  };
}

/**
 * Every face in `bboxes` gets a marker — a full-name label if it has a name
 * in `names` and one fits, otherwise a numbered pin. Faces with no entry in
 * `names` (not yet assigned to a player) also get a numbered pin: the pin's
 * number is what lets a user correlate "which face is #3" with the "Assign"
 * link in the metadata panel's People list before a name exists.
 */
export function placeLabels(
  bboxes: FaceBox[],
  names: Record<number, string>,
  imageWidth: number,
  imageHeight: number,
): PlacementResult {
  const labels: PlacedLabel[] = [];
  const pins: PlacedPin[] = [];
  const lines: LeaderLine[] = [];

  const faceRects: Rect[] = bboxes.map((b) => ({ x: b.x, y: b.y, width: b.width, height: b.height }));
  const occupied: Rect[] = [...faceRects];

  for (const face of bboxes) {
    const name = names[face.id];
    let placed = false;

    if (name !== undefined) {
      const labelWidth = labelWidthFor(name);
      for (const candidate of candidateLabelPositions(face, labelWidth, LABEL_HEIGHT)) {
        if (!withinBounds(candidate, imageWidth, imageHeight)) continue;
        if (occupied.some((r) => rectsOverlap(candidate, r))) continue;
        labels.push({ id: face.id, name, x: candidate.x, y: candidate.y, width: candidate.width, height: candidate.height });
        occupied.push(candidate);
        placed = true;
        break;
      }
    }

    if (placed) continue;

    const pinCenter = findPinCenter(face, faceRects, occupied, imageWidth, imageHeight);
    occupied.push(pinRect(pinCenter));
    pins.push({ id: face.id, number: face.id, x: pinCenter.x, y: pinCenter.y });
  }

  for (const pin of pins) {
    const ownFace = bboxes.find((f) => f.id === pin.id)!;
    const ownCenter = { x: ownFace.x + ownFace.width / 2, y: ownFace.y + ownFace.height / 2 };
    const ownDist = Math.hypot(pin.x - ownCenter.x, pin.y - ownCenter.y);

    let nearestOtherDist = Infinity;
    for (const other of bboxes) {
      if (other.id === pin.id) continue;
      const otherCenter = { x: other.x + other.width / 2, y: other.y + other.height / 2 };
      const d = Math.hypot(pin.x - otherCenter.x, pin.y - otherCenter.y);
      if (d < nearestOtherDist) nearestOtherDist = d;
    }

    if (bboxes.length > 1 && nearestOtherDist - ownDist < LEADER_AMBIGUITY_PX) {
      lines.push({ fromId: pin.id, toX: ownCenter.x, toY: ownCenter.y });
    }
  }

  return { labels, pins, lines };
}
