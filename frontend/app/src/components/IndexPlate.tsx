import { useEffect, useMemo, useState, type ReactNode, type Ref } from "react";
import type { TrendingSnapshot } from "../api/generated";
import type { Budget } from "../lib/budget";
import { formatProseDate, formatRefresh } from "../lib/format";
import type { ConceptGraphEdge, ConceptGraphNode } from "../lib/graphNodeInfo";
import { useMediaQuery } from "../lib/hooks/useMediaQuery";
import { useOpenDossier } from "../lib/hooks/useOpenDossier";
import type { ColorKeyGroup } from "../lib/indexGraph";
import { namesShownText } from "../lib/plateLabels";
import { plateSide } from "../lib/plateSide";
import { slugify, slugPath } from "../lib/slug";
import { FRESH_EDIT_MS } from "../lib/todaysIndex";
import { ConceptGraph, type ConceptGraphHandle } from "./ConceptGraph";
import { Plate } from "./Plate";

/** The frame's borders and padding take this much width from the figure, so the drawing is that much narrower. */
const PLATE_FRAME_INSET_PX = 10;
/** The height the header, the page's top padding and the gaps take from the window, so the frame on a short screen fits what is left. */
const SHORT_CHROME_PX = 96;
/** The narrowest frame side below the desktop layout, even in a very short window. */
const MIN_PLATE_PX = 210;
/** The narrowest drawing, whatever the frame's side. */
const MIN_DRAWING_PX = 200;
/** The column width before the first measurement. */
const DEFAULT_COLUMN_PX = 774;

const INDEX_GUIDE = [
  { label: "Lines", value: "articles whose lead paragraphs are similar" },
  { label: "Hulls", value: "a group of articles joined by lines" },
  { label: "Colour", value: "which group an article is in" },
  { label: "Key", value: "point at a colour to outline its group" },
  { label: "Grey", value: "no line to any other article" },
  { label: "Size", value: "views (square root)" },
  { label: "Red ring", value: `edited in the last ${FRESH_EDIT_MS / 1000} s` },
  { label: "Method", value: "all-MiniLM-L6-v2 similarity, 0.35 or more" },
];

export interface IndexPlateProps {
  trending: TrendingSnapshot | undefined;
  nodes: ConceptGraphNode[];
  edges: ConceptGraphEdge[];
  /** True while the edit feed is disconnected; the node tooltips then say "no edit data". */
  editsUnavailable: boolean;
  /** When the snapshot is from ("yesterday (...)" or "on ... (UTC)"), for the caption. */
  mostReadOn: string;
  graphRef: Ref<ConceptGraphHandle>;
  budget: Budget;
  isLoading: boolean;
  /** The failed-request message and its action, shown inside the empty frame. */
  error: { line: string; detail?: string; action: ReactNode } | null;
  /** The legend: each linked group by its most-read member. */
  colorKey: ColorKeyGroup[];
}

