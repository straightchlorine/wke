import { describe, expect, it, vi } from "vitest";
import { fireEvent, screen } from "@testing-library/react";
import { renderWithRouter } from "../test/renderWithRouter";
import type { ApiError } from "../api/generated";
import { ProblemPanel, type ProblemPanelProps } from "./ProblemPanel";

const problem = (fields: Partial<ApiError>): ApiError => ({
  type: "about:blank",
  title: "Problem",
  status: 500,
  code: "internal",
  request_id: "req-1",
  ...fields,
});

const candidates = [
  { page_id: 1, title: "Mary Magdalene", dossier_state: "none" as const },
  { page_id: 2, title: "Jesus", dossier_state: "ready" as const },
];

function renderPanel(props: Partial<ProblemPanelProps> & { problem: ApiError }) {
  return renderWithRouter(<ProblemPanel budget={8000} onRetry={() => {}} {...props} />, {
    extraRoutes: ["/t/$slug"],
  });
}

describe("ProblemPanel", () => {
  it("shows the title, detail and request id of a failure as an alert", async () => {
    renderPanel({ problem: problem({ code: "upstream_unavailable", detail: "Try later." }) });
    expect((await screen.findByRole("alert")).textContent).toContain("Wikipedia is unavailable");
    expect(screen.getByText("Try later.")).toBeTruthy();
    expect(screen.getByText("req-1")).toBeTruthy();
  });

  it("shows a not_found answer as a muted outcome, with its detail", async () => {
    renderPanel({ problem: problem({ code: "not_found", detail: "No such page." }) });
    expect(await screen.findByText("No article by that title")).toBeTruthy();
    expect(screen.queryByRole("alert")).toBeNull();
    expect(screen.getByText("No such page.")).toBeTruthy();
  });

  it("uses `notFoundDetail` only for a not_found answer that has no detail", async () => {
    renderPanel({ problem: problem({ code: "not_found" }), notFoundDetail: 'No article "Zq".' });
    expect(await screen.findByText('No article "Zq".')).toBeTruthy();
  });

  it("prefers the detail of the problem to `notFoundDetail`", async () => {
    renderPanel({
      problem: problem({ code: "not_found", detail: "No such page." }),
      notFoundDetail: 'No article "Zq".',
    });
    await screen.findByText("No such page.");
    expect(screen.queryByText('No article "Zq".')).toBeNull();
  });

  it("does not use `notFoundDetail` for another code", async () => {
    renderPanel({ problem: problem({ code: "internal" }), notFoundDetail: 'No article "Zq".' });
    expect(await screen.findByText("Could not build that dossier")).toBeTruthy();
    expect(screen.queryByText('No article "Zq".')).toBeNull();
  });

  it("leaves the title out of a not_found answer when asked, and only then", async () => {
    renderPanel({
      problem: problem({ code: "not_found", detail: "No such page." }),
      hideNotFoundTitle: true,
    });
    await screen.findByText("No such page.");
    expect(screen.queryByText("No article by that title")).toBeNull();
  });

  it("keeps the title of another code when `hideNotFoundTitle` is set", async () => {
    renderPanel({ problem: problem({ code: "queue_full" }), hideNotFoundTitle: true });
    expect(await screen.findByText("Build queue is full")).toBeTruthy();
  });

  it("offers Retry for a failure, and it starts the request again", async () => {
    const onRetry = vi.fn();
    renderPanel({ problem: problem({ code: "queue_full" }), onRetry });
    fireEvent.click(await screen.findByRole("button", { name: "Retry" }));
    expect(onRetry).toHaveBeenCalledOnce();
  });

  it("shows a countdown instead of Retry when the server said how long to wait", async () => {
    renderPanel({ problem: problem({ code: "rate_limited", retry_after: 30 }) });
    expect(await screen.findByRole("button", { name: "Retry in 30 s" })).toBeTruthy();
    expect(screen.getAllByRole("button")).toHaveLength(1);
  });

  it("lists the candidates of a disambiguation answer", async () => {
    renderPanel({ problem: problem({ code: "disambiguation", candidates }) });
    const links = await screen.findAllByRole("link");
    expect(links.map((link) => link.textContent)).toEqual(["Mary Magdalene", "Jesus"]);
    expect(screen.queryByRole("button", { name: "Retry" })).toBeNull();
  });

  it("lists the follow-up matches and the suggestion of a not_found answer", async () => {
    renderPanel({
      problem: problem({ code: "not_found" }),
      didYouMean: candidates,
      suggestion: "Jesus Christ",
    });
    const links = await screen.findAllByRole("link");
    expect(links.map((link) => link.getAttribute("href"))).toEqual([
      "/t/Jesus_Christ?budget=8000",
      "/t/Mary_Magdalene?budget=8000",
      "/t/Jesus?budget=8000",
    ]);
    expect(screen.queryByRole("button", { name: "Retry" })).toBeNull();
  });

  it("offers the suggestion of a not_found answer even with no matches", async () => {
    renderPanel({ problem: problem({ code: "not_found" }), suggestion: "Jesus Christ" });
    expect((await screen.findByRole("link", { name: "Jesus Christ" })).getAttribute("href")).toBe(
      "/t/Jesus_Christ?budget=8000",
    );
  });

  it("says suggestions are paused when a not_found answer has none", async () => {
    renderPanel({ problem: problem({ code: "not_found" }), suggestionsPaused: true });
    expect(await screen.findByText(/Suggestions paused/)).toBeTruthy();
  });

  it("adds the topic search under a not_found answer only when asked", async () => {
    const { unmount } = renderPanel({ problem: problem({ code: "not_found" }), openSearch: true });
    expect(await screen.findByRole("combobox", { name: "Search for a topic" })).toBeTruthy();
    unmount();
    renderPanel({ problem: problem({ code: "not_found" }) });
    await screen.findByText("No article by that title");
    expect(screen.queryByRole("combobox")).toBeNull();
  });
});
