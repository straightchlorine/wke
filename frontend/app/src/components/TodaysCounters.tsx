import { Link } from "@tanstack/react-router";
import type { DossierListItem, TrendingTopic } from "../api/generated";
import { fetchDossierMarkdownText, type DossierView } from "../api/dossier";
import { budgetAlias, type Budget } from "../lib/budget";
import { copyAsContextMessage, topDossierTip } from "../lib/counters";
import { formatNumber, formatRecordDate } from "../lib/format";
import { useOpenDossier } from "../lib/hooks/useOpenDossier";
import { slugify } from "../lib/slug";
import { Button } from "./Button";
import { Chip, FreshnessChip } from "./Chip";
import { CopyButton } from "./CopyButton";
import { InfoDot } from "./InfoDot";
import { Record } from "./Record";

/** The most-read topic that has a dossier, with what is known about that dossier. */
export interface TopDossier {
  topic: TrendingTopic;
  /** Its stored entry; undefined until the list of stored dossiers has loaded. */
  item: DossierListItem | undefined;
  /** The dossier at the current budget; undefined until it has loaded. */
  view: DossierView | undefined;
  viewFailed: boolean;
}

export interface TodaysCountersProps {
  /** The stored-dossiers figure. `known` is false while it loads or after a failed request. */
  stored: { label: string; known: boolean };
  /** How many dossiers were built today; undefined while the live feed has sent no counters. */
  builtToday: number | undefined;
  edits: { value: string; sub: string; unavailable: boolean };
  /** Undefined when no topic of today's index has a dossier. */
  top: TopDossier | undefined;
  /** True when the lists that decide the top dossier failed to load, so "none" would be a guess. */
  topUnknown: boolean;
  budget: Budget;
  /** Receives the message of the copy button after a successful copy. */
  onCopy: (message: string) => void;
}

function topDossierRow({
  top,
  topUnknown,
  budget,
  onOpen,
  onCopy,
}: Pick<TodaysCountersProps, "top" | "topUnknown" | "budget" | "onCopy"> & {
  onOpen: (slug: string) => void;
}) {
  const topic = top?.topic;
  const item = top?.item;
  const view = top?.view;
  return {
    label: (
      <span>
        Top dossier today
        <InfoDot
          text="The most-read article in today's index that already has a dossier."
          label="About Top dossier today"
        />
      </span>
    ),
    value: topic ? (
      <Link
        to="/t/$slug"
        params={{ slug: slugify(topic.title) }}
        search={{ budget }}
        title={topic.title}
        className="underline decoration-rule-strong decoration-1 underline-offset-[3px] hover:decoration-ink [@media(pointer:coarse)]:-my-3.5 [@media(pointer:coarse)]:inline-block [@media(pointer:coarse)]:py-3.5"
      >
        {topic.title}
      </Link>
    ) : topUnknown ? (
      "unknown"
    ) : (
      "None built yet"
    ),
    title: topic?.title,
    size: topic ? ("name" as const) : ("normal" as const),
    sub:
      item && topic ? (
        <InfoDot text={topDossierTip(item, view?.budget, top?.viewFailed ?? false)}>
          {`pinned ${formatRecordDate(item.pinned_at)}`}
        </InfoDot>
      ) : topic ? (
        "Revision pending"
      ) : (
        ""
      ),
    below:
      item && topic ? (
        <div
          data-top-dossier=""
          className="mt-2 flex flex-wrap items-center justify-start gap-2 @max-[379px]:[&>*]:px-2.5"
        >
          <Chip variant="built" control>
            Fits in {budgetAlias(item.largest_budget_filled)}
          </Chip>
          <FreshnessChip
            control
            state={item.freshness_state}
            editsSincePin={item.edits_since_pin}
          />
          <Button variant="secondary" onClick={() => onOpen(slugify(topic.title))}>
            Open
          </Button>
          <CopyButton
            id="context"
            variant="secondary"
            getText={() => fetchDossierMarkdownText(topic.page_id, budget)}
            message={copyAsContextMessage(view?.budget, item)}
            fetchFailedMessage="Copy failed; try Open instead"
            onCopy={onCopy}
          >
            {(copied) => (copied ? "Copied" : "Copy as context")}
          </CopyButton>
        </div>
      ) : undefined,
  };
}

/** The "Today's counters" record: stored dossiers, edits seen since the page loaded, and the top dossier with its actions. */
export function TodaysCounters({
  stored,
  builtToday,
  edits,
  top,
  topUnknown,
  budget,
  onCopy,
}: TodaysCountersProps) {
  const openDossier = useOpenDossier(budget);
  return (
    <Record
      className="mt-6 lg:mt-0"
      label="Today's counters"
      lines
      rows={[
        {
          label: (
            <span>
              Dossiers stored
              <InfoDot
                text="All dossiers stored right now, and how many of them were built today (UTC)."
                label="About Dossiers stored"
              />
            </span>
          ),
          value: stored.label,
          size: stored.known ? "big" : "normal",
          // With no counters the line says so, unless the value above already says "unknown".
          sub:
            builtToday != null
              ? `${formatNumber(builtToday)} built today`
              : stored.known
                ? "built today: unknown"
                : "",
        },
        {
          label: (
            <span>
              Edits seen since page load
              <InfoDot
                text="English Wikipedia edits seen since you opened this page, from a sample of all edits, not only edits to tracked articles."
                label="About Edits seen since page load"
              />
            </span>
          ),
          value: edits.value,
          size: edits.unavailable ? "normal" : "big",
          sub: edits.sub,
        },
        topDossierRow({ top, topUnknown, budget, onOpen: openDossier, onCopy }),
      ]}
    />
  );
}
