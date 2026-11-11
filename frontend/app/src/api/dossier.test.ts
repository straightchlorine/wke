import { beforeEach, describe, expect, it, vi } from "vitest";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { client } from "./client";
import {
  FULL_PARTS,
  flattenDossier,
  getDossierView,
  getFullDossierMarkdown,
  nestDossier,
  requestDossierView,
} from "./dossier";
import type { DossierView } from "./dossier";
import type { DossierResponse, Job } from "./generated";

const fixtureText = (name: string) =>
  readFileSync(resolve(process.cwd(), "e2e/fixtures", name), "utf-8");
const loadView = (): DossierView => JSON.parse(fixtureText("dossier_2000.json"));
const loadJob = (): Job => JSON.parse(fixtureText("job_queued.json"));

const flat = loadView();
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
    [
      "the Markdown fetch",
      () => getFullDossierMarkdown({ path: { page_id: pageId }, query: { budget: 2000 } }),
    ],
  ])("%s asks for every part and keeps the budget", async (_name, call) => {
    await call();
    expect(requested[0]?.searchParams.get("parts")).toBe(FULL_PARTS);
    expect(requested[0]?.searchParams.get("budget")).toBe("2000");
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
