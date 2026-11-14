/** Pure helpers that format numbers, dates and durations for display. */

const GROUPED = new Intl.NumberFormat("en-GB");

const MONTHS_LONG = [
  "January",
  "February",
  "March",
  "April",
  "May",
  "June",
  "July",
  "August",
  "September",
  "October",
  "November",
  "December",
];

/**
 * A time value in any form a caller may hold. null and undefined stand for a value that is not
 * loaded yet or missing from the response.
 */
type DateInput = Date | string | number | null | undefined;

// Returns null for a missing or unparsable value, so a caller can fall back instead of showing
// "NaN" or "Invalid Date".
function toDate(value: DateInput): Date | null {
  if (value == null) {
    return null;
  }
  const d = value instanceof Date ? value : new Date(value);
  return Number.isNaN(d.getTime()) ? null : d;
}

function pad2(n: number): string {
  return String(n).padStart(2, "0");
}

/**
 * Groups thousands with commas, as in "1,284". Revision ids, page ids and years must not go through
 * it.
 */
export function formatNumber(n: number): string {
  return GROUPED.format(n);
}

/** Joins a count and its noun, adding "s" for any count other than 1. */
export function pluralize(n: number, noun: string): string {
  return `${formatNumber(n)} ${noun}${n === 1 ? "" : "s"}`;
}

/**
 * Labels an out-of-date dossier with its edit count. A null or zero count prints "newer revision"
 * instead, because an out-of-date dossier always has a newer revision.
 */
export function staleLabel(n: number | null): string {
  if (n == null || n === 0) {
    return "Out of date: newer revision";
  }
  return `Out of date: ${pluralize(n, "edit")} since built`;
}

/** Formats a signed delta with a "+" or a true minus sign (U+2212). Zero prints as "+0". */
export function formatSignedDelta(n: number): string {
  if (n < 0) {
    return `\u2212${formatNumber(Math.abs(n))}`;
  }
  return `+${formatNumber(n)}`;
}

/**
 * Formats seconds with one decimal below 10 and as whole seconds from 10 up, followed by " s". The
 * value must not be negative.
 */
export function formatDuration(seconds: number): string {
  const tenths = Math.round(seconds * 10) / 10;
  return tenths < 10 ? `${tenths.toFixed(1)} s` : `${Math.round(seconds)} s`;
}

/**
 * Formats the UTC time of day as "HH:MM" with no zone suffix, so a sentence can name the zone once.
 * Returns "" for a missing or invalid value.
 */
function formatUtcClock(value: DateInput): string {
  const d = toDate(value);
  if (d == null) {
    return "";
  }
  return `${pad2(d.getUTCHours())}:${pad2(d.getUTCMinutes())}`;
}

/**
 * Formats the UTC time of day as "HH:MM:SS", for arrivals close enough together that minutes hide
 * their order. Returns "" for a missing or invalid value.
 */
export function formatUtcClockSeconds(value: DateInput): string {
  const d = toDate(value);
  if (d == null) {
    return "";
  }
  return `${formatUtcClock(d)}:${pad2(d.getUTCSeconds())}`;
}

/**
 * Formats the UTC time of day as "HH:MM UTC", for a time shown on its own where no nearby text
 * names the zone. Returns "" for a missing or invalid value.
 */
export function formatUtcTime(value: DateInput): string {
  const clock = formatUtcClock(value);
  return clock === "" ? "" : `${clock} UTC`;
}

/**
 * Says when the most-read list refreshes next, or "Refresh overdue" once that time has passed.
 * Returns "" for a missing or invalid value.
 */
export function formatRefresh(value: DateInput, now: Date = new Date()): string {
  const d = toDate(value);
  if (d == null) {
    return "";
  }
  return d.getTime() <= now.getTime() ? "Refresh overdue" : `Refreshes ${formatUtcTime(d)}`;
}

/**
 * Formats a freshness checked_at for the dossier header. A check from an earlier UTC day includes
 * its date, and a null or invalid value reads "not checked".
 */
export function formatCheckedAt(value: string | null | undefined, now: Date = new Date()): string {
  const time = formatUtcTime(value);
  if (time === "") {
    return "not checked";
  }
  const d = toDate(value);
  return d == null || utcDaysAgo(d, now) === 0
    ? `checked ${time}`
    : `checked ${formatRecordDate(d)}`;
}

