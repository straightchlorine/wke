import { type Ref, useLayoutEffect, useRef, useState } from "react";
import { NOTE_GAP_PX, stackNotes } from "../lib/stackNotes";
import { Record, type RecordRowProps } from "./Record";

export interface MarginNoteProps {
  /** The section's label, shown in the note's heading and used in its accessible group name. */
  sectionLabel: string;
  rows: RecordRowProps[];
  className?: string;
}

/** A section's source rows under a heading that names the section. */
export function MarginNote({ sectionLabel, rows, className = "" }: MarginNoteProps) {
  return (
    <div className={className}>
      {/* The visible heading is hidden from assistive tech because the Record's aria-label already names the group. */}
      <p aria-hidden="true" className="mb-1 text-12 text-ink-3">
        Source, {sectionLabel}
      </p>
      <Record label={`Source for ${sectionLabel}`} rows={rows} />
    </div>
  );
}

export interface MarginNoteRailNote {
  id: string;
  sectionLabel: string;
  rows: RecordRowProps[];
  /** Where the note wants to start, in px from the rail's own top. */
  top: number;
}

export interface MarginNoteRailProps {
  notes: MarginNoteRailNote[];
  /** The article's bottom edge, in px from the rail's own top. */
  bottom: number;
  ref?: Ref<HTMLDivElement>;
  className?: string;
}

/**
 * The margin column of section notes. Each note sits at its section, is
 * stacked below the one before it when sections are short, and stays
 * sticky inside the span up to the next note.
 */
export function MarginNoteRail({ notes, bottom, ref, className = "" }: MarginNoteRailProps) {
  const noteRefs = useRef<Array<HTMLDivElement | null>>([]);
  const [layout, setLayout] = useState<{ placed: number[]; heights: number[] }>({
    placed: [],
    heights: [],
  });
  const topsKey = notes.map((note) => Math.round(note.top)).join(",");

  useLayoutEffect(() => {
    const tops = topsKey === "" ? [] : topsKey.split(",").map(Number);
    function place() {
      const heights = tops.map((_, index) => noteRefs.current[index]?.offsetHeight ?? 0);
      const placed = stackNotes(tops, heights, bottom);
      setLayout((previous) =>
        previous.placed.length === placed.length &&
        previous.placed.every((value, index) => value === placed[index]) &&
        previous.heights.every((value, index) => value === heights[index])
          ? previous
          : { placed, heights },
      );
    }
    place();
    let observer: ResizeObserver | undefined;
    if (typeof ResizeObserver !== "undefined") {
      observer = new ResizeObserver(place);
      for (const el of noteRefs.current.slice(0, tops.length)) {
        if (el) {
          observer.observe(el);
        }
      }
    }
    window.addEventListener("resize", place);
    return () => {
      observer?.disconnect();
      window.removeEventListener("resize", place);
    };
  }, [topsKey, bottom]);

  const lastIndex = notes.length - 1;
  const lastPlaced = layout.placed[lastIndex] ?? 0;
  const stackBottom = lastPlaced + (layout.heights[lastIndex] ?? 0);

  return (
    <div
      ref={ref}
      className={`relative ${className}`}
      style={stackBottom > bottom ? { minHeight: stackBottom } : undefined}
    >
      {notes.map((note, index) => {
        const top = layout.placed[index] ?? note.top;
        const height = layout.heights[index] ?? 0;
        const nextTop = layout.placed[index + 1];
        const span =
          nextTop === undefined ? Math.max(bottom - top, height) : nextTop - top - NOTE_GAP_PX;
        return (
          <div
            key={note.id}
            className="absolute inset-x-0"
            style={{ top, height: Math.max(span, height) }}
          >
            <div
              ref={(el) => {
                noteRefs.current[index] = el;
              }}
              className="sticky top-16"
            >
              <MarginNote sectionLabel={note.sectionLabel} rows={note.rows} />
            </div>
          </div>
        );
      })}
    </div>
  );
}
