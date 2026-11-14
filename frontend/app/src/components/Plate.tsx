import { useCallback, useEffect, useId, useMemo, useRef, useState } from "react";
import type { CSSProperties, MouseEvent, ReactNode } from "react";
import { InfoDot, type TipClearance } from "./InfoDot";
import { isPlainLeftClick } from "../lib/clicks";
import { CLUSTER_COLORS, clusterVar } from "../lib/clusterStyle";
import type { DossierState } from "../lib/dossierState";
import { useMediaQuery } from "../lib/hooks/useMediaQuery";
import { legendChipSize } from "../lib/plateLegend";
import { PLATE_BOARD_PX } from "../lib/plateSide";
import { PlateSlotsContext } from "../lib/plateSlots";

/** How far apart the sample points on a group outline are. */
const OUTLINE_STEP_PX = 3;
/** Under this viewport height the legend tooltip opens beside its chip. */
const SHORT_VIEWPORT_PX = 500;

/** One legend swatch: a linked group, named by its most-read member. */
export interface PlateKeyEntry {
  /** The most-read member's title. */
  name: string;
  /** The group's colour index, the one the graph paints its dots and outline with. */
  cluster: number;
  /** The member's dossier route. */
  href: string;
  /** The member's dossier state: "Open dossier" when ready, "Build dossier" otherwise. */
  state?: DossierState;
  /** Opens the dossier in the app; the link still works as a plain link without it. */
  onOpen?: () => void;
}

/** One line of the "How to read the plate" tooltip: a visual encoding and what it shows. */
export interface PlateGuideRow {
  label: string;
  value: string;
}

export interface PlateProps {
  /** The text of the stats chip, e.g. "40 nodes, 71 edges, sized by views". */
  hud: string;
  /** The caption's bold first words, such as a figure number. */
  captionLead: string;
  /** The rest of the one-sentence caption. */
  captionBody: string;
  /** The rows of the "How to read the plate" tooltip, one per encoding. */
  guide: PlateGuideRow[];
  /** A sentence under the guide rows, e.g. which names the graph shows. */
  guideNote?: string;
  /**
   * The legend's entries in colour order, one swatch each. Entries beyond the number of group
   * colours are not drawn. A swatch shows no name: its tooltip reads "Articles related to <name>"
   * and links to that dossier. Omitted, no legend is drawn.
   */
  colorKey?: PlateKeyEntry[];
  /** The legend chip's accessible name. The chip shows no text. */
  colorKeyLabel?: string;
  /** Called with the colour index of the swatch whose tooltip is open, or null once none is. */
  onKeyActive?: (cluster: number | null) => void;
  className?: string;
  /** Inline style on the figure, for example a width that caps the frame's side. */
  style?: CSSProperties;
  children: ReactNode;
}

