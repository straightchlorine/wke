import type { Chunk, Citation } from "../api/generated";
import { passageMarkers, splitLastWord } from "../lib/passageMarkers";
import { parseList, parseTable, textLinks } from "../lib/structuredPassage";
import { PassageBullets } from "./PassageBullets";
import { PassageMark } from "./PassageRun";
import { PassageTable } from "./PassageTable";

export interface PassageListProps {
  chunks: readonly Chunk[];
  citations: Citation[];
  /** The number shown in each citation's marker, by citation id. */
  numbers: ReadonlyMap<string, number>;
}

/**
 * The passages of one section, each with a link to its citation on the first passage of that citation.
 * A table or list passage is shown as a table or list; one whose text does not read as such is shown as plain text.
 */
export function PassageList({ chunks, citations, numbers }: PassageListProps) {
  const markers = passageMarkers(chunks, citations, numbers);
  return chunks.map((chunk, index) => {
    const marker = markers[index] ?? null;
    const id = `chunk-${chunk.id}`;
    if (chunk.kind === "table" || chunk.kind === "list") {
      const links = textLinks(chunk.text, chunk.links);
      const table = chunk.kind === "table" ? parseTable(chunk.text) : null;
      const list = chunk.kind === "list" ? parseList(chunk.text) : null;
      if (table) {
        return (
          <PassageTable
            key={chunk.id}
            text={chunk.text}
            layout={table}
            links={links}
            id={id}
            marker={marker}
          />
        );
      }
      if (list) {
        return (
          <PassageBullets
            key={chunk.id}
            text={chunk.text}
            layout={list}
            links={links}
            id={id}
            marker={marker}
          />
        );
      }
    }
    const { head, lastWord } = splitLastWord(chunk.text);
    return (
      <p key={chunk.id} id={id} className="scroll-mt-[calc(var(--dossier-stick,56px)_+_16px)]">
        {head}
        {/* The last word and the marker share one no-wrap span, so a line break never leaves "[n]" alone on a line. */}
        <span className="whitespace-nowrap">
          {lastWord}
          {marker ? <PassageMark marker={marker} /> : null}
        </span>
      </p>
    );
  });
}
