import { beforeEach, describe, expect, it, vi } from "vitest";
import { client } from "./client";
import {
  FULL_PARTS,
  fetchDossierMarkdownText,
  flattenDossier,
  getDossierView,
  nestDossier,
  requestDossierView,
} from "./dossier";
import type { DossierResponse, Job } from "./generated";
import { fixtureText, loadDossier } from "../test/fixtures";

const loadJob = (): Job => JSON.parse(fixtureText("job_queued.json"));

const flat = loadDossier("dossier_1095706_2000.json");
const nested = nestDossier(flat);

describe("flattenDossier and nestDossier", () => {
  it("merges the three parts into the flat view the components read", () => {
    expect(flattenDossier(nested)).toEqual(flat);
  });

  it("nests the content, metadata and sources apart", () => {
    expect(Object.keys(nested.dossier).toSorted()).toEqual(["chunks", "graph", "sections"]);
    expect(nested.metadata?.budget).toEqual(flat.budget);
    expect(nested.sources).toEqual(flat.citations);
  });

  it.each(["metadata", "sources"] as const)("refuses a response without %s", (part) => {
    const partial: DossierResponse = { ...nested, [part]: undefined };
    expect(() => flattenDossier(partial)).toThrow(/metadata or sources/);
  });
});

describe("dossier fetches", () => {
  let requested: URL[] = [];

  function respondWith(body: unknown, status = 200) {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        requested.push(new URL(input instanceof Request ? input.url : String(input)));
        return new Response(JSON.stringify(body), {
          status,
          headers: { "Content-Type": "application/json" },
        });
      }),
    );
  }

  beforeEach(() => {
    client.setConfig({ baseUrl: "http://localhost" });
    requested = [];
    respondWith(nested);
  });

  const pageId = flat.topic.page_id;

  it.each([
    [
      "the JSON fetch",
      () => getDossierView({ path: { page_id: pageId }, query: { budget: 2000 } }),
    ],
    ["the Markdown fetch", () => fetchDossierMarkdownText(pageId, 2000)],
  ])("%s asks for every part and keeps the budget", async (_name, call) => {
    await call();
    expect(requested[0]?.searchParams.get("parts")).toBe(FULL_PARTS);
    expect(requested[0]?.searchParams.get("budget")).toBe("2000");
  });

  it("the Markdown text fetch returns the body", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response("# Jesus", { headers: { "Content-Type": "text/markdown" } })),
    );
    expect(await fetchDossierMarkdownText(pageId, 2000)).toBe("# Jesus");
  });

  it("the Markdown text fetch returns null when the API answers with an error", async () => {
    respondWith({ code: "not_built", status: 404, title: "Not built", request_id: "r" }, 404);
    expect(await fetchDossierMarkdownText(pageId, 2000)).toBeNull();
  });

  it("the JSON fetch returns the flat view", async () => {
    const result = await getDossierView({ path: { page_id: pageId } });
    expect(result.data).toEqual(flat);
  });

  it("a build request asks for every part and flattens an already built dossier", async () => {
    const result = await requestDossierView(flat.topic.title);
    expect(requested[0]?.searchParams.get("parts")).toBe(FULL_PARTS);
    expect(result.data).toEqual(flat);
  });

  it("a build request returns a queued job unchanged", async () => {
    const job = loadJob();
    respondWith(job, 202);
    const result = await requestDossierView(flat.topic.title);
    expect(result.data).toEqual(job);
  });
});
