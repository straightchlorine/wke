import { describe, expect, it } from "vitest";
import { screen } from "@testing-library/react";
import { renderWithRouter } from "../test/renderWithRouter";
import {
  Ledger,
  LEDGER_FIXED_SLOTS,
  LEDGER_ROW_PX,
  ledgerSlotsFor,
  type LedgerProps,
  type LedgerRowProps,
} from "./Ledger";

function row(subject: string, extra: Partial<LedgerRowProps> = {}): LedgerRowProps {
  return {
    ts: "2026-11-10T12:03:04Z",
    subject,
    budget: 8000,
    byteDelta: 12,
    userKind: "bot",
    ...extra,
  };
}

function rows(count: number): LedgerRowProps[] {
  return Array.from({ length: count }, (_, i) => row(`Page ${i}`));
}

function renderLedger(props: Partial<LedgerProps> = {}) {
  return renderWithRouter(<Ledger rows={[]} {...props} />, { extraRoutes: ["/t/$slug"] });
}

function bodyRows(container: HTMLElement) {
  return container.querySelectorAll("tbody tr");
}

describe("ledgerSlotsFor", () => {
  it.each([
    ["a tall panel", LEDGER_ROW_PX * 12 + 5, 12],
    ["an exact multiple", LEDGER_ROW_PX * 8, 8],
    ["a short panel", LEDGER_ROW_PX * 2, LEDGER_FIXED_SLOTS + 3],
    ["no room", 0, LEDGER_FIXED_SLOTS + 3],
  ])("counts the slots of %s", (_name, height, slots) => {
    expect(ledgerSlotsFor(height)).toBe(slots);
  });
});

describe("Ledger", () => {
  it("is as tall as its slots with no edits, a full feed or a paused one", async () => {
    const empty = renderLedger({ slots: 9, markerLabel: "listening", moreCount: 4 });
    await screen.findByText("listening");
    expect(bodyRows(empty.container)).toHaveLength(9);
    empty.unmount();

    const full = renderLedger({ rows: rows(30), slots: 9, markerLabel: "listening", moreCount: 4 });
    await screen.findByText("listening");
    expect(bodyRows(full.container)).toHaveLength(9);
    full.unmount();

    const paused = renderLedger({
      rows: rows(30),
      slots: 9,
      markerLabel: "listening",
      notice: "Live edits paused",
    });
    await screen.findByText("Live edits paused");
    expect(bodyRows(paused.container)).toHaveLength(9);
  });

  it.each([
    ["nothing besides edits", {}, 6],
    ["a marker", { markerLabel: "m" }, 5],
    ["a marker and a notice", { markerLabel: "m", notice: "n" }, 4],
    ["all three extra rows", { markerLabel: "m", notice: "n", moreCount: 2 }, 3],
  ])("leaves the remaining slots to edits with %s", async (_name, extra, edits) => {
    const { container } = renderLedger({ rows: rows(20), slots: 6, ...extra });
    await screen.findByText("Page 0");
    expect(container.querySelectorAll("tbody tr:not([aria-hidden])")).toHaveLength(6);
    expect(screen.getAllByText(/^Page \d+$/)).toHaveLength(edits);
  });

  it("always shows one edit row, so too few slots make it taller", async () => {
    const { container } = renderLedger({
      rows: rows(5),
      slots: 2,
      markerLabel: "m",
      notice: "n",
      moreCount: 1,
    });
    await screen.findByText("Page 0");
    expect(screen.getAllByText(/^Page \d+$/)).toHaveLength(1);
    expect(bodyRows(container)).toHaveLength(4);
  });

  it("puts the marker after the first markerIndex edits and the more row before it", async () => {
    const { container } = renderLedger({
      rows: rows(4),
      slots: 9,
      markerLabel: "listening",
      earlierLabel: "earlier",
      moreCount: 3,
      markerIndex: 2,
    });
    await screen.findByText("listening");
    const texts = Array.from(bodyRows(container), (tr) => tr.textContent?.replace(/\u00a0/g, ""));
    expect(texts.slice(0, 5)).toEqual([
      expect.stringContaining("Page 0"),
      expect.stringContaining("Page 1"),
      "+3 more edits not shown",
      "listeningearlier",
      expect.stringContaining("Page 2"),
    ]);
  });

  it("shows the earlier label only when edits follow the marker", async () => {
    const { container } = renderLedger({
      rows: rows(2),
      markerLabel: "listening",
      earlierLabel: "earlier",
      markerIndex: 2,
    });
    await screen.findByText("listening");
    expect(container.textContent).not.toContain("earlier");
  });

  it("sets the row height from LEDGER_ROW_PX", async () => {
    const { container } = renderLedger();
    await screen.findByRole("table", { name: "Edits as they land, times UTC", hidden: true });
    expect(
      container.querySelector<HTMLElement>("table")?.style.getPropertyValue("--ledger-row"),
    ).toBe(`${LEDGER_ROW_PX}px`);
  });

  it("links an edit with a slug to its dossier at the budget, and leaves others as text", async () => {
    renderLedger({
      rows: [row("Alan Turing", { slug: "Alan_Turing", budget: 2000 }), row("No dossier")],
    });
    const link = await screen.findByRole("link", { name: "Alan Turing" });
    expect(link.getAttribute("href")).toBe("/t/Alan_Turing?budget=2000");
    expect(screen.queryByRole("link", { name: "No dossier" })).toBeNull();
    expect(screen.getByText("No dossier")).toBeTruthy();
  });

  it.each([
    ["with a link", "Alan"],
    ["without a link", undefined],
  ])("shows the merged-edit count of a collapsed row %s", async (_name, slug) => {
    renderLedger({ rows: [row("Alan", { slug, runCount: 3 })] });
    expect(await screen.findByText("x3")).toBeTruthy();
  });

  it.each(["registered", "anonymous", "bot"] as const)("names the %s editor kind", async (kind) => {
    renderLedger({ rows: [row("Alan", { userKind: kind })] });
    expect((await screen.findByText(kind)).tagName).toBe("TD");
  });

  it("shows the net delta of a collapsed row, and a dash when there is none", async () => {
    renderLedger({
      rows: [row("Alan", { runCount: 3, byteDelta: -40 }), row("Bo", { byteDelta: null })],
    });
    expect(await screen.findByText("net \u221240")).toBeTruthy();
    expect(screen.getByText("-")).toBeTruthy();
  });
});