/** A framed figure for a concept graph, with a stats chip, a caption, a legend of linked groups and a how-to-read tooltip. */
export function Plate({
  hud,
  captionLead,
  captionBody,
  guide,
  guideNote,
  colorKey = [],
  colorKeyLabel = "Group colour",
  onKeyActive,
  children,
  className = "",
  style,
}: PlateProps) {
  const captionId = useId();
  const swatches = colorKey.slice(0, CLUSTER_COLORS.length);
  // The graph portals its node box (`PlateBoard`) into this slot, because the frame clips overflow.
  // The slot fixes the box's height.
  const [board, setBoard] = useState<HTMLElement | null>(null);
  const coarse = useMediaQuery("(pointer: coarse)");
  const legend = useMemo(
    () => (swatches.length > 0 ? legendChipSize(swatches.length, coarse) : null),
    [swatches.length, coarse],
  );
  const slots = useMemo(() => ({ board, legend }), [board, legend]);
  const frameRef = useRef<HTMLDivElement>(null);
  // On a touch screen a tap on the legend scrolls the whole frame into view, so the outlined group
  // and the tooltip are on screen together.
  const revealFrame = useCallback(() => {
    if (coarse) {
      frameRef.current?.scrollIntoView({ block: "nearest", behavior: "instant" });
    }
  }, [coarse]);
  const [activeKey, setActiveKey] = useState<number | null>(null);
  const onKeyActiveRef = useRef(onKeyActive);
  useEffect(() => {
    onKeyActiveRef.current = onKeyActive;
  });
  useEffect(() => {
    onKeyActiveRef.current?.(activeKey);
  }, [activeKey]);

  return (
    <figure
      aria-labelledby={captionId}
      style={style}
      className={`@container relative m-0 flex min-w-0 flex-col ${className}`}
    >
      <div
        ref={frameRef}
        data-plate-frame=""
        className="relative order-1 flex scroll-mt-16 scroll-mb-3 flex-col border-(length:--hairline) border-ink bg-sheet p-[3px]"
      >
        <div className="overflow-hidden border-(length:--hairline) border-rule-strong">
          <PlateSlotsContext value={slots}>{children}</PlateSlotsContext>
        </div>
        {/* The legend chip sits inside the frame, over the drawing. The graph keeps its dots,
            outlines and names off this rectangle (`legendChipSize`). */}
        {swatches.length > 0 ? (
          <span
            // oxlint-disable-next-line jsx-a11y/prefer-tag-over-role -- a row of buttons needs a name; fieldset and details carry other semantics
            role="group"
            aria-label={colorKeyLabel}
            data-plate-legend=""
            className="absolute bottom-[calc(8px-var(--hairline))] left-[calc(8px-var(--hairline))] z-10 flex h-[22px] items-center gap-x-3 border-(length:--hairline) border-rule bg-sheet px-1.5 text-12 [@media(pointer:coarse)]:h-7 [@media(pointer:coarse)]:gap-x-8 [@media(pointer:coarse)]:px-2"
          >
            {swatches.map((entry) => (
              <InfoDot
                key={entry.cluster}
                interactive
                tipBounds="figure"
                onReveal={revealFrame}
                clearOf={() => keyClearance(frameRef.current, board, entry.cluster)}
                triggerLabel={`Articles related to ${entry.name}`}
                onOpenChange={(open) =>
                  setActiveKey((current) =>
                    open ? entry.cluster : current === entry.cluster ? null : current,
                  )
                }
                text={<KeyTip entry={entry} />}
              >
                <span
                  aria-hidden="true"
                  className="inline-block size-3 shrink-0 rounded-full border-(length:--hairline) border-ink"
                  style={{ backgroundColor: clusterVar(entry.cluster) }}
                />
              </InfoDot>
            ))}
          </span>
        ) : null}
      </div>
      <div ref={setBoard} style={{ height: PLATE_BOARD_PX }} className="order-3 mt-2" />
      {/* The stats chip sits in flow under the frame, ahead of the caption, on narrow screens. On
          wider ones it floats over the frame's top-right corner. It needs z-10 because an
          out-of-flow child of the flex figure paints as order 0, under the frame. */}
      <span className="order-4 mt-2 self-start border-(length:--hairline) border-rule bg-sheet px-1.5 py-0.5 text-12 text-ink-3 min-[600px]:absolute min-[600px]:top-2 min-[600px]:right-2 min-[600px]:z-10 min-[600px]:mt-0">
        {hud}
      </span>
      <figcaption id={captionId} className="order-5 pt-2 font-serif text-13 text-ink-2">
        <b className="font-medium text-ink">{captionLead}</b> {captionBody}
      </figcaption>
      <span className="order-6 mt-1 self-start text-12 text-ink-3 [@media(pointer:coarse)]:inline-flex [@media(pointer:coarse)]:min-h-11 [@media(pointer:coarse)]:items-center">
        <span>
          How to read the plate
          <InfoDot
            text={<PlateGuide rows={guide} note={guideNote} />}
            label="How to read the plate"
          />
        </span>
      </span>
    </figure>
  );
}

/** Every visible node circle, whatever its colour, but not the transparent hit circles or the hover rings. */
const DISC_SELECTOR = "a > circle:not([data-plate-hit]):not([data-plate-hover-ring])";

/**
 * Collects what a legend tooltip keeps clear of: the swatch's own group first, then the other
 * groups, in screen px. `frame` is the figure's frame, `board` the slot under it where the tooltip
 * falls back to, and `cluster` the colour index of the swatch's group.
 */
