import { citationHref, type CitationNote, type CitationNotes } from "../lib/dossierPack";
import { formatCitedAbove } from "../lib/format";

function CitationList({ notes }: { notes: CitationNote[] }) {
  return (
    <ol className="mt-1 space-y-1 text-13 text-ink-2">
      {notes.map(({ citation, n, section }) => (
        <li key={citation.id}>
          [{n}]{" "}
          <a
            href={citationHref(citation)}
            className="text-accent [@media(pointer:coarse)]:inline-block [@media(pointer:coarse)]:py-[15px]"
          >
            {citation.pin.title}, {section ? `${section}, ` : ""}revision {citation.pin.rev_id}
          </a>
        </li>
      ))}
    </ol>
  );
}

/** The list of the links the dossier cites and, apart, the related articles, each pinned to a revision. */
export function DossierCitations({ notes }: { notes: CitationNotes }) {
  return (
    <section
      id="cites"
      className="border-t-(length:--hairline) border-rule py-6"
      aria-label="Citations"
    >
      <h2 className="font-serif text-22 text-ink">Citations</h2>
      <p className="mt-1 text-12 text-ink-3">
        {notes.cited.length + notes.related.length} links, each pinned to the revision shown.
      </p>
      {notes.cited.length > 0 ? (
        <>
          <p className="mt-3 text-12 text-ink-3">{formatCitedAbove(notes.cited.length)}</p>
          <CitationList notes={notes.cited} />
        </>
      ) : null}
      {notes.related.length > 0 ? (
        <>
          <p className="mt-3 text-12 text-ink-3">
            Related articles in Plate 1, each pinned to a revision but not cited in the text above.
          </p>
          <CitationList notes={notes.related} />
        </>
      ) : null}
    </section>
  );
}
