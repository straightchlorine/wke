import type { Budget, DossierListItem, ListDossiersResponse } from "../api/generated";
import { DOSSIERS_LIST_LIMIT } from "../api/queries";
import { formatNumber } from "./format";

/** The figure of the stored-dossiers counter. `known` is false while it loads or after a failed request. */
export function storedDossiersCounter(
  list: Pick<ListDossiersResponse, "items" | "next_cursor"> | undefined,
  failed: boolean,
): { label: string; known: boolean } {
  if (list) {
    return {
      label: list.next_cursor != null ? `${DOSSIERS_LIST_LIMIT}+` : formatNumber(list.items.length),
      known: true,
    };
  }
  return { label: failed ? "unknown" : "...", known: false };
}

/**
 * Returns the tooltip of the top dossier's pin date: its revision and how much of the budget it uses.
 * `used` is undefined until that dossier has loaded. If it failed to load, `usedFailed` leaves out the "tokens pending" note.
 */
export function topDossierTip(
  item: Pick<DossierListItem, "rev_id">,
  used: Pick<Budget, "used_est_tokens" | "requested"> | undefined,
  usedFailed: boolean,
): string {
  const tokens = used
    ? `, ${formatNumber(used.used_est_tokens)} of ${formatNumber(used.requested)} tokens`
    : usedFailed
      ? ""
      : ", tokens pending";
  return `Revision ${item.rev_id}${tokens}`;
}

/** Returns the toast text after the top dossier was copied as Markdown. */
export function copyAsContextMessage(
  used: Pick<Budget, "used_est_tokens"> | undefined,
  item: Pick<DossierListItem, "rev_id"> | undefined,
): string {
  return used && item
    ? `Copied as markdown, ${formatNumber(used.used_est_tokens)} dossier tokens, revision ${item.rev_id}`
    : "Copied as context";
}
