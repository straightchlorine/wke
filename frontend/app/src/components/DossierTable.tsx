import type { ReactNode } from "react";
import { Link } from "@tanstack/react-router";
import { ExternalLink } from "lucide-react";
import type { DossierListItem } from "../api/generated";
import { Chip, FreshnessChip } from "./Chip";
import { InfoDot } from "./InfoDot";
import { slugify } from "../lib/slug";
import { budgetAlias, FITS_IN_HELP } from "../lib/budget";
import { formatRecordDate } from "../lib/format";

export interface DossierTableProps {
  items: DossierListItem[];
  /** Number of skeleton body rows to draw instead of `items` while the list loads. The header row keeps its real column labels. */
  loadingRows?: number;
  className?: string;
}

const SKELETON_COLS = 6;

function oldidUrl(title: string, revId: number): string {
  const params = new URLSearchParams({ title: title.replace(/ /g, "_"), oldid: String(revId) });
  return `https://en.wikipedia.org/w/index.php?${params.toString()}`;
}

const KEEP_TOGETHER = /(\S+ \d\S*)/g;

/** Wraps word-number pairs so they never break across lines ("Hut 8", "iPhone 18"). */
function keepTogether(title: string): ReactNode {
  return title.split(KEEP_TOGETHER).map((part, i) =>
    /^\S+ \d\S*$/.test(part) ? (
      <span key={i} className="whitespace-nowrap">
        {part}
      </span>
    ) : (
      part
    ),
  );
}

const UTC_TAIL = " UTC";

/** A record date that drops its " UTC" below the md breakpoint. The built-on date in the same row keeps its " UTC". */
function PinnedDate({ value }: { value: string }) {
  const full = formatRecordDate(value);
  if (!full.endsWith(UTC_TAIL)) {
    return full;
  }
  return (
    <>
      {full.slice(0, -UTC_TAIL.length)}
      <span className="max-md:hidden">{UTC_TAIL}</span>
    </>
  );
}

