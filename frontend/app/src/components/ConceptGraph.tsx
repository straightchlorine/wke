import { useCallback, useContext, useEffect, useImperativeHandle, useMemo, useState } from "react";
import type { KeyboardEvent, Ref } from "react";
import { createPortal } from "react-dom";
import { clusterVar, hullPath } from "../lib/clusterStyle";
import { isPlainLeftClick } from "../lib/clicks";
import { dotNamesFor } from "../lib/dotNames";
import {
  boardNodeFor,
  groupedClusters,
  neighbourTitles,
  nodeAriaLabel,
  type ConceptGraphEdge,
  type ConceptGraphNode,
  type GraphVariant,
} from "../lib/graphNodeInfo";
import { useGraphLayout } from "../lib/hooks/useGraphLayout";
import { useMediaQuery } from "../lib/hooks/useMediaQuery";
import { usePings } from "../lib/hooks/usePings";
import { useReducedMotion } from "../lib/hooks/useReducedMotion";
import { keyStartedInside, useRovingFocus } from "../lib/hooks/useRovingFocus";
import { textBaselineY, nameBackingRect, textOriginX } from "../lib/labelText";
import { announceLive } from "../lib/liveRegion";
import { PlateSlotsContext } from "../lib/plateSlots";
import { GraphLabel } from "./GraphLabel";
import { GraphNodeMark } from "./GraphNodeMark";
import { HaloText } from "./HaloText";
import { PlateBoard } from "./PlateBoard";

export type { ConceptGraphEdge, ConceptGraphNode };

export interface ConceptGraphHandle {
  /** Marks the node for `pageId` as just edited, if it is in the graph. Pass `ring` false to skip the rings. */
  ping: (pageId: number, ring?: boolean) => void;
  /** Sets or clears the heavier outline on the node for `pageId`, for hover and focus elsewhere on the page. */
  highlight: (pageId: number | null) => void;
}

export interface ConceptGraphProps {
  nodes: ConceptGraphNode[];
  edges: ConceptGraphEdge[];
  /** The index graph on Home, or the related-articles graph on a dossier page. */
  variant: GraphVariant;
  /** Drawing-area size in CSS px. */
  width: number;
  height: number;
  /** Called when a selected node is opened: a second click, tap or Enter, or the link in PlateBoard. */
  onOpen: (pageId: number) => void;
  /** Appended to every node link, e.g. "?budget=8000". */
  hrefSuffix?: string;
  /** Replaces the width test that decides phone behaviour: the label rules and, on the related variant, whether room is kept for the stats chip. */
  compact?: boolean;
  /**
   * Forces or forbids the square-frame layout, which suits a frame that holds more dots per unit
   * area: fewer rows of groups and wider spacing. Omitted, a frame that is nearly square and
   * narrow is treated as square.
   */
  squareFrame?: boolean;
  /** Accessible name of the svg group. Defaults to a fixed name per variant. */
  ariaLabel?: string;
  /**
   * True while the edit feed is disconnected. On the index variant, PlateBoard then says "no edit
   * data" instead of a count that would read as a measured 0.
   */
  editsUnavailable?: boolean;
  /**
   * The colour index of the linked group a legend swatch points at: its outline is drawn stronger
   * and its dots take the heavier stroke, so the swatch can be matched to the group. Null or
   * omitted draws every group alike.
   */
  activeGroup?: number | null;
  ref?: Ref<ConceptGraphHandle>;
  className?: string;
}

/** The smallest radius of a node's hit circle: wide enough for a 24px target, with a pixel of slack for a graph drawn slightly under 1:1. */
const MIN_HIT_RADIUS_PX = 13;
/** The radius of a node's hit circle under a coarse pointer, for a 44px target. */
const COARSE_HIT_RADIUS_PX = 22;
/** Fill opacity of a group outline while its legend swatch is active. The other outlines use a lighter fill. */
const HULL_ACTIVE_FILL_OPACITY = 0.16;
const HULL_FILL_OPACITY = 0.06;