/**
 * Formats a UTC date for prose, as "24 September 2026". Returns "" for a missing or invalid value.
 */
export function formatProseDate(value: DateInput): string {
  const d = toDate(value);
  if (d == null) {
    return "";
  }
  return `${d.getUTCDate()} ${MONTHS_LONG[d.getUTCMonth()]} ${d.getUTCFullYear()}`;
}

const DAY_MS = 86_400_000;

// Whole UTC calendar days from `date` to `now`, where 1 means yesterday. Returns null when `date`
// is missing or does not parse.
function utcDaysAgo(date: DateInput, now: Date): number | null {
  const d = toDate(date);
  if (d == null) {
    return null;
  }
  const then = Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), d.getUTCDate());
  const today = Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate());
  return Math.round((today - then) / DAY_MS);
}

/**
 * Says when the most-read snapshot is from, naming its date. The word "yesterday" appears only when
 * the snapshot is exactly one UTC day old.
 */
export function mostReadWhen(date: DateInput, now: Date): string {
  const prose = formatProseDate(date);
  if (prose === "") {
    return "";
  }
  return utcDaysAgo(date, now) === 1 ? `yesterday (${prose} UTC)` : `on ${prose} (UTC)`;
}

/**
 * Returns the note that the most-read snapshot is out of date when it is more than two UTC days
 * old, otherwise null.
 */
export function mostReadStaleNote(date: DateInput, now: Date): string | null {
  const age = utcDaysAgo(date, now);
  if (age == null || age <= 2) {
    return null;
  }
  return `the nightly index has not refreshed since ${formatProseDate(date)}`;
}

/**
 * Formats a UTC date and time for a record value, as "2026-09-24, 18:41 UTC". Returns "" for a
 * missing or invalid value.
 */
export function formatRecordDate(value: DateInput): string {
  const d = toDate(value);
  if (d == null) {
    return "";
  }
  const date = `${d.getUTCFullYear()}-${pad2(d.getUTCMonth() + 1)}-${pad2(d.getUTCDate())}`;
  return `${date}, ${formatUtcTime(d)}`;
}

/**
 * Formats a score range as "low to high", or as one value when both ends print the same at two
 * decimals.
 */
export function formatRange(low: number, high: number): string {
  const a = low.toFixed(2);
  const b = high.toFixed(2);
  return a === b ? a : `${a} to ${b}`;
}

/** Joins numbers or words as a spoken list: "1", "1 and 2" or "1, 2 and 3". */
export function joinList(items: readonly (string | number)[]): string {
  if (items.length <= 1) {
    return items.map(String).join("");
  }
  return `${items.slice(0, -1).join(", ")} and ${items[items.length - 1]}`;
}

/**
 * Returns the note that introduces the links already cited in the text, with "link" agreeing with
 * the count.
 */
export function formatCitedAbove(count: number): string {
  return count === 1
    ? "Cited above: every [n] in the text resolves to this link."
    : `Cited above: every [n] in the text resolves to one of these ${count} links.`;
}

/**
 * States how many of a dossier's sections the model summarised, and how many the pipeline selected,
 * as "3 of 20 sections (3 selected)".
 */
export function formatSummaryScope(done: number, selected: number, sections: number): string {
  return `${formatNumber(done)} of ${pluralize(sections, "section")} (${formatNumber(selected)} selected)`;
}

/**
 * Returns the status-line text for the live edit feed. The state "rate_limited" means the server
 * asks for fewer polls.
 * A disconnect names when the feed was last heard from, if `since` is known.
 */
export function formatLiveEditsStatus(
  state: "connected" | "reconnecting" | "disconnected" | "paused" | "rate_limited",
  since?: DateInput | null,
): string {
  if (state === "rate_limited") {
    return "Live edits paused, retrying shortly";
  }
  if (state === "paused") {
    return "Live edits paused; edits keep counting";
  }
  if (state === "disconnected") {
    const time = since ? formatUtcTime(since) : "";
    return time === "" ? "Live edits disconnected" : `Live edits disconnected since ${time}`;
  }
  return `Live edits ${state}`;
}