/** The concept graph of today's most-read articles in its frame (the Plate component), or a placeholder while it loads, fails or has nothing to draw. */
export function IndexPlate({
  trending,
  nodes,
  edges,
  editsUnavailable,
  mostReadOn,
  graphRef,
  budget,
  isLoading,
  error,
  colorKey,
}: IndexPlateProps) {
  const openDossier = useOpenDossier(budget);
  const [slotEl, setSlotEl] = useState<HTMLDivElement | null>(null);
  const [columnWidth, setColumnWidth] = useState(DEFAULT_COLUMN_PX);
  const [room, setRoom] = useState(Infinity);
  const [viewportHeight, setViewportHeight] = useState(Infinity);
  const [zoom, setZoom] = useState(1);
  const desktop = useMediaQuery("(min-width: 1024px)");
  const touch = useMediaQuery("(hover: none)");
  const [activeGroup, setActiveGroup] = useState<number | null>(null);
  const keyEntries = useMemo(
    () =>
      colorKey.map((group) => ({
        cluster: group.cluster,
        name: group.name,
        state: group.state,
        href: `${slugPath(group.name)}?budget=${budget}`,
        onOpen: () => openDossier(slugify(group.name)),
      })),
    [colorKey, budget, openDossier],
  );

  // Measures what plateSide needs: the column width, the root zoom and the height left below the frame's top edge.
  // It measures again when the column or the window resizes.
  useEffect(() => {
    const el = slotEl;
    if (!el || typeof ResizeObserver === "undefined") {
      return () => {};
    }
    function measure() {
      if (!el) {
        return;
      }
      const rootZoom =
        Number.parseFloat(
          getComputedStyle(document.documentElement).getPropertyValue("--ui-zoom"),
        ) || 1;
      setZoom(rootZoom);
      setColumnWidth(el.clientWidth);
      setViewportHeight(window.innerHeight / rootZoom);
      setRoom(
        window.innerHeight / rootZoom -
          (el.getBoundingClientRect().top + window.scrollY) / rootZoom,
      );
    }
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(el);
    window.addEventListener("resize", measure);
    return () => {
      observer.disconnect();
      window.removeEventListener("resize", measure);
    };
  }, [slotEl]);

  // The heading below the graph gives the date, so the caption only says "yesterday" when that applies.
  const plateDay = mostReadOn.startsWith("yesterday") ? " yesterday" : "";
  // Below the desktop layout the frame is as wide as the column, but no taller than the window height minus SHORT_CHROME_PX.
  // MIN_PLATE_PX is the floor, so a landscape phone gets a frame it can see whole unless the window is very short.
  const side = desktop
    ? plateSide(columnWidth, room, zoom)
    : Math.min(columnWidth, Math.max(MIN_PLATE_PX, Math.floor(viewportHeight - SHORT_CHROME_PX)));
  const drawing = Math.max(MIN_DRAWING_PX, side - PLATE_FRAME_INSET_PX);
  const frameStyle = desktop || side < columnWidth ? { width: side } : undefined;

  // At >= lg the slot is column 2 and spans every row, beside the intro, the search and the counters.
  // Below lg it follows the search in document order. When column 1 is taller, the figure stretches to match.
  const gridSlot =
    "mt-8 min-w-0 lg:col-start-2 lg:row-start-1 lg:row-span-3 lg:mt-0 lg:flex lg:flex-col";

  if (isLoading) {
    return (
      <div className={gridSlot} ref={setSlotEl}>
        <div
          style={frameStyle}
          className="mx-auto aspect-square w-full animate-pulse motion-reduce:animate-none border-(length:--hairline) border-rule bg-sunken"
        />
      </div>
    );
  }

  if (!trending) {
    // The empty frame keeps its square and carries the message and the action.
    // The index section below the frame says which part failed.
    return (
      <div className={gridSlot} ref={setSlotEl}>
        <div
          data-plate-error=""
          style={frameStyle}
          className="mx-auto flex aspect-square w-full flex-col items-center justify-center gap-2 border-(length:--hairline) border-rule bg-sunken p-4 text-center"
        >
          {error ? (
            <>
              <p className="text-14 font-medium text-ink">{error.line}</p>
              {error.detail ? <p className="text-13 text-ink-2">{error.detail}</p> : null}
              <div className="mt-1">{error.action}</div>
            </>
          ) : null}
        </div>
      </div>
    );
  }

  if (nodes.length === 0) {
    return (
      <div className={gridSlot} ref={setSlotEl}>
        <div className="border-(length:--hairline) border-rule-strong p-4 text-13 text-ink-2">
          No graph in the {formatProseDate(trending.date)} set yet.
          {formatRefresh(trending.next_refresh) ? ` ${formatRefresh(trending.next_refresh)}.` : ""}
        </div>
      </div>
    );
  }

  return (
    <div className={gridSlot} ref={setSlotEl}>
      <Plate
        className="mx-auto lg:flex-1"
        style={frameStyle}
        hud={`${nodes.length} nodes, ${edges.length} edges, sized by views`}
        captionLead="Plate 1."
        captionBody={`The ${nodes.length} most-read English Wikipedia articles${plateDay}.`}
        guide={INDEX_GUIDE}
        guideNote={namesShownText("index", touch)}
        colorKey={keyEntries}
        colorKeyLabel="Linked groups"
        onKeyActive={setActiveGroup}
      >
        <ConceptGraph
          ref={graphRef}
          nodes={nodes}
          edges={edges}
          variant="index"
          editsUnavailable={editsUnavailable}
          activeGroup={activeGroup}
          width={drawing}
          height={drawing}
          hrefSuffix={`?budget=${budget}`}
          ariaLabel={`The ${nodes.length} most-read English Wikipedia articles${plateDay}, sized by views, linked by similar lead paragraphs (similarity 0.35 or more).`}
          onOpen={(pageId) => {
            const node = nodes.find((n) => n.id === pageId);
            if (node) {
              openDossier(node.slug);
            }
          }}
        />
      </Plate>
    </div>
  );
}
