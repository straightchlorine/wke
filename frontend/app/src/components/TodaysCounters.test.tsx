import { beforeEach, describe, expect, it, vi } from "vitest";
import { act, fireEvent, screen, waitFor } from "@testing-library/react";
import type { DossierListItem, TrendingTopic } from "../api/generated";
import { loadDossier } from "../test/fixtures";
import { renderWithRouter } from "../test/renderWithRouter";

const fetchDossierMarkdownText = vi.fn();
vi.mock("../api/dossier", () => ({
  fetchDossierMarkdownText: (...args: unknown[]) => fetchDossierMarkdownText(...args),
}));

const { TodaysCounters } = await import("./TodaysCounters");

const topic: TrendingTopic = {
  rank: 1,
  page_id: 42,
  title: "Mary Magdalene",
  views: 100,
  rev_id: 9,
  dossier_state: "ready",
};
const item: DossierListItem = {
  page_id: 42,
  title: topic.title,
  rev_id: 777,
  pinned_at: "2026-11-01T10:00:00Z",
  freshness_state: "fresh",
  edits_since_pin: 0,
  largest_budget_filled: 8000,
  sections: 3,
  built_at: "2026-11-01T10:00:00Z",
};
const view = loadDossier();

const base = {
  stored: { label: "12", known: true },
  builtToday: 3,
  edits: { value: "5", sub: "in 2 min", unavailable: false },
  top: undefined,
  topUnknown: false,
  budget: 8000 as const,
  onCopy: vi.fn(),
};

function renderCounters(props: Partial<Parameters<typeof TodaysCounters>[0]> = {}) {
  return renderWithRouter(<TodaysCounters {...base} {...props} />, {
    extraRoutes: ["/t/$slug"],
  });
}

describe("TodaysCounters", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("shows the stored and edit figures with their lines", async () => {
    renderCounters();
    expect(await screen.findByText("12")).toBeTruthy();
    expect(screen.getByText("3 built today")).toBeTruthy();
    expect(screen.getByText("5")).toBeTruthy();
    expect(screen.getByText("in 2 min")).toBeTruthy();
  });

  it.each([
    [
      "known figure, no counters",
      { stored: base.stored, builtToday: undefined },
      "built today: unknown",
    ],
    [
      "unknown figure, no counters",
      { stored: { label: "unknown", known: false }, builtToday: undefined },
      null,
    ],
  ])("%s", async (_name, props, line) => {
    renderCounters(props);
    await screen.findByText("None built yet");
    expect(screen.queryByText("built today: unknown") !== null).toBe(line !== null);
  });

  it.each([
    ["a known stored count", { stored: { label: "12", known: true } }, "12", true],
    [
      "a stored count that is unknown",
      { stored: { label: "unknown", known: false } },
      "unknown",
      false,
    ],
    ["an edit count", { edits: { value: "5", sub: "", unavailable: false } }, "5", true],
    [
      "an unavailable edit count",
      { edits: { value: "no edit data", sub: "", unavailable: true } },
      "no edit data",
      false,
    ],
  ])("sets %s in big type only when it is a number", async (_name, props, text, big) => {
    renderCounters(props);
    const value = await screen.findByText(text);
    expect(value.className.includes("text-18")).toBe(big);
  });

  it.each([
    ["no dossier yet", false, "None built yet"],
    ["a failed list", true, "unknown"],
  ])("says what it knows for %s", async (_name, topUnknown, text) => {
    renderCounters({ topUnknown });
    expect(await screen.findByText(text)).toBeTruthy();
    expect(screen.queryByRole("link", { name: topic.title })).toBeNull();
  });

  it("links the top dossier and offers no actions before its stored entry is known", async () => {
    renderCounters({ top: { topic, item: undefined, view: undefined, viewFailed: false } });
    const link = await screen.findByRole("link", { name: topic.title });
    expect(link.getAttribute("href")).toBe("/t/Mary_Magdalene?budget=8000");
    expect(screen.getByText("Revision pending")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Open" })).toBeNull();
  });

  it("opens the top dossier from its Open button", async () => {
    const { router } = renderCounters({ top: { topic, item, view, viewFailed: false } });
    fireEvent.click(await screen.findByRole("button", { name: "Open" }));
    await waitFor(() => expect(router.state.location.pathname).toBe("/t/Mary_Magdalene"));
    expect(router.state.location.search).toEqual({ budget: 8000 });
  });

  it("copies the top dossier as Markdown and says how many tokens it holds", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, "clipboard", { value: { writeText }, configurable: true });
    fetchDossierMarkdownText.mockResolvedValue("# Markdown");
    const onCopy = vi.fn();
    renderCounters({ top: { topic, item, view, viewFailed: false }, onCopy });
    await act(async () => {
      fireEvent.click(await screen.findByRole("button", { name: /^Copy as context/ }));
    });
    expect(fetchDossierMarkdownText).toHaveBeenCalledWith(42, 8000);
    expect(writeText).toHaveBeenCalledWith("# Markdown");
    expect(onCopy).toHaveBeenCalledWith(
      `Copied as markdown, ${view.budget.used_est_tokens.toLocaleString("en-US")} dossier tokens, revision 777`,
    );
  });
});
