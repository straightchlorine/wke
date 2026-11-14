import { SECOND_RING_DELAY_MS } from "../lib/hooks/usePings";
import { clusterVar } from "../lib/clusterStyle";

const HOVER_RING_GAP_PX = 3.75;
const SELECTION_BOX_GAP_PX = 4;

export interface GraphNodeMarkProps {
  /** The node's centre, radius and group colour index. */
  node: { x: number; y: number; radius: number; cluster: number };
  /** The node was just edited: it is drawn in the stamp colour, with rings. */
  pinged: boolean;
  /** The node is the seed of the related graph: a filled ink dot. */
  seed: boolean;
  /** The node belongs to no linked group, so it has no group colour. */
  neutral: boolean;
  /** Draws a heavier outline. */
  highlighted: boolean;
  selected: boolean;
  /** Draws the hover and focus ring. */
  ringed: boolean;
  /** The radius of the transparent circle that takes pointer hits. */
  hitRadius: number;
  /** The ids of the rings to draw while `pinged`. */
  ringIds: string[];
  reducedMotion: boolean;
}

/** The circles that draw one node: its dot, hit area, selection box, hover ring and ping rings. */
export function GraphNodeMark({
  node,
  pinged,
  seed,
  neutral,
  highlighted,
  selected,
  ringed,
  hitRadius,
  ringIds,
  reducedMotion,
}: GraphNodeMarkProps) {
  const { x, y, radius } = node;
  return (
    <>
      {pinged ? (
        <circle
          cx={x}
          cy={y}
          r={radius}
          stroke="var(--wke-stamp)"
          strokeWidth={highlighted ? 4 : 2.5}
          fill="var(--wke-stamp-wash)"
        />
      ) : seed ? (
        <circle
          cx={x}
          cy={y}
          r={radius}
          stroke="var(--wke-ink)"
          strokeWidth={highlighted ? 3 : 1.5}
          fill="var(--wke-ink)"
        />
      ) : (
        <circle
          data-plate-neutral={neutral ? "" : undefined}
          data-plate-cluster={neutral ? undefined : node.cluster}
          cx={x}
          cy={y}
          r={radius}
          stroke={neutral ? "var(--wke-ink-3)" : clusterVar(node.cluster)}
          strokeWidth={highlighted ? 3 : 1.5}
          fill={neutral ? "var(--wke-paper)" : clusterVar(node.cluster)}
          fillOpacity={neutral ? 1 : 0.18}
        />
      )}
      <circle data-plate-hit="" cx={x} cy={y} r={Math.max(radius, hitRadius)} fill="transparent" />
      {selected ? (
        <rect
          data-plate-ring=""
          x={x - radius - SELECTION_BOX_GAP_PX}
          y={y - radius - SELECTION_BOX_GAP_PX}
          width={2 * (radius + SELECTION_BOX_GAP_PX)}
          height={2 * (radius + SELECTION_BOX_GAP_PX)}
          rx={0}
          fill="none"
          stroke="var(--wke-ink)"
          strokeWidth={1}
          pointerEvents="none"
        />
      ) : null}
      {ringed ? (
        <circle
          data-plate-hover-ring=""
          cx={x}
          cy={y}
          r={radius + HOVER_RING_GAP_PX}
          fill="none"
          stroke="var(--wke-ink)"
          strokeOpacity={0.55}
          strokeWidth={1.5}
          pointerEvents="none"
        />
      ) : null}
      {/* Each ping draws two stroke-only rings. When animated, the second starts later than the first. */}
      {pinged
        ? ringIds.flatMap((ringId) =>
            [0, 1].map((ringIndex) => (
              <circle
                key={`${ringId}-${ringIndex}`}
                cx={x}
                cy={y}
                r={radius}
                fill="none"
                stroke="var(--wke-stamp)"
                strokeWidth={1.5}
                className={reducedMotion ? "" : "animate-(--animate-ping-ring)"}
                style={{
                  transformBox: "fill-box",
                  transformOrigin: "center",
                  ...(reducedMotion
                    ? { transform: "scale(1.8)", opacity: 0.6 }
                    : ringIndex === 1
                      ? { animationDelay: `${SECOND_RING_DELAY_MS}ms`, opacity: 0 }
                      : {}),
                }}
              />
            )),
          )
        : null}
    </>
  );
}
