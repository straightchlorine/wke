import { describe, expect, it } from "vitest";
import {
  formatRange,
  formatCitedAbove,
  formatRefresh,
  formatDuration,
  formatLiveEditsStatus,
  formatSummaryScope,
  joinList,
  formatNumber,
  pluralize,
  formatProseDate,
  formatRecordDate,
  formatSignedDelta,
  mostReadStaleNote,
  mostReadWhen,
  formatUtcClockSeconds,
  formatUtcTime,
  formatCheckedAt,
  staleLabel,
} from "./format";

describe("formatNumber", () => {
  it("groups thousands", () => {
    expect(formatNumber(1284)).toBe("1,284");
    expect(formatNumber(7842)).toBe("7,842");
  });
});

describe("pluralize", () => {
  it.each<[number, string]>([
    [0, "0 edits"],
    [1, "1 edit"],
    [2, "2 edits"],
    [1234, "1,234 edits"],
  ])("pluralizes %i", (n, text) => {
    expect(pluralize(n, "edit")).toBe(text);
  });
});

describe("staleLabel", () => {
  it("names the newer revision when the edit count is unknown or 0", () => {
    expect(staleLabel(null)).toBe("Out of date: newer revision");
    expect(staleLabel(0)).toBe("Out of date: newer revision");
  });

  it("counts edits with the right plural", () => {
    expect(staleLabel(1)).toBe("Out of date: 1 edit since built");
    expect(staleLabel(1234)).toBe("Out of date: 1,234 edits since built");
  });
});

describe("formatSignedDelta", () => {
  it("adds a plus sign and groups a positive delta", () => {
    expect(formatSignedDelta(412)).toBe("+412");
  });
  it("uses a true minus sign for a negative delta", () => {
    expect(formatSignedDelta(-379)).toBe("\u2212379");
  });
  it("treats zero as positive", () => {
    expect(formatSignedDelta(0)).toBe("+0");
  });
});

describe("formatDuration", () => {
  it.each<[number, string]>([
    [1.4, "1.4 s"],
    [9.94, "9.9 s"],
    [9.96, "10 s"],
    [10, "10 s"],
    [10.6, "11 s"],
    [11, "11 s"],
  ])("formats %d seconds as %s", (seconds, text) => {
    expect(formatDuration(seconds)).toBe(text);
  });
});

describe("UTC time formatting", () => {
  const instant = "2026-09-25T16:22:00Z";

  it("formats the clock with a UTC suffix", () => {
    expect(formatUtcTime(instant)).toBe("16:22 UTC");
  });

  it("formats a record date", () => {
    expect(formatRecordDate("2026-09-24T18:41:00Z")).toBe("2026-09-24, 18:41 UTC");
  });

  it("formats a prose date", () => {
    expect(formatProseDate("2026-09-24T00:00:00Z")).toBe("24 September 2026");
  });

  it("formats a UTC clock with seconds", () => {
    expect(formatUtcClockSeconds("2026-09-24T18:41:07Z")).toBe("18:41:07");
  });

  it("returns an empty string for a missing or invalid value, never NaN", () => {
    expect(formatProseDate(undefined)).toBe("");
    expect(formatProseDate(null)).toBe("");
    expect(formatProseDate("not a date")).toBe("");
    expect(formatUtcClockSeconds(undefined)).toBe("");
    expect(formatUtcTime(undefined)).toBe("");
    expect(formatRecordDate(undefined)).toBe("");
  });
});

describe("mostReadWhen", () => {
  const now = new Date("2026-09-29T00:30:00Z");

  it("says yesterday only for a snapshot exactly one UTC day old", () => {
    expect(mostReadWhen("2026-09-28", now)).toBe("yesterday (28 September 2026 UTC)");
  });

  it("names the date for an older snapshot", () => {
    expect(mostReadWhen("2026-09-27", now)).toBe("on 27 September 2026 (UTC)");
  });

  it("names the date for a snapshot dated today", () => {
    expect(mostReadWhen("2026-09-29", now)).toBe("on 29 September 2026 (UTC)");
  });

  it("counts UTC days across a month boundary", () => {
    expect(mostReadWhen("2026-08-31", new Date("2026-09-01T23:59:00Z"))).toBe(
      "yesterday (31 August 2026 UTC)",
    );
  });

  it("returns an empty string for a missing date", () => {
    expect(mostReadWhen(undefined, now)).toBe("");
  });
});

