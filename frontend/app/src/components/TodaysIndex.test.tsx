import { describe, expect, it, vi } from "vitest";
import { fireEvent, screen, waitFor } from "@testing-library/react";
import type { DossierListItem, TrendingSnapshot, TrendingTopic } from "../api/generated";
import { renderWithRouter } from "../test/renderWithRouter";
import { TodaysIndex, type TodaysIndexProps } from "./TodaysIndex";

const NOW = Date.parse("2026-11-10T12:00:00Z");

function topic(n: number, over: Partial<TrendingTopic> = {}): TrendingTopic {
  return {
    rank: n,
    page_id: n,
    title: `Topic ${n}`,
    views: 1000 - n,
    rev_id: n,
    dossier_state: "none",
    ...over,
  };
}

function snapshot(topics: TrendingTopic[]): TrendingSnapshot {
  return {
    schema_version: "1",
    date: "2026-11-09",
    source: "wikifeeds_mostread",
    generated_at: "2026-11-10T03:00:00Z",
    topics,
    edges: [],
  };
}

function storedItem(pageId: number): DossierListItem {
  return {
    page_id: pageId,
    title: `Topic ${pageId}`,
    rev_id: 1,
    pinned_at: "2026-11-01T00:00:00Z",
    freshness_state: "fresh",
    edits_since_pin: 0,
    largest_budget_filled: 8000,
    sections: 3,
    built_at: "2026-11-01T00:00:00Z",
  };
}

function renderIndex(props: Partial<TodaysIndexProps> & { count?: number } = {}) {
  const { count = 3, ...rest } = props;
  const topics = Array.from({ length: count }, (_, i) => topic(i + 1));
  const all: TodaysIndexProps = {
    trending: snapshot(topics),
    topics,
    isLoading: false,
    isError: false,
    dossierByPageId: new Map(),
    budget: 8000,
    editsUnavailable: false,
    freshPageIds: new Set(),
    mostReadOn: "yesterday (2026-11-09)",
    now: NOW,
    onHighlight: vi.fn(),
    ...rest,
  };
  return renderWithRouter(<TodaysIndex {...all} />, { extraRoutes: ["/t/$slug"] });
}

describe("TodaysIndex", () => {
  it("heads the list with the day and counts what is built and queued", async () => {
    const topics = [
      topic(1, { dossier_state: "ready" }),
      topic(2, { dossier_state: "partial" }),
      topic(3, { dossier_state: "building" }),
    ];
    renderIndex({ trending: snapshot(topics), topics });
    expect(
      await screen.findByRole("heading", { name: "Most read yesterday (2026-11-09)" }),
    ).toBeTruthy();
    expect(screen.getByText(/2 of 3 built, 1 queued\./)).toBeTruthy();
  });

  it("shows the first page, then every topic after Show all, and moves focus to the first new row", async () => {
    renderIndex({ count: 25 });
    expect(await screen.findAllByRole("link", { name: /^Topic / })).toHaveLength(20);
    fireEvent.click(screen.getByRole("button", { name: "Show all 25" }));
    expect(screen.getAllByRole("link", { name: /^Topic / })).toHaveLength(25);
    expect(screen.queryByRole("button", { name: /Show all/ })).toBeNull();
    await waitFor(() =>
      expect(document.activeElement).toBe(screen.getByRole("link", { name: /^Topic 21/ })),
    );
  });

  it("offers no Show all for one page", async () => {
    renderIndex({ count: 20 });
    await screen.findAllByRole("link", { name: /^Topic / });
    expect(screen.queryByRole("button", { name: /Show all/ })).toBeNull();
  });

  it("shows a budget badge for a built topic only once its stored entry is known", async () => {
    const topics = [topic(1, { dossier_state: "ready" }), topic(2, { dossier_state: "ready" })];
    renderIndex({
      trending: snapshot(topics),
      topics,
      dossierByPageId: new Map([[1, storedItem(1)]]),
    });
    await screen.findAllByRole("link", { name: /^Topic / });
    const chips = [...document.querySelectorAll("[data-entry-chip]")].map((el) => el.textContent);
    expect(chips).toEqual(["Fits in 8k", ""]);
  });

  it("names the build state of a topic that is not built", async () => {
    renderIndex({
      trending: snapshot([topic(1, { dossier_state: "building" })]),
      topics: [topic(1, { dossier_state: "building" })],
    });
    expect(await screen.findByText("Building")).toBeTruthy();
  });

  it("says no edit data for every topic while the edit feed is unavailable", async () => {
    renderIndex({ editsUnavailable: true });
    expect(await screen.findAllByText("no edit data")).toHaveLength(3);
  });

  it("shows twenty hidden skeleton rows and no message or links while loading", async () => {
    const { container } = renderIndex({ trending: undefined, isLoading: true, topics: [] });
    await screen.findByRole("heading", { name: "Most-read articles" });
    const list = container.querySelector("ol[aria-hidden='true']");
    expect(list?.querySelectorAll("li")).toHaveLength(20);
    expect(screen.queryByText(/No index yet/)).toBeNull();
    expect(screen.queryAllByRole("link")).toHaveLength(0);
  });

  it.each([
    [
      "an error with nothing to show",
      { trending: undefined, isError: true },
      "Today's index is unavailable",
    ],
    [
      "no snapshot yet",
      { trending: undefined },
      "No index yet. The nightly job builds it at 03:00 UTC.",
    ],
  ])("shows no rows while %s", async (_name, props, text) => {
    renderIndex({ ...props, topics: [] });
    await screen.findByRole("heading", { name: "Most-read articles" });
    expect(screen.queryAllByRole("link")).toHaveLength(0);
    expect(screen.getByText(text)).toBeTruthy();
  });

  it("keeps the list and says so when a refresh failed", async () => {
    renderIndex({ isError: true });
    expect(
      await screen.findByText(/Could not reach the server; showing the list loaded earlier\./),
    ).toBeTruthy();
    expect(screen.getAllByRole("link", { name: /^Topic / })).toHaveLength(3);
  });

  it("reports the hovered or focused row's page id and null when it is left", async () => {
    const onHighlight = vi.fn();
    renderIndex({ onHighlight });
    const link = await screen.findByRole("link", { name: /^Topic 2/ });
    fireEvent.mouseEnter(link);
    fireEvent.mouseLeave(link);
    fireEvent.focus(link);
    fireEvent.blur(link);
    expect(onHighlight.mock.calls).toEqual([[2], [null], [2], [null]]);
  });
});
