/** Least distance between two number labels on a vertical ruler, in px. */
export const MIN_LABEL_GAP_PX = 14;
/** Half a label's line box: a label is centred on its position. */
const LABEL_HALF_PX = 8;

export interface RulerLabel {
  key: string;
  text: string;
  /** The label's wanted centre, in px from the ruler's top. */
  pos: number;
  kind: "section" | "tick" | "end";
  title?: string;
}

/**
 * Returns the number labels of a vertical ruler to draw, with no two centres closer than `MIN_LABEL_GAP_PX`.
 * When labels collide, the end label wins over section labels, which win over ticks, and every centre is clamped inside the ruler.
 */
export function thinLabels(candidates: RulerLabel[], height: number): RulerLabel[] {
  const lo = LABEL_HALF_PX;
  const hi = Math.max(lo, height - LABEL_HALF_PX);
  const placed = candidates.map((c) => ({ ...c, pos: Math.min(hi, Math.max(lo, c.pos)) }));
  const rank = { end: 0, section: 1, tick: 2 } as const;
  const order = placed.toSorted((a, b) => rank[a.kind] - rank[b.kind] || a.pos - b.pos);
  const kept: RulerLabel[] = [];
  for (const label of order) {
    if (kept.every((k) => Math.abs(k.pos - label.pos) >= MIN_LABEL_GAP_PX)) {
      kept.push(label);
    }
  }
  return kept.toSorted((a, b) => a.pos - b.pos);
}

/**
 * Maps a token offset to a fraction by linear interpolation between the surrounding breakpoints, clamped to their range.
 * This lets a ruler follow the measured layout instead of assuming a fixed number of tokens per pixel.
 * The breakpoints must be sorted ascending by token.
 */
export function tokenToFraction(
  token: number,
  breakpoints: Array<{ token: number; fraction: number }>,
): number {
  const first = breakpoints[0];
  if (!first) {
    return 0;
  }
  if (token <= first.token) {
    return first.fraction;
  }
  for (let i = 1; i < breakpoints.length; i++) {
    const curr = breakpoints[i];
    const prev = breakpoints[i - 1];
    if (!curr || !prev) {
      continue;
    }
    if (token <= curr.token) {
      const t = (token - prev.token) / (curr.token - prev.token);
      return prev.fraction + t * (curr.fraction - prev.fraction);
    }
  }
  return (breakpoints[breakpoints.length - 1] ?? first).fraction;
}
