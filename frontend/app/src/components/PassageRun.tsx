import type { PassageMarker } from "../lib/passageMarkers";
import { splitLastWord } from "../lib/passageMarkers";
import { slugPath } from "../lib/slug";
import type { Piece } from "../lib/structuredPassage";

const LINK =
  "text-ink underline decoration-rule-strong decoration-1 underline-offset-[3px] hover:decoration-ink";

/** The citation marker of a passage: its number as a link to the pinned revision. */
export function PassageMark({ marker }: { marker: PassageMarker }) {
  return (
    <sup className="ml-0.5">
      <a href={marker.href} className="hit-coarse text-accent">
        [{marker.n}]
      </a>
    </sup>
  );
}

/**
 * Shows the runs of a cell's or item's text, the linked ones as links to the Wikipedia article.
 * With a marker, the last word and the marker share one no-wrap span, so a line break never leaves "[n]" alone.
 */
export function PassageRun({ pieces, marker }: { pieces: Piece[]; marker?: PassageMarker | null }) {
  const last = marker ? pieces[pieces.length - 1] : undefined;
  const lead = last ? pieces.slice(0, -1) : pieces;
  const split = last && last.title == null ? splitLastWord(last.text) : null;
  return (
    <>
      {lead.map((piece, i) => (
        <Run key={i} piece={piece} />
      ))}
      {split?.head}
      {last && marker ? (
        <span className="whitespace-nowrap">
          {split ? split.lastWord : <Run piece={last} />}
          <PassageMark marker={marker} />
        </span>
      ) : null}
    </>
  );
}

function wikiUrl(title: string): string {
  return `https://en.wikipedia.org/wiki/${slugPath(title).slice("/t/".length)}`;
}

function Run({ piece }: { piece: Piece }) {
  return piece.title == null ? (
    piece.text
  ) : (
    <a href={wikiUrl(piece.title)} className={LINK}>
      {piece.text}
    </a>
  );
}
