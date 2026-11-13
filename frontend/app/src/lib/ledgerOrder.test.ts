import { describe, expect, it } from "vitest";
import { newestOfBurst, orderLedgerRows } from "./ledgerOrder";

const row = (id: string, ts: string, cursor: number, isArrival: boolean) => ({
  id,
  ts,
  cursor,
  isArrival,
});

describe("orderLedgerRows", () => {
  it("lists live arrivals first, newest first, then replayed rows newest first", () => {
    const ordered = orderLedgerRows([
      row("replay-old", "2026-09-30T09:00:00Z", 1, false),
      row("live-old", "2026-09-30T09:01:00Z", 3, true),
      row("replay-new", "2026-09-30T09:00:30Z", 2, false),
      row("live-new", "2026-09-30T09:01:30Z", 4, true),
    ]);
    expect(ordered.map((r) => r.id)).toEqual(["live-new", "live-old", "replay-new", "replay-old"]);
  });

  it("breaks a same-second tie by cursor, highest first", () => {
    const ordered = orderLedgerRows([
      row("a", "2026-09-30T09:00:00Z", 5, true),
      row("b", "2026-09-30T09:00:00Z", 6, true),
    ]);
    expect(ordered.map((r) => r.id)).toEqual(["b", "a"]);
  });

  it("keeps a replayed row below a live one even when its timestamp is later", () => {
    const ordered = orderLedgerRows([
      row("replay", "2026-09-30T09:05:00Z", 9, false),
      row("live", "2026-09-30T09:00:00Z", 1, true),
    ]);
    expect(ordered.map((r) => r.id)).toEqual(["live", "replay"]);
  });

  it("does not change its input", () => {
    const input = [
      row("a", "2026-09-30T09:00:00Z", 1, false),
      row("b", "2026-09-30T09:01:00Z", 2, true),
    ];
    orderLedgerRows(input);
    expect(input.map((r) => r.id)).toEqual(["a", "b"]);
  });
});

describe("newestOfBurst", () => {
  it("drops the oldest events of a burst", () => {
    expect(newestOfBurst([1, 2, 3, 4, 5], 3)).toEqual([3, 4, 5]);
  });

  it("keeps a short burst whole", () => {
    expect(newestOfBurst([1, 2], 3)).toEqual([1, 2]);
    expect(newestOfBurst([], 3)).toEqual([]);
  });
});
