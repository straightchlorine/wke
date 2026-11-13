import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, render, screen } from "@testing-library/react";
import type { LiveRow, UseLiveResult } from "../lib/hooks/useLive";
import type { PausedFeed } from "../lib/hooks/usePausedFeed";
import { LEDGER_ROW_PX } from "./Ledger";
import { renderWithRouter } from "../test/renderWithRouter";
import { LedgerPanel, useLedgerSlots, type LedgerPanelProps } from "./LedgerPanel";

const NOW = Date.parse("2026-11-10T12:00:00Z");

function liveRow(title: string, isArrival = true): LiveRow {
  return {
    key: title,
    ts: new Date(NOW - 1000).toISOString(),
    cursor: 1,
    title,
    pageId: 1,
    slug: null,
    byteDelta: 5,
    userKind: "registered",
    runCount: 1,
    isArrival,
  };
}

function live(over: Partial<UseLiveResult> = {}): UseLiveResult {
  return {
    rows: [liveRow("Alpha"), liveRow("Beta", false)],
    editsSeenSincePageLoad: 1,
    loadTime: new Date(NOW - 60_000),
    streamState: "connected",
    streamError: null,
    lastEventAt: null,
    counters: null,
    downSince: null,
    rateLimited: false,
    missedWhilePaused: 0,
    overflowCount: 0,
    ...over,
  };
}

const running: PausedFeed = { paused: false, pausedSince: null, resumedAt: null, toggle: vi.fn() };

function renderPanel(props: { live?: Partial<UseLiveResult>; feed?: Partial<PausedFeed> } = {}) {
  const panel: LedgerPanelProps = {
    live: live(props.live),
    feed: { ...running, ...props.feed },
    slots: 9,
    bodyRef: { current: null },
    now: NOW,
    budget: 8000,
    freshPageIds: new Set(),
    onHighlight: vi.fn(),
  };
  return renderWithRouter(<LedgerPanel {...panel} />, { extraRoutes: ["/t/$slug"] });
}

const announcing = (over: Partial<UseLiveResult>) => (
  <LedgerPanel
    live={live({ rows: [], ...over })}
    feed={running}
    slots={9}
    bodyRef={{ current: null }}
    now={NOW}
    budget={8000}
    freshPageIds={new Set()}
    onHighlight={vi.fn()}
  />
);

describe("LedgerPanel", () => {
  afterEach(() => {
    document.getElementById("live-region")?.remove();
  });

  it("puts a plain count beside the title and shows the rows", async () => {
    renderPanel();
    const status = await screen.findByText("last 2");
    expect(status.hasAttribute("data-ledger-status")).toBe(true);
    expect(screen.getByText("Alpha")).toBeTruthy();
  });

  it("puts any other state of the feed in the table as a notice, not beside the title", async () => {
    renderPanel({ feed: { paused: true } });
    expect(await screen.findByText("Live edits paused")).toBeTruthy();
    expect(document.querySelector("[data-ledger-panel] span[data-ledger-status]")).toBeNull();
  });

  it("says a rate limit in one line when there are no rows yet", async () => {
    renderPanel({ live: { rateLimited: true, rows: [] } });
    const line = await screen.findByText("Live edits paused, retrying shortly");
    expect(line.tagName).toBe("P");
    expect(line.hasAttribute("data-ledger-status")).toBe(true);
  });

  it("keeps the rows and adds the notice while a rate limit has rows to show", async () => {
    renderPanel({ live: { rateLimited: true } });
    expect(await screen.findByText("Alpha")).toBeTruthy();
    expect(screen.getByText("Live edits paused, retrying shortly").tagName).not.toBe("P");
  });

  it.each([
    ["a connected feed", {}, false],
    ["a down feed", { streamState: "down" as const }, true],
    ["a disconnected feed", { streamState: "disconnected" as const }, true],
    ["a rate limit", { rateLimited: true }, true],
  ])("disables the pause button for %s: %s", async (_name, over, disabled) => {
    renderPanel({ live: over });
    const button = await screen.findByRole("button", { name: /Pause|Resume/ });
    expect(button.getAttribute("aria-disabled") === "true").toBe(disabled);
  });

  it("tells the reader how many edits arrived while paused", async () => {
    renderPanel({ feed: { paused: true }, live: { missedWhilePaused: 3 } });
    const button = await screen.findByRole("button", { name: /Resume/ });
    expect(button.getAttribute("title")).toBe("3 edits arrived while paused");
  });

  it("reports the edits the table could not show in the footer", async () => {
    renderPanel({ live: { overflowCount: 1234 } });
    expect(await screen.findByText("+1,234 more since the last update")).toBeTruthy();
  });

  it("announces the feed's state when it changes, and only then", () => {
    const region = document.createElement("div");
    region.id = "live-region";
    document.body.append(region);
    const { rerender } = render(announcing({ streamState: "reconnecting" }));
    expect(region.textContent).toBe("Live edits reconnecting");

    region.textContent = "";
    rerender(announcing({ streamState: "reconnecting", lastEventAt: "2026-11-10T11:59:00Z" }));
    expect(region.textContent).toBe("");

    rerender(announcing({ streamState: "connected" }));
    expect(region.textContent).toBe("Live edits connected");
  });
});

function Probe() {
  const { bodyRef, slots } = useLedgerSlots();
  return (
    <div ref={bodyRef} data-testid="body">
      {slots}
    </div>
  );
}

describe("useLedgerSlots", () => {
  let observed: (() => void) | null = null;
  let height = 0;

  beforeEach(() => {
    observed = null;
    height = 0;
    vi.stubGlobal(
      "ResizeObserver",
      class {
        constructor(callback: () => void) {
          observed = callback;
        }
        observe() {}
        disconnect() {}
      },
    );
    vi.spyOn(HTMLElement.prototype, "clientHeight", "get").mockImplementation(() => height);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("counts the slots from the body's height and again when it resizes", () => {
    height = LEDGER_ROW_PX * 12;
    render(<Probe />);
    expect(screen.getByTestId("body").textContent).toBe("12");
    height = LEDGER_ROW_PX * 20;
    act(() => observed?.());
    expect(screen.getByTestId("body").textContent).toBe("20");
  });
});
