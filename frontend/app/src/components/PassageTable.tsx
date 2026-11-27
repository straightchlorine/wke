import { useEffect, useRef } from "react";
import type { PassageMarker } from "../lib/passageMarkers";
import { pieces, type CountNote, type TableLayout, type TextLink } from "../lib/structuredPassage";
import { PassageMark, PassageRun } from "./PassageRun";

export interface PassageTableProps {
  /** The chunk's text, which the layout's cell ranges index. */
  text: string;
  layout: TableLayout;
  links: readonly TextLink[];
  /** The anchor id of the passage. */
  id: string;
  marker: PassageMarker | null;
}

/** The "8 of 21 rows shown" line under a table or list that was cut at a row or item boundary. */
export function countNoteText(note: CountNote): string {
  return `${note.shown} of ${note.total} ${note.noun} shown`;
}

/**
 * Makes the box scroll and take focus only while its content is wider than it is.
 * A box that fits has no tab stop; one that overflows gets a name, so a keyboard user can scroll it.
 */
function useSidewaysScroll(label: string) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const box = ref.current;
    if (!box) {
      return () => {};
    }
    function update() {
      if (!box) {
        return;
      }
      if (box.scrollWidth > box.clientWidth + 1) {
        box.tabIndex = 0;
        box.setAttribute("role", "group");
        box.setAttribute("aria-label", label);
      } else {
        box.removeAttribute("tabindex");
        box.removeAttribute("role");
        box.removeAttribute("aria-label");
      }
    }
    update();
    const resize = typeof ResizeObserver === "undefined" ? null : new ResizeObserver(update);
    resize?.observe(box);
    if (box.firstElementChild) {
      resize?.observe(box.firstElementChild);
    }
    return () => resize?.disconnect();
  }, [label]);
  return ref;
}

/** One table passage as a real table: its caption, header and rows, wide ones scrolling sideways inside their own box. */
export function PassageTable({ text, layout, links, id, marker }: PassageTableProps) {
  const label = layout.caption || "Table";
  const scroller = useSidewaysScroll(label);
  const { caption, header, rows, note } = layout;
  const cell = (range: { start: number; end: number }) => pieces(text, range, links, true);
  return (
    <div
      id={id}
      data-passage="table"
      className="scroll-mt-[calc(var(--dossier-stick,56px)_+_16px)] pt-2 font-sans text-13"
    >
      <div ref={scroller} className="thin-scroll overflow-x-auto">
        <table className="w-full border-t-(length:--hairline) border-ink text-left">
          {caption ? (
            <caption className="pb-1.5 text-left text-13 text-ink-2">
              <PassageRun pieces={[{ text: caption, title: null }]} marker={marker} />
            </caption>
          ) : null}
          <thead>
            <tr className="border-b-(length:--hairline) border-rule-strong text-12 text-ink-3">
              {header.map((range, i) => (
                <th key={i} scope="col" className="min-w-24 py-1.5 pr-3 align-top font-normal">
                  {range.end > range.start ? (
                    <PassageRun pieces={cell(range)} />
                  ) : (
                    <span className="sr-only">Unlabelled column</span>
                  )}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row, r) => (
              <tr key={r} className="border-b-(length:--hairline) border-rule">
                {row.map((range, c) => (
                  <td key={c} className="min-w-24 py-1.5 pr-3 align-top text-ink">
                    <PassageRun pieces={cell(range)} />
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {note || (marker && !caption) ? (
        <div className="mt-1.5 text-12 text-ink-3">
          {note ? countNoteText(note) : null}
          {marker && !caption ? <PassageMark marker={marker} /> : null}
        </div>
      ) : null}
    </div>
  );
}
