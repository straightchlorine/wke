import { describe, expect, it } from "vitest";
import { cleanup, screen } from "@testing-library/react";
import { renderWithRouter } from "../test/renderWithRouter";
import type { TopicCandidate } from "../api/generated";
import { DidYouMean, type DidYouMeanProps } from "./DidYouMean";

const candidate: TopicCandidate = {
  page_id: 1,
  title: "Alan Turing",
  description: "English mathematician",
  dossier_state: "none",
};

async function renderPanel(props: Partial<DidYouMeanProps>) {
  renderWithRouter(<DidYouMean candidates={[]} budget={8000} {...props} />, {
    extraRoutes: ["/t/$slug"],
  });
  await screen.findByText(/Did you mean/);
}

describe("DidYouMean", () => {
  it("leads with the API suggestion as a link when one is present", async () => {
    await renderPanel({ candidates: [candidate], suggestion: "Alan Turing" });
    const links = await screen.findAllByRole("link");
    expect(links.map((l) => l.getAttribute("href"))).toEqual([
      "/t/Alan_Turing?budget=8000",
      "/t/Alan_Turing?budget=8000",
    ]);
    expect(screen.getAllByText(/Did you mean/)).toHaveLength(1);
  });

  it("renders the suggestion alone when the candidate list is empty", async () => {
    await renderPanel({ candidates: [], suggestion: "Grace Hopper" });
    const links = await screen.findAllByRole("link");
    expect(links.map((l) => l.getAttribute("href"))).toEqual(["/t/Grace_Hopper?budget=8000"]);
  });

  it("trims the suggestion, and ignores one that is only spaces", async () => {
    await renderPanel({ candidates: [candidate], suggestion: "  Grace Hopper " });
    expect(screen.getByRole("link", { name: "Grace Hopper" }).getAttribute("href")).toBe(
      "/t/Grace_Hopper?budget=8000",
    );
    cleanup();
    await renderPanel({ candidates: [candidate], suggestion: "   " });
    expect(screen.getByText("Did you mean").tagName).toBe("P");
    expect(screen.getAllByRole("link")).toHaveLength(1);
  });

  it("falls back to the plain candidate list without a suggestion", async () => {
    await renderPanel({ candidates: [candidate], suggestion: null });
    const links = await screen.findAllByRole("link");
    expect(links.map((l) => l.getAttribute("href"))).toEqual(["/t/Alan_Turing?budget=8000"]);
    expect(screen.getByText("Did you mean").tagName).toBe("P");
  });

  it.each([
    ["none", "Not built"],
    ["building", "Building"],
    ["partial", "Partial"],
    ["ready", "Ready"],
  ] as const)("marks a %s candidate with the %s chip", async (state, text) => {
    await renderPanel({ candidates: [{ ...candidate, dossier_state: state }] });
    expect(screen.getByText(text)).toBeTruthy();
  });

  it("tells an unbuilt candidate how to build it, and keeps the description", async () => {
    await renderPanel({ candidates: [candidate] });
    expect(screen.getByText("Enter builds it - English mathematician")).toBeTruthy();
  });

  it("shows only the description for a candidate that has a dossier", async () => {
    await renderPanel({ candidates: [{ ...candidate, dossier_state: "ready" }] });
    expect(screen.getByText("English mathematician")).toBeTruthy();
  });

  it("lists at most three candidates, under a label when a suggestion leads", async () => {
    const many = ["A", "B", "C", "D"].map((title, i) => ({ ...candidate, page_id: i, title }));
    await renderPanel({ candidates: many, suggestion: "Z" });
    expect(screen.getByRole("group", { name: "Other close titles" })).toBeTruthy();
    expect(screen.getAllByRole("link").map((l) => l.textContent)).toEqual(["Z", "A", "B", "C"]);
  });

  it("puts no label on the list when the suggestion stands alone", async () => {
    await renderPanel({ candidates: [], suggestion: "Z" });
    expect(screen.queryByRole("group")).toBeNull();
  });
});
