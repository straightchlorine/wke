import type { DossierView } from "../api/dossier";
import type { RevisionPin } from "../api/generated";
import { budgetAlias, type Budget } from "./budget";
import { formatCheckedAt } from "./format";

/** Returns the revision pin of the article the dossier is about: its seed citation, else the first citation. */
export function seedPin(dossier: Pick<DossierView, "citations">): RevisionPin | undefined {
  return (dossier.citations.find((c) => c.role === "seed") ?? dossier.citations[0])?.pin;
}

/** What the source record shows for freshness: the chip's state and the tooltip that explains it. */
export interface FreshnessView {
  state: DossierView["freshness"]["state"];
  /** Undefined when the API has no freshness source, so the chip explains "Not checked" itself. */
  info: string | undefined;
}

/**
 * Returns the freshness the record shows. While the edit feed is disconnected, a watcher-based
 * "fresh" would be a guess, so it shows as unknown and the tooltip says why.
 */
export function freshnessView(
  freshness: DossierView["freshness"],
  editFeedDown: boolean,
): FreshnessView {
  const feedGap = editFeedDown && freshness.source === "watcher";
  const state = feedGap && freshness.state === "fresh" ? "unknown" : freshness.state;
  if (freshness.source === "none") {
    return { state, info: undefined };
  }
  if (feedGap) {
    return {
      state,
      info: "The edit feed is disconnected, so WKE cannot say whether this dossier is up to date.",
    };
  }
  const checked =
    freshness.checked_at == null ? "Not checked yet" : formatCheckedAt(freshness.checked_at);
  const how =
    freshness.source === "poll"
      ? "WKE asks Wikipedia for the newest revision and compares it with the pinned one."
      : "WKE compares the pinned revision with the newest edits it has seen.";
  return {
    state,
    info: `${checked.charAt(0).toUpperCase()}${checked.slice(1)}. ${how} The text below is still the pinned revision.`,
  };
}

/**
 * Returns how many sections the dossier leaves out and a sentence per cause, for the tooltip of the
 * "Left out" row. Titles are joined by semicolons because a title can hold commas.
 */
export function leftOutSummary(
  noProseTitles: readonly string[],
  foldedTitles: readonly string[],
  budget: Budget,
): { count: number; detail: string } {
  const detail = [
    noProseTitles.length > 0
      ? `No prose, so left out (lists and tables are not extracted): ${noProseTitles.join("; ")}.`
      : null,
    foldedTitles.length > 0
      ? `Left out at ${budgetAlias(budget)}: ${foldedTitles.join("; ")}.`
      : null,
  ]
    .filter((part) => part != null)
    .join(" ");
  return { count: noProseTitles.length + foldedTitles.length, detail };
}