/** The table of stored dossiers: one row per article with its revision, freshness, smallest fitting budget and build date. */
export function DossierTable({ items, loadingRows, className = "" }: DossierTableProps) {
  return (
    <table
      className={`w-full table-fixed border-t-(length:--hairline) border-ink text-13 max-md:table-auto max-md:border-t-0 ${className}`}
    >
      <colgroup className="max-md:hidden">
        <col />
        <col className="w-[160px] lg:w-[250px]" />
        <col className="w-[200px]" />
        <col className="w-[84px]" />
        <col className="w-[80px] max-lg:hidden" />
        <col className="w-[140px] lg:w-[150px]" />
      </colgroup>
      <thead className="max-md:sr-only">
        <tr className="h-8 border-b-(length:--hairline) border-rule-strong text-left text-12 font-normal text-ink-3 pointer-coarse:h-11">
          <th scope="col" className="pr-3 font-normal">
            Article
          </th>
          <th scope="col" className="pr-3 font-normal">
            Revision
          </th>
          <th scope="col" className="pr-3 font-normal">
            Freshness
            <span className="max-md:hidden">
              <InfoDot
                label="About Freshness"
                text="WKE has not seen an edit to this article since the dossier was built, so it cannot say whether the dossier is up to date."
              />
            </span>
          </th>
          <th scope="col" className="pr-3 font-normal">
            Fits in
            <span className="max-md:hidden">
              <InfoDot label="About Fits in" text={FITS_IN_HELP} />
            </span>
          </th>
          <th scope="col" className="pr-3 font-normal max-lg:hidden">
            Sections
          </th>
          <th scope="col" className="font-normal">
            Built on
          </th>
        </tr>
      </thead>
      <tbody className="max-md:block">
        {loadingRows != null
          ? Array.from({ length: loadingRows }, (_unused, row) => (
              <tr
                key={row}
                className="h-10 border-b-(length:--hairline) border-rule"
                aria-hidden="true"
              >
                {Array.from({ length: SKELETON_COLS }, (_unusedCol, col) => (
                  <td
                    key={col}
                    aria-hidden="true"
                    className={col === 4 ? "pr-3 max-lg:hidden" : "pr-3"}
                  >
                    <span className="block h-3 w-4/5 animate-pulse rounded-1 bg-sunken motion-reduce:animate-none" />
                  </td>
                ))}
              </tr>
            ))
          : items.map((item) => {
              const slug = slugify(item.title);
              return (
                <tr
                  key={item.page_id}
                  className="relative h-10 cursor-pointer border-b-(length:--hairline) border-rule pointer-coarse:h-11 max-md:pointer-coarse:h-auto transition-colors duration-(--motion-fast) hover:bg-sunken focus-within:bg-sunken max-md:grid max-md:h-auto max-md:grid-cols-[auto_auto_minmax(0,1fr)] max-md:items-center max-md:gap-x-2 max-md:gap-y-1 max-md:pt-3.5 max-md:pb-3"
                >
                  <td className="overflow-hidden pr-3 max-md:col-span-3 max-md:row-start-1 max-md:overflow-visible max-md:pr-0">
                    <Link
                      to="/t/$slug"
                      params={{ slug }}
                      search={{ budget: item.largest_budget_filled }}
                      title={item.title}
                      className="block truncate text-ink underline decoration-rule-strong decoration-1 underline-offset-[3px] hover:decoration-ink after:absolute after:inset-0 after:content-[''] max-md:text-14"
                    >
                      {keepTogether(item.title)}
                    </Link>
                  </td>
                  {/* On phones this cell dissolves: the revision link takes the third line and the pinned date the right end of the chip line. */}
                  <td className="overflow-hidden text-ellipsis pr-3 text-ink-2 tabular-nums lg:whitespace-nowrap max-md:contents max-md:text-12 max-md:text-ink-3">
                    <a
                      href={oldidUrl(item.title, item.rev_id)}
                      title={`Wikipedia revision ${item.rev_id}, opens en.wikipedia.org`}
                      className="hit-44 relative z-10 inline-flex items-center gap-x-1 text-ink-2 hover:text-ink md:pointer-coarse:min-h-11 max-md:col-span-2 max-md:row-start-3 max-md:justify-self-start"
                    >
                      {item.rev_id}
                      <ExternalLink size={14} strokeWidth={1.6} aria-hidden="true" />
                      <span className="sr-only">opens Wikipedia</span>
                    </a>{" "}
                    <span className="inline-block text-ink-3 max-md:col-start-3 max-md:row-start-2 max-md:justify-self-end max-md:whitespace-nowrap">
                      <PinnedDate value={item.pinned_at} />
                    </span>
                  </td>
                  <td className="pr-3 max-md:col-start-2 max-md:row-start-2 max-md:pr-0">
                    <FreshnessChip
                      state={item.freshness_state}
                      editsSincePin={item.edits_since_pin}
                      showInfo={false}
                      quiet
                      shortOnPhone
                    />
                  </td>
                  <td className="pr-3 max-md:col-start-1 max-md:row-start-2 max-md:pr-0">
                    <Chip variant="built">
                      <span className="mr-1 max-md:inline hidden">Fits in</span>
                      {budgetAlias(item.largest_budget_filled)}
                    </Chip>
                  </td>
                  <td className="pr-3 tabular-nums max-lg:hidden">{item.sections}</td>
                  <td className="text-ink-2 tabular-nums max-md:col-start-3 max-md:row-start-3 max-md:justify-self-end max-md:whitespace-nowrap max-md:text-12 max-md:text-ink-3">
                    <span className="max-md:inline hidden">built on </span>
                    <span className="inline-block">{formatRecordDate(item.built_at)}</span>
                  </td>
                </tr>
              );
            })}
      </tbody>
    </table>
  );
}
