import type { DossierView } from "../api/dossier";
import type { Section } from "../api/generated";
import { type Budget } from "../lib/budget";
import { formatNumber, formatRecordDate, pluralize } from "../lib/format";
import { leftOutSummary, seedPin, type FreshnessView } from "../lib/sourceRecord";
import type { SectionRow } from "../lib/dossierSections";
import { FreshnessChip } from "./Chip";
import { InfoDot } from "./InfoDot";
import { Record } from "./Record";
import { SectionTitle } from "./SectionTitle";

/** The dossier id with a break opportunity after the colon, so a narrow column breaks there before it breaks inside the hash. */
function DossierId({ id }: { id: string }) {
  const colon = id.indexOf(":");
  if (colon === -1) {
    return <>{id}</>;
  }
  return (
    <>
      {id.slice(0, colon + 1)}
      <wbr />
      {id.slice(colon + 1)}
    </>
  );
}

export interface SourceRecordProps {
  dossier: DossierView;
  rows: readonly SectionRow[];
  /** The sections the page leaves out of the article because the build found no prose in them. */
  noProseSections: readonly Section[];
  budget: Budget;
  freshness: FreshnessView;
}

/** The record of the pinned revision, the build and what the page leaves out, laid out for the screen width. */
export function SourceRecord({
  dossier,
  rows,
  noProseSections,
  budget,
  freshness,
}: SourceRecordProps) {
  const pin = seedPin(dossier);
  const leftOut = leftOutSummary(
    noProseSections.map((section) => section.label),
    rows.filter((row) => row.pack.state === "folded").map((row) => row.section.label),
    budget,
  );
  // Every section of the article, with the ones the page leaves out for having no prose counted in, so
  // "Sections" and "Left out" add up.
  const totalSectionCount = dossier.sections.length + noProseSections.length;
  const sourceRows = [
    {
      label: "Revision",
      value: pin ? (
        <a href={pin.permalink} className="hit-44 inline-block text-accent">
          {pin.rev_id}
        </a>
      ) : (
        "unknown"
      ),
      size: "normal" as const,
      wrap: true,
    },
    {
      label: "Retrieved",
      value: pin ? formatRecordDate(pin.retrieved_at) : "unknown",
      size: "normal" as const,
    },
    {
      label: "Freshness",
      value: (
        <FreshnessChip
          state={freshness.state}
          editsSincePin={dossier.freshness.edits_since ?? null}
          info={freshness.info}
          showInfo={dossier.freshness.source === "none"}
        />
      ),
      size: "normal" as const,
      wrap: true,
    },
    {
      label: "Licence",
      value: pin ? (
        <a
          href="https://creativecommons.org/licenses/by-sa/4.0/"
          className="hit-44 inline-block text-accent"
        >
          {pin.license}
        </a>
      ) : (
        "unknown"
      ),
      size: "normal" as const,
      wrap: true,
    },
    {
      label: "Sections",
      value: formatNumber(totalSectionCount),
      size: "normal" as const,
    },
    ...(leftOut.count > 0
      ? [
          {
            label: (
              <span>
                Left out
                <InfoDot label="About the sections left out" text={leftOut.detail} />
              </span>
            ),
            value: pluralize(leftOut.count, "section"),
            size: "normal" as const,
          },
        ]
      : []),
    {
      label: "Article",
      value: (
        <a href={dossier.links.wikipedia} className="hit-44 inline-block text-accent">
          {dossier.topic.title}
        </a>
      ),
      size: "normal" as const,
    },
    {
      label: "Revised",
      value: pin ? formatRecordDate(pin.rev_timestamp) : "unknown",
      size: "normal" as const,
    },
    {
      label: "Dossier id",
      value: (
        <span className="-my-0.5 block font-mono text-12 leading-[14px] [overflow-wrap:anywhere]">
          <DossierId id={dossier.id} />
        </span>
      ),
      title: dossier.id,
      size: "normal" as const,
      wrap: true,
    },
  ];
  return (
    <aside aria-labelledby="source-record-h">
      <SectionTitle level={2} count="one Wikipedia revision, pinned">
        <span id="source-record-h">Source record</span>
      </SectionTitle>
      <div className="mt-2 min-[600px]:hidden">
        <Record rows={sourceRows.slice(0, 4)} />
        <details>
          <summary className="cursor-pointer border-t-(length:--hairline) border-ink py-[13px] text-13 text-ink-2">
            Full source record
          </summary>
          <Record rows={sourceRows.slice(4)} />
        </details>
      </div>
      {/* In the single-column layout, shorter rows and a closer start keep the record from running far past the lede. */}
      <Record
        className="mt-2 max-w-[640px] max-[599px]:hidden min-[1200px]:hidden lg:max-[1199px]:mt-1 lg:max-[1199px]:[&_[data-record-row]]:min-h-6 lg:max-[1199px]:[&_[data-record-row]]:py-0.5"
        rows={sourceRows}
      />
      <div className="mt-2 hidden min-[1200px]:block min-[1200px]:border-(length:--hairline) min-[1200px]:border-rule-strong min-[1200px]:p-3">
        {/* The record splits into two columns of rows, and into three at the widest layout, so it ends level with the head instead of leaving a band under the lede. */}
        <div className="grid grid-cols-2 gap-x-6 min-[1440px]:hidden">
          <Record rows={sourceRows.slice(0, Math.ceil(sourceRows.length / 2))} />
          <Record rows={sourceRows.slice(Math.ceil(sourceRows.length / 2))} />
        </div>
        <div className="hidden grid-cols-3 gap-x-6 min-[1440px]:grid">
          {[0, 1, 2].map((column) => {
            const size = Math.ceil(sourceRows.length / 3);
            return (
              <Record key={column} rows={sourceRows.slice(column * size, (column + 1) * size)} />
            );
          })}
        </div>
      </div>
    </aside>
  );
}