describe("mostReadStaleNote", () => {
  const now = new Date("2026-09-29T12:00:00Z");

  it("is silent up to two days old", () => {
    expect(mostReadStaleNote("2026-09-28", now)).toBeNull();
    expect(mostReadStaleNote("2026-09-27", now)).toBeNull();
  });

  it("names the date once the snapshot is older than two days", () => {
    expect(mostReadStaleNote("2026-09-26", now)).toBe(
      "the nightly index has not refreshed since 26 September 2026",
    );
  });

  it("is silent for a missing date", () => {
    expect(mostReadStaleNote(null, now)).toBeNull();
  });
});

describe("formatCheckedAt", () => {
  const now = new Date("2026-10-02T09:00:00Z");

  it("formats a check from today (UTC) as a UTC clock", () => {
    expect(formatCheckedAt("2026-10-02T03:51:00Z", now)).toBe("checked 03:51 UTC");
  });

  it("names the date when the check is from an earlier UTC day", () => {
    expect(formatCheckedAt("2026-09-30T03:51:00Z", now)).toBe("checked 2026-09-30, 03:51 UTC");
    expect(formatCheckedAt("2026-10-01T23:59:00Z", now)).toBe("checked 2026-10-01, 23:59 UTC");
  });

  it("compares UTC days, not local ones", () => {
    expect(formatCheckedAt("2026-10-02T00:05:00Z", new Date("2026-10-02T23:55:00Z"))).toBe(
      "checked 00:05 UTC",
    );
  });

  it("says not checked for null, missing or invalid, never Invalid Date or empty", () => {
    for (const value of [null, undefined, "", "not a date"]) {
      const text = formatCheckedAt(value);
      expect(text).toBe("not checked");
      expect(text).not.toMatch(/Invalid|NaN/);
    }
  });
});

describe("joinList", () => {
  it("reads one, two and three items as prose", () => {
    expect(joinList([1])).toBe("1");
    expect(joinList([1, 2])).toBe("1 and 2");
    expect(joinList([1, 2, 3])).toBe("1, 2 and 3");
    expect(joinList([])).toBe("");
  });
});

describe("formatCitedAbove", () => {
  it("agrees the count with its noun", () => {
    expect(formatCitedAbove(1)).toBe("Cited above: every [n] in the text resolves to this link.");
    expect(formatCitedAbove(4)).toBe(
      "Cited above: every [n] in the text resolves to one of these 4 links.",
    );
  });
});

describe("formatSummaryScope", () => {
  it("says how many of the dossier's sections the model summarised", () => {
    expect(formatSummaryScope(3, 3, 20)).toBe("3 of 20 sections (3 selected)");
    expect(formatSummaryScope(2, 3, 20)).toBe("2 of 20 sections (3 selected)");
    expect(formatSummaryScope(1, 1, 1)).toBe("1 of 1 section (1 selected)");
  });
});

describe("formatLiveEditsStatus", () => {
  it("never names the stream", () => {
    expect(formatLiveEditsStatus("connected")).toBe("Live edits connected");
    expect(formatLiveEditsStatus("reconnecting")).toBe("Live edits reconnecting");
    expect(formatLiveEditsStatus("paused")).toBe("Live edits paused; edits keep counting");
  });

  it("gives the UTC time a disconnect began when known", () => {
    expect(formatLiveEditsStatus("disconnected", "2026-09-30T13:54:10Z")).toBe(
      "Live edits disconnected since 13:54 UTC",
    );
    expect(formatLiveEditsStatus("disconnected", null)).toBe("Live edits disconnected");
    expect(formatLiveEditsStatus("disconnected", "not a date")).toBe("Live edits disconnected");
  });
});

describe("formatRange", () => {
  it("prints one value when both ends agree to two decimals", () => {
    expect(formatRange(0.6, 0.6)).toBe("0.60");
    expect(formatRange(0.601, 0.604)).toBe("0.60");
  });

  it("prints a range otherwise", () => {
    expect(formatRange(0.53, 0.64)).toBe("0.53 to 0.64");
  });
});

describe("formatRefresh", () => {
  const now = new Date("2026-10-04T07:20:00Z");

  it("names the next refresh time while it is ahead", () => {
    expect(formatRefresh("2026-10-05T03:00:00Z", now)).toBe("Refreshes 03:00 UTC");
  });

  it("says the refresh is overdue once the time has passed", () => {
    expect(formatRefresh("2026-10-04T03:00:00Z", now)).toBe("Refresh overdue");
    expect(formatRefresh("2026-10-04T07:20:00Z", now)).toBe("Refresh overdue");
  });

  it("is empty without a usable instant", () => {
    expect(formatRefresh(null, now)).toBe("");
    expect(formatRefresh("not a date", now)).toBe("");
  });
});