/** Draws a concept graph: dots grouped by link, their names, and PlateBoard for the dot in play. */
export function ConceptGraph({
  nodes,
  edges,
  variant,
  width,
  height,
  onOpen,
  hrefSuffix = "",
  ariaLabel,
  compact,
  squareFrame,
  editsUnavailable = false,
  activeGroup = null,
  ref,
  className = "",
}: ConceptGraphProps) {
  const [settled, setSettled] = useState(false);
  const [highlightedId, setHighlightedId] = useState<number | null>(null);
  // hoverId is the node under the pointer and focusId the node with keyboard focus. Each is set at
  // once, with no delay.
  const [hoverId, setHoverId] = useState<number | null>(null);
  const [focusId, setFocusId] = useState<number | null>(null);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  // Focus that came from a pointer keeps no outline: the selection box marks the node.
  const [pointerFocusId, setPointerFocusId] = useState<number | null>(null);
  const slots = useContext(PlateSlotsContext);
  const touchOnly = useMediaQuery("(hover: none)");
  const coarsePointer = useMediaQuery("(pointer: coarse)");
  const reducedMotion = useReducedMotion();
  const hitRadius = coarsePointer ? COARSE_HIT_RADIUS_PX : MIN_HIT_RADIUS_PX;

  const { layout, labelPlacements, reservedBoxes, nameChars, graphEdges } = useGraphLayout({
    nodes,
    edges,
    variant,
    width,
    height,
    compact,
    squareFrame,
    legendSize: slots?.legend ?? null,
  });
  const groups = useMemo(() => groupedClusters(layout.nodes), [layout.nodes]);
  const layoutById = useMemo(() => new Map(layout.nodes.map((n) => [n.id, n])), [layout.nodes]);
  const nodeById = useMemo(() => new Map(nodes.map((n) => [n.id, n])), [nodes]);
  // Tab order, arrow keys and Home/End follow the order of `nodes`, which is the caller's rank.
  // layout.nodes is ordered by page id, so it cannot be used here.
  const ordered = useMemo(
    () =>
      nodes.flatMap((source) => {
        const node = layoutById.get(source.id);
        return node ? [{ source, node }] : [];
      }),
    [nodes, layoutById],
  );
  const roving = useRovingFocus(ordered.length);
  const knownIds = useMemo(() => new Set(nodeById.keys()), [nodeById]);
  const { counts: pingCounts, ringIdsFor, ping } = usePings(knownIds);

  useEffect(() => {
    // Settling waits one frame, so the first paint is at opacity 0 and the fade has a start.
    // Under reduced motion the transition is off and the graph simply appears.
    const frame = requestAnimationFrame(() => setSettled(true));
    return () => cancelAnimationFrame(frame);
  }, []);

  const highlight = useCallback((pageId: number | null) => {
    setHighlightedId(pageId);
  }, []);
  useImperativeHandle(ref, () => ({ ping, highlight }), [ping, highlight]);

  // The name of a dot that has no permanent label but is in play (selected, under the pointer,
  // focused or just edited): drawn beside its own dot in the label style, never moving a label.
  const dotNames = useMemo(
    () =>
      dotNamesFor([selectedId, hoverId, focusId, ...pingCounts.keys()], {
        variant,
        selectedId,
        nodes: layout.nodes,
        labelPlacements,
        reservedBoxes,
        width,
        height,
        ellipsisChars: nameChars,
      }),
    [
      selectedId,
      hoverId,
      focusId,
      pingCounts,
      variant,
      layout.nodes,
      labelPlacements,
      reservedBoxes,
      width,
      height,
      nameChars,
    ],
  );

  // PlateBoard shows the selection when there is one, else the node under the pointer or focus,
  // else its idle hint.
  const boardId = selectedId ?? hoverId ?? focusId;
  const boardSource = boardId != null ? nodeById.get(boardId) : undefined;
  const neighbours = useMemo(() => neighbourTitles(nodes, edges), [nodes, edges]);

  function select(id: number | null) {
    setSelectedId(id);
    if (id == null) {
      announceLive("Selection cleared");
      return;
    }
    announceLive(`Selected ${nodeById.get(id)?.title ?? ""}. Press Enter again to open.`);
  }

  /** Selects a node, or opens its dossier when it is already selected. */
  function activate(id: number) {
    if (selectedId === id) {
      onOpen(id);
    } else {
      select(id);
    }
  }

  function handleKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    if (event.key === "Escape") {
      if (selectedId != null) {
        select(null);
      }
      // The key came from PlateBoard in a slot outside this element, so bring focus back to the graph.
      if (!keyStartedInside(event)) {
        roving.focusCurrent();
      }
      return;
    }
    // Moving along the ranks drops the selection; PlateBoard follows the focus.
    if (roving.moveOnKey(event) && selectedId != null) {
      setSelectedId(null);
    }
  }

  // The one dot whose name is emphasised: the selection, else the dot under the pointer or focus.
  // While something is selected, a hovered dot gets its ring but its name is not emphasised.
  const emphasisId = selectedId ?? hoverId ?? focusId;
  const board = (
    <PlateBoard
      node={
        boardSource
          ? boardNodeFor(boardSource, { variant, editsUnavailable, neighbours, hrefSuffix })
          : null
      }
      selected={selectedId != null && selectedId === boardId}
      touch={touchOnly}
      onOpen={() => (boardId != null ? onOpen(boardId) : undefined)}
    />
  );
  // Inside `Plate`, PlateBoard goes into the slot `Plate` provides, outside the clipped frame, and
  // waits until the slot exists. Without a `Plate` it sits in flow under the graph.
  const boardPortal = slots ? (slots.board ? createPortal(board, slots.board) : null) : board;
  // Larger nodes draw first so a small node's hit area wins an overlap.
  const drawOrder = ordered
    .map((item, index) => ({ ...item, index }))
    .toSorted((a, b) => b.node.radius - a.node.radius);

  return (
    // oxlint-disable-next-line jsx-a11y/no-static-element-interactions -- arrow-key roving tabindex listens on the frame, not the svg
    <div onKeyDown={handleKeyDown} className={`relative ${className}`}>
      {/* A click that lands on no node clears the selection; Escape is the keyboard path. */}
      {/* oxlint-disable-next-line jsx-a11y/click-events-have-key-events, jsx-a11y/no-noninteractive-element-interactions -- the nodes carry the keyboard behaviour */}
      <svg
        onClick={(event) => {
          if (selectedId != null && event.target instanceof Element && !event.target.closest("a")) {
            select(null);
          }
        }}
        // oxlint-disable-next-line jsx-a11y/prefer-tag-over-role -- an inline svg graph has no semantic tag; role=group with aria-label is the required pattern
        role="group"
        aria-label={
          ariaLabel ?? (variant === "index" ? "Plate 1: concept graph" : "Plate 2: concept graph")
        }
        viewBox={`0 0 ${width} ${height}`}
        className="block h-auto w-full"
        style={{
          opacity: settled ? 1 : 0,
          transition: reducedMotion ? "none" : "opacity 200ms var(--ease-out)",
        }}
      >
        <g>
          {layout.hulls.map((hull) => {
            const active = activeGroup === hull.cluster;
            return (
              <path
                key={hull.cluster}
                data-plate-hull={hull.cluster}
                data-plate-hull-active={active ? "" : undefined}
                d={hullPath(hull.points)}
                fill={clusterVar(hull.cluster)}
                fillOpacity={active ? HULL_ACTIVE_FILL_OPACITY : HULL_FILL_OPACITY}
                stroke={clusterVar(hull.cluster)}
                strokeOpacity={active ? 1 : 0.5}
                strokeWidth={active ? 1.5 : 1}
                strokeDasharray="1 3"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            );
          })}
        </g>
        <g>
          {graphEdges.map((edge) => {
            const from = layoutById.get(edge.source);
            const to = layoutById.get(edge.target);
            if (!from || !to) {
              return null;
            }
            return (
              <line
                key={`${edge.source}-${edge.target}`}
                x1={from.x}
                y1={from.y}
                x2={to.x}
                y2={to.y}
                stroke="var(--wke-rule-strong)"
                strokeOpacity={0.6}
                strokeWidth={1}
              />
            );
          })}
        </g>
        <g>
          {drawOrder.map(({ source, node, index }) => {
            const pinged = pingCounts.has(node.id);
            const pingCount = pingCounts.get(node.id) ?? 0;
            const selected = selectedId === node.id;
            const neutral = variant === "index" && !groups.has(node.cluster);
            const highlighted =
              highlightedId === node.id ||
              (activeGroup != null && !neutral && node.cluster === activeGroup);
            const label = labelPlacements.get(node.id);
            const hideOwnLabel = variant === "related" && selected && label != null;
            return (
              <a
                key={node.id}
                ref={roving.itemRef(index)}
                // oxlint-disable-next-line jsx-a11y/prefer-tag-over-role -- the node keeps its href so a modified click opens the dossier natively; it acts as a button otherwise
                role="button"
                aria-pressed={selected}
                href={`/t/${source.slug}${hrefSuffix}`}
                aria-label={nodeAriaLabel(source, variant, { pinged, selected })}
                tabIndex={index === roving.current ? 0 : -1}
                onFocus={(event) => {
                  roving.markFocused(index);
                  let visible = false;
                  try {
                    visible = event.currentTarget.matches(":focus-visible");
                  } catch {
                    // No :focus-visible support: treat as a pointer focus.
                  }
                  setFocusId(visible ? node.id : null);
                }}
                onBlur={() => {
                  setFocusId(null);
                  setPointerFocusId(null);
                }}
                onPointerDown={() => setPointerFocusId(node.id)}
                onPointerEnter={(event) => {
                  if (event.pointerType === "touch") {
                    return;
                  }
                  setHoverId(node.id);
                }}
                onPointerLeave={(event) => {
                  if (event.pointerType === "touch") {
                    return;
                  }
                  setHoverId((current) => (current === node.id ? null : current));
                }}
                onKeyDown={(event) => {
                  setPointerFocusId(null);
                  // A link answers Enter but not Space; a button answers both. An svg link has no
                  // click(), so Space calls the same handler a click does.
                  if (event.key === " ") {
                    event.preventDefault();
                    activate(node.id);
                  }
                }}
                onClick={(event) => {
                  if (!isPlainLeftClick(event)) {
                    return;
                  }
                  event.preventDefault();
                  activate(node.id);
                }}
                className={`cursor-pointer ${pointerFocusId === node.id ? "outline-none" : ""}`}
              >
                <GraphNodeMark
                  node={node}
                  pinged={pinged}
                  seed={source.role === "seed"}
                  neutral={neutral}
                  highlighted={highlighted}
                  selected={selected}
                  ringed={!selected && (hoverId === node.id || focusId === node.id)}
                  hitRadius={hitRadius}
                  ringIds={ringIdsFor(node.id)}
                  reducedMotion={reducedMotion}
                />
                {label ? (
                  <GraphLabel
                    label={label}
                    emphasised={emphasisId === node.id}
                    hidden={hideOwnLabel}
                  />
                ) : null}
                {pinged && pingCount > 1 ? (
                  <HaloText
                    x={node.x + node.radius + 4}
                    y={node.y - node.radius}
                    fontWeight={500}
                    fill="var(--wke-stamp)"
                    pointerEvents="none"
                  >
                    {`+${pingCount - 1}`}
                  </HaloText>
                ) : null}
              </a>
            );
          })}
        </g>
        <g aria-hidden="true" pointerEvents="none">
          {[...dotNames].map(([id, { box, backed }]) => (
            <g key={id}>
              {backed ? (
                <rect
                  data-plate-name-backing=""
                  {...nameBackingRect(box)}
                  fill="var(--wke-sheet)"
                  stroke="var(--wke-rule-strong)"
                  strokeWidth={1}
                />
              ) : null}
              <HaloText
                data-plate-name=""
                x={textOriginX(box)}
                textAnchor={box.textAnchor ?? "start"}
                y={textBaselineY(box)}
                emphasised={emphasisId === id}
              >
                {box.text}
              </HaloText>
            </g>
          ))}
        </g>
      </svg>
      {boardPortal}
    </div>
  );
}
