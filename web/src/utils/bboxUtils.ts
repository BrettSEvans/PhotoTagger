export interface ImgDim { w: number; h: number }

export interface BackgroundColorAnalysis {
  isLowContrast: boolean;
  isPurplish: boolean;
}

// Returns %-based absolute positioning for a face bbox overlay.
// The image is displayed with object-cover in a square container.
// bbox coordinates are in natural image pixels [x0, y0, x1, y1].
// outset: expand the box outward by this many px.
export function bboxStyle(
  bbox: [number, number, number, number],
  dim: ImgDim,
  outset = 0,
): React.CSSProperties {
  // With object-cover in a square container (100x100 displayed):
  // If image is landscape (w > h): scaled by height, cropped from sides
  //   visible portion: from x = (w - h)/2 to x = (w+h)/2 (in natural coords)
  // If image is portrait (h > w): scaled by width, cropped from top/bottom
  //   visible portion: from y = (h - w)/2 to y = (h+w)/2 (in natural coords)

  const isLandscape = dim.w > dim.h;

  let visibleL = 0;
  let visibleT = 0;
  let visibleW = dim.w;
  let visibleH = dim.h;

  if (isLandscape) {
    // Image wider than tall: crop from sides
    const croppedAmount = (dim.w - dim.h) / 2;
    visibleL = croppedAmount;
    visibleW = dim.h;
  } else {
    // Image taller than wide: crop from top/bottom
    const croppedAmount = (dim.h - dim.w) / 2;
    visibleT = croppedAmount;
    visibleH = dim.w;
  }

  // Convert bbox coordinates to visible portion coordinates
  const x0 = Math.max(0, bbox[0] - visibleL);
  const y0 = Math.max(0, bbox[1] - visibleT);
  const x1 = Math.min(visibleW, bbox[2] - visibleL);
  const y1 = Math.min(visibleH, bbox[3] - visibleT);

  // Convert to percentages of visible area
  const pctL = (x0 / visibleW) * 100;
  const pctT = (y0 / visibleH) * 100;
  const pctW = ((x1 - x0) / visibleW) * 100;
  const pctH = ((y1 - y0) / visibleH) * 100;

  if (outset === 0) {
    return { left: `${pctL}%`, top: `${pctT}%`, width: `${pctW}%`, height: `${pctH}%` };
  }
  return {
    left:   `calc(${pctL}% - ${outset}px)`,
    top:    `calc(${pctT}% - ${outset}px)`,
    width:  `calc(${pctW}% + ${outset * 2}px)`,
    height: `calc(${pctH}% + ${outset * 2}px)`,
  };
}

/**
 * Analyze background color around a bounding box to determine if bbox should be
 * rendered in purple (good contrast) or fluorescent orange (low contrast/purplish background).
 *
 * @param imageElement HTML img element (must be loaded)
 * @param bbox Bounding box [x0, y0, x1, y1] in image coordinates
 * @returns { isLowContrast, isPurplish } flags for determining bbox color
 */
export function analyzeBackgroundColor(
  imageElement: HTMLImageElement,
  bbox: [number, number, number, number],
): BackgroundColorAnalysis {
  try {
    if (!imageElement || !imageElement.src) {
      return { isLowContrast: false, isPurplish: false };
    }

    // Create a canvas and draw the image
    const canvas = document.createElement('canvas');
    canvas.width = imageElement.naturalWidth;
    canvas.height = imageElement.naturalHeight;
    const ctx = canvas.getContext('2d');
    if (!ctx) return { isLowContrast: false, isPurplish: false };

    ctx.drawImage(imageElement, 0, 0);

    // Sample background pixels around the bbox (margins)
    const [x0, y0, x1, y1] = bbox;
    const width = x1 - x0;
    const height = y1 - y0;
    const margin = Math.max(width, height) * 0.15; // 15% margin around bbox

    const sampleRegions = [
      { x: x0 - margin, y: y0 - margin, w: width + margin * 2, h: margin }, // top
      { x: x0 - margin, y: y1, w: width + margin * 2, h: margin }, // bottom
      { x: x0 - margin, y: y0, w: margin, h: height }, // left
      { x: x1, y: y0, w: margin, h: height }, // right
    ];

    const pixels: Array<{ r: number; g: number; b: number }> = [];

    for (const region of sampleRegions) {
      const clampedX = Math.max(0, Math.min(region.x, canvas.width - 1));
      const clampedY = Math.max(0, Math.min(region.y, canvas.height - 1));
      const clampedW = Math.min(region.w, canvas.width - clampedX);
      const clampedH = Math.min(region.h, canvas.height - clampedY);

      if (clampedW <= 0 || clampedH <= 0) continue;

      const imageData = ctx.getImageData(clampedX, clampedY, clampedW, clampedH);
      const data = imageData.data;

      // Sample every 4th pixel for efficiency
      for (let i = 0; i < data.length; i += 16) {
        pixels.push({ r: data[i], g: data[i + 1], b: data[i + 2] });
      }
    }

    if (pixels.length === 0) {
      return { isLowContrast: false, isPurplish: false };
    }

    // Calculate average RGB
    const avgR = pixels.reduce((sum, p) => sum + p.r, 0) / pixels.length;
    const avgG = pixels.reduce((sum, p) => sum + p.g, 0) / pixels.length;
    const avgB = pixels.reduce((sum, p) => sum + p.b, 0) / pixels.length;

    // Convert RGB to HSL
    const r = avgR / 255;
    const g = avgG / 255;
    const b = avgB / 255;

    const max = Math.max(r, g, b);
    const min = Math.min(r, g, b);
    const l = (max + min) / 2;

    let h = 0;
    if (max !== min) {
      const d = max - min;
      const s = l > 0.5 ? d / (2 - max - min) : d / (max + min);

      switch (max) {
        case r:
          h = ((g - b) / d + (g < b ? 6 : 0)) / 6;
          break;
        case g:
          h = ((b - r) / d + 2) / 6;
          break;
        case b:
          h = ((r - g) / d + 4) / 6;
          break;
      }
    }

    const hDegrees = h * 360;

    // Check for low contrast (lightness < 50%)
    const isLowContrast = l < 0.5;

    // Check for purplish hue (240° to 300°)
    const isPurplish = hDegrees >= 240 && hDegrees <= 300;

    return { isLowContrast, isPurplish };
  } catch (err) {
    console.warn('Error analyzing background color:', err);
    return { isLowContrast: false, isPurplish: false };
  }
}
