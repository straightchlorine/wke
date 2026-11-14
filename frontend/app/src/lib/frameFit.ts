/** A point and how far its mark must stay clear of each frame edge, in px. */
export interface FitItem {
  x: number;
  y: number;
  left: number;
  right: number;
  top: number;
  bottom: number;
}

export interface FrameFit {
  /** The one factor applied to both axes. */
  scale: number;
  /** Offset added after scaling, per axis. */
  tx: number;
  ty: number;
}

/** Largest enlargement a fit may apply, so a small layout is not blown up past its own spacing. */
const MAX_SCALE = 2;
/** How many times the search for the largest scale halves its range. */
const SEARCH_STEPS = 40;

/** Returns the low and high ends, along one axis, of the scaled items with their clearances. */
function spanAt(
  coords: number[],
  before: number[],
  after: number[],
  scale: number,
): { lo: number; hi: number } {
  let lo = Infinity;
  let hi = -Infinity;
  for (let i = 0; i < coords.length; i++) {
    const c = (coords[i] ?? 0) * scale;
    lo = Math.min(lo, c - (before[i] ?? 0));
    hi = Math.max(hi, c + (after[i] ?? 0));
  }
  return { lo, hi };
}

/**
 * Returns the largest uniform scale, up to MAX_SCALE, at which every mark and its clearance fits the frame, and the offsets that centre them.
 * Apply it to each centre as x * scale + tx and y * scale + ty.
 */
export function fitToFrame(items: FitItem[], width: number, height: number): FrameFit {
  if (items.length === 0) {
    return { scale: 1, tx: 0, ty: 0 };
  }
  const xs = items.map((i) => i.x);
  const ys = items.map((i) => i.y);
  const lefts = items.map((i) => i.left);
  const rights = items.map((i) => i.right);
  const tops = items.map((i) => i.top);
  const bottoms = items.map((i) => i.bottom);
  const fits = (scale: number): boolean => {
    const sx = spanAt(xs, lefts, rights, scale);
    const sy = spanAt(ys, tops, bottoms, scale);
    return sx.hi - sx.lo <= width && sy.hi - sy.lo <= height;
  };
  let lo = 0;
  let hi = MAX_SCALE;
  if (fits(hi)) {
    lo = hi;
  } else {
    for (let step = 0; step < SEARCH_STEPS; step++) {
      const mid = (lo + hi) / 2;
      if (fits(mid)) {
        lo = mid;
      } else {
        hi = mid;
      }
    }
  }
  const scale = lo;
  const sx = spanAt(xs, lefts, rights, scale);
  const sy = spanAt(ys, tops, bottoms, scale);
  return { scale, tx: (width - (sx.hi + sx.lo)) / 2, ty: (height - (sy.hi + sy.lo)) / 2 };
}
