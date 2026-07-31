import { describe, expect, it } from 'vitest';
import { placeLabels, type FaceBox } from '../labelPlacement';

const IMG_W = 576;
const IMG_H = 384;

function overlaps(
  a: { x: number; y: number; width: number; height: number },
  b: { x: number; y: number; width: number; height: number },
): boolean {
  return a.x < b.x + b.width && a.x + a.width > b.x && a.y < b.y + b.height && a.y + a.height > b.y;
}

describe('placeLabels', () => {
  it('places a full-name label for an isolated face, with no pin and no leader line', () => {
    const bboxes: FaceBox[] = [{ id: 1, x: 110, y: 0, width: 31, height: 46 }];
    const names = { 1: 'Axel Olson' };

    const result = placeLabels(bboxes, names, IMG_W, IMG_H);

    expect(result.labels).toHaveLength(1);
    expect(result.labels[0].name).toBe('Axel Olson');
    expect(result.pins).toHaveLength(0);
    expect(result.lines).toHaveLength(0);
  });

  it('never overlaps a label with the face box it belongs to', () => {
    const bboxes: FaceBox[] = [{ id: 1, x: 110, y: 0, width: 31, height: 46 }];
    const names = { 1: 'Axel Olson' };

    const result = placeLabels(bboxes, names, IMG_W, IMG_H);

    expect(overlaps(result.labels[0], bboxes[0])).toBe(false);
  });

  it('an unassigned face gets a numbered pin (no label attempted) so it can still be clicked to assign', () => {
    const bboxes: FaceBox[] = [{ id: 7, x: 110, y: 0, width: 31, height: 46 }];
    const result = placeLabels(bboxes, {}, IMG_W, IMG_H);

    expect(result.labels).toHaveLength(0);
    expect(result.pins).toEqual([{ id: 7, number: 7, x: expect.any(Number), y: expect.any(Number) }]);
  });

  it('degrades a dense cluster to numbered pins with zero overlaps against any face box', () => {
    // 8 faces packed into a tight 2x4 grid (18px column pitch, 24px row
    // pitch — both far narrower than a ~56px-wide name label) with enough
    // frame margin for a 16px pin to route around the cluster, but not
    // enough gap anywhere for a label — every face must fall back to a pin.
    const bboxes: FaceBox[] = [
      { id: 2, x: 10, y: 20, width: 14, height: 20 },
      { id: 3, x: 28, y: 20, width: 14, height: 20 },
      { id: 4, x: 10, y: 44, width: 14, height: 20 },
      { id: 5, x: 28, y: 44, width: 14, height: 20 },
      { id: 6, x: 10, y: 68, width: 14, height: 20 },
      { id: 7, x: 28, y: 68, width: 14, height: 20 },
      { id: 8, x: 10, y: 92, width: 14, height: 20 },
      { id: 9, x: 28, y: 92, width: 14, height: 20 },
    ];
    const names = Object.fromEntries(bboxes.map((b) => [b.id, `Player ${b.id}`]));

    const result = placeLabels(bboxes, names, 50, 140);

    expect(result.pins).toHaveLength(8);
    expect(result.labels).toHaveLength(0);
    for (const pin of result.pins) {
      const pinBox = { x: pin.x - 8, y: pin.y - 8, width: 16, height: 16 };
      for (const face of bboxes) {
        expect(overlaps(pinBox, face)).toBe(false);
      }
    }
  });

  it('gives a pin a leader line when it is not clearly closer to its own face than a neighbour\'s', () => {
    // Same tight-pitch construction, a single packed row.
    const bboxes: FaceBox[] = [
      { id: 2, x: 10, y: 20, width: 14, height: 20 },
      { id: 3, x: 28, y: 20, width: 14, height: 20 },
      { id: 4, x: 46, y: 20, width: 14, height: 20 },
    ];
    const names = Object.fromEntries(bboxes.map((b) => [b.id, `Player ${b.id}`]));

    const result = placeLabels(bboxes, names, 50, 60);

    expect(result.pins.length).toBeGreaterThan(0);
    expect(result.lines.length).toBeGreaterThan(0);
    for (const line of result.lines) {
      expect(bboxes.some((b) => b.id === line.fromId)).toBe(true);
    }
    for (const pin of result.pins) {
      const pinBox = { x: pin.x - 8, y: pin.y - 8, width: 16, height: 16 };
      for (const face of bboxes) {
        expect(overlaps(pinBox, face)).toBe(false);
      }
    }
  });

  it('never positions a label or pin outside the image bounds', () => {
    // Face pinned right at the top-left corner of the frame.
    const bboxes: FaceBox[] = [{ id: 1, x: 0, y: 0, width: 20, height: 28 }];
    const names = { 1: 'Corner Player' };

    const result = placeLabels(bboxes, names, IMG_W, IMG_H);

    for (const label of result.labels) {
      expect(label.x).toBeGreaterThanOrEqual(0);
      expect(label.y).toBeGreaterThanOrEqual(0);
      expect(label.x + label.width).toBeLessThanOrEqual(IMG_W);
    }
    for (const pin of result.pins) {
      expect(pin.x).toBeGreaterThanOrEqual(0);
      expect(pin.y).toBeGreaterThanOrEqual(0);
    }
  });

  it('two well-separated assigned faces both get labels with no leader lines', () => {
    const bboxes: FaceBox[] = [
      { id: 1, x: 20, y: 20, width: 24, height: 32 },
      { id: 2, x: 500, y: 300, width: 24, height: 32 },
    ];
    const names = { 1: 'Axel Olson', 2: 'Sam Elliott' };

    const result = placeLabels(bboxes, names, IMG_W, IMG_H);

    expect(result.labels).toHaveLength(2);
    expect(result.lines).toHaveLength(0);
  });
});
