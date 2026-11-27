import type { PassageMarker } from "../lib/passageMarkers";
import { pieces, type ListItem, type ListLayout, type TextLink } from "../lib/structuredPassage";
import { PassageRun } from "./PassageRun";
import { countNoteText } from "./PassageTable";

export interface PassageBulletsProps {
  /** The chunk's text, which the layout's item ranges index. */
  text: string;
  layout: ListLayout;
  links: readonly TextLink[];
  /** The anchor id of the passage. */
  id: string;
  marker: PassageMarker | null;
}

function lastItem(items: ListItem[]): ListItem | undefined {
  const last = items[items.length - 1];
  return last && last.children.length > 0 ? lastItem(last.children) : last;
}

/** One list passage as a real list, nested where the text nests; the citation marker ends its last item. */
export function PassageBullets({ text, layout, links, id, marker }: PassageBulletsProps) {
  const { items, note } = layout;
  const marked = lastItem(items);
  const render = (level: ListItem[], depth: number) => (
    <ul
      className={`${depth === 0 ? "" : "mt-1 "}pl-5 marker:text-ink-3 ${depth === 0 ? "list-disc" : "list-[circle]"}`}
    >
      {level.map((item, i) => (
        <li key={i} className="mt-1 first:mt-0">
          <PassageRun
            pieces={pieces(text, item, links, false)}
            marker={item === marked ? marker : null}
          />
          {item.children.length > 0 ? render(item.children, depth + 1) : null}
        </li>
      ))}
    </ul>
  );
  return (
    <div id={id} data-passage="list" className="scroll-mt-[calc(var(--dossier-stick,56px)_+_16px)]">
      {render(items, 0)}
      {note ? (
        <div className="mt-1.5 font-sans text-12 text-ink-3">{countNoteText(note)}</div>
      ) : null}
    </div>
  );
}