function keyClearance(
  frame: HTMLElement | null,
  board: HTMLElement | null,
  cluster: number,
): TipClearance {
  const empty = new DOMRect();
  const chip = frame?.querySelector("[data-plate-legend]");
  const hull = frame?.querySelector(`path[data-plate-hull="${cluster}"]`);
  const discs = frame?.querySelectorAll(`circle[data-plate-cluster="${cluster}"]`) ?? [];
  const names = [...(frame?.querySelectorAll("a > text[data-plate-label]") ?? [])];
  const ownNames = names.filter(
    (el) => el.parentElement?.querySelector(`circle[data-plate-cluster="${cluster}"]`) != null,
  );
  const ownDiscs = new Set(discs);
  const otherDiscs = [...(frame?.querySelectorAll(DISC_SELECTOR) ?? [])].filter(
    (el) => !ownDiscs.has(el),
  );
  const otherHulls = [...(frame?.querySelectorAll("path[data-plate-hull]") ?? [])].filter(
    (el) => el !== hull,
  );
  return {
    anchor: chip?.getBoundingClientRect() ?? empty,
    frame: frame?.getBoundingClientRect() ?? empty,
    avoid: [...discs, ...ownNames].map((el) => el.getBoundingClientRect()),
    points: isPath(hull) ? outlinePoints(hull) : [],
    others: [...otherDiscs, ...names.filter((el) => !ownNames.includes(el))].map((el) =>
      el.getBoundingClientRect(),
    ),
    otherPoints: otherHulls.flatMap((el) => (isPath(el) ? outlinePoints(el) : [])),
    besideFirst: window.innerHeight < SHORT_VIEWPORT_PX,
    outside: board?.getBoundingClientRect(),
  };
}

/** Whether an element is an SVG path that can be measured, which jsdom's cannot. */
function isPath(el: Element | null | undefined): el is SVGPathElement {
  return el != null && "getTotalLength" in el && typeof el.getTotalLength === "function";
}

/** Returns a path's outline sampled every `OUTLINE_STEP_PX`, in screen px. */
function outlinePoints(path: SVGPathElement) {
  const m = path.getScreenCTM();
  const length = path.getTotalLength();
  const points: { x: number; y: number }[] = [];
  if (!m) {
    return points;
  }
  for (let at = 0; at < length; at += OUTLINE_STEP_PX) {
    const p = path.getPointAtLength(at);
    points.push({ x: m.a * p.x + m.c * p.y + m.e, y: m.b * p.x + m.d * p.y + m.f });
  }
  return points;
}

/** The body of the how-to-read tooltip: one row per encoding, then an optional note. */
function PlateGuide({ rows, note }: { rows: PlateGuideRow[]; note?: string }) {
  return (
    <>
      <dl className="m-0 text-12">
        {rows.map((row) => (
          <div key={row.label} className="flex min-h-5 items-baseline gap-x-2 leading-5">
            <dt className="shrink-0 whitespace-nowrap text-ink-2">{row.label}</dt>
            <span
              aria-hidden="true"
              className="min-w-3 flex-1 border-b-(length:--hairline) border-dotted border-rule-strong"
            />
            <dd className="m-0 min-w-0 text-right text-ink">{row.value}</dd>
          </div>
        ))}
      </dl>
      {note ? <p className="mt-1.5 text-12 text-ink-3">{note}</p> : null}
    </>
  );
}

/** The body of a legend swatch's tooltip: what the group is and a link to the dossier of its most-read member. */
function KeyTip({ entry }: { entry: PlateKeyEntry }) {
  function handleClick(event: MouseEvent<HTMLAnchorElement>) {
    if (!isPlainLeftClick(event) || !entry.onOpen) {
      return;
    }
    event.preventDefault();
    entry.onOpen();
  }
  return (
    <>
      <span className="block">Articles related to {entry.name}</span>
      <a
        href={entry.href}
        onClick={handleClick}
        className="hit-coarse mt-1 inline-block text-accent underline decoration-1 underline-offset-2"
      >
        {entry.state === "ready" ? "Open dossier" : "Build dossier"}
      </a>
    </>
  );
}
