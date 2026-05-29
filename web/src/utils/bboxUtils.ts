export interface ImgDim { w: number; h: number }

// Returns %-based absolute positioning for a face bbox overlay.
// outset: expand the box outward by this many px so the border sits
// just outside the face region (transparent interior doesn't cover the face).
export function bboxStyle(
  bbox: [number, number, number, number],
  dim: ImgDim,
  outset = 0,
): React.CSSProperties {
  const pctL = (bbox[0] / dim.w) * 100;
  const pctT = (bbox[1] / dim.h) * 100;
  const pctW = ((bbox[2] - bbox[0]) / dim.w) * 100;
  const pctH = ((bbox[3] - bbox[1]) / dim.h) * 100;
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
