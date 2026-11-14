/** The colour token names a cluster cycles through. */
export const CLUSTER_COLORS = ["c1", "c2", "c3", "c4", "c5", "c6"] as const;

/** The CSS variable reference for a cluster's colour, cycling through CLUSTER_COLORS. */
export function clusterVar(cluster: number): string {
  const name = CLUSTER_COLORS[cluster % CLUSTER_COLORS.length] ?? "c1";
  return `var(--wke-${name})`;
}

/** The closed SVG path for a hull polygon given in viewBox units, or an empty string when there are no points. */
export function hullPath(points: Array<[number, number]>): string {
  if (points.length === 0) {
    return "";
  }
  const [first, ...rest] = points;
  if (!first) {
    return "";
  }
  const segments = rest.map(([x, y]) => `L${x.toFixed(1)} ${y.toFixed(1)}`);
  return `M${first[0].toFixed(1)} ${first[1].toFixed(1)}${segments.join("")}Z`;
}
