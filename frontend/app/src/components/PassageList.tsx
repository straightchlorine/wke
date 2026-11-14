import type { Chunk, Citation } from "../api/generated";
import { passageMarkers, splitLastWord } from "../lib/passageMarkers";

export interface PassageListProps {
  chunks: readonly Chunk[];
  citations: Citation[];
  /** The number shown in each citation's marker, by citation id. */
  numbers: ReadonlyMap<string, number>;
}

/** The passages of one section, each with a link to its citation on the first passage of that citation. */
export function PassageList({ chunks, citations, numbers }: PassageListProps) {
  const markers = passageMarkers(chunks, citations, numbers);
  return chunks.map((chunk, index) => {
    const { head, lastWord } = splitLastWord(chunk.text);
    const marker = markers[index];
    return (
      <p
        key={chunk.id}
        id={`chunk-${chunk.id}`}
        className="scroll-mt-[calc(var(--dossier-stick,56px)_+_16px)]"
      >
        {head}
        {/* The last word and the marker share one no-wrap span, so a line break never leaves "[n]" alone on a line. */}
        <span className="whitespace-nowrap">
          {lastWord}
          {marker ? (
            <sup className="ml-0.5">
              <a href={marker.href} className="hit-coarse text-accent">
                [{marker.n}]
              </a>
            </sup>
          ) : null}
        </span>
      </p>
    );
  });
}
