import { beforeEach, describe, expect, it, vi } from "vitest";
import { QueryClient } from "@tanstack/react-query";
import type { ApiError, Job } from "../../api/generated";
import { nestDossier } from "../../api/dossier";
import { dossierQueryOptions } from "../../api/queries";
import { fixtureText, loadDossier } from "../../test/fixtures";

const searchTopics = vi.fn();
const getDossier = vi.fn();
const requestDossier = vi.fn();
vi.mock("../../api/generated", () => ({
  searchTopics: (...args: unknown[]) => searchTopics(...args),
  getDossier: (...args: unknown[]) => getDossier(...args),
  requestDossier: (...args: unknown[]) => requestDossier(...args),
}));

const { resolveDossier } = await import("./resolveDossier");

const flat = loadDossier();
const { page_id: PAGE_ID, title: TITLE } = flat.topic;
const loadQueued = (): Job => JSON.parse(fixtureText("job_queued.json"));
const queued = loadQueued();

function problem(status: number, code: ApiError["code"]): ApiError {
  return { type: "about:blank", title: "Problem", status, code, request_id: "r", detail: "detail" };
}

const found = {
  data: {
    query: TITLE,
    results: [{ page_id: PAGE_ID, title: TITLE, dossier_state: "ready" as const }],
  },
};
const notFound = { data: { query: TITLE, results: [] } };

function resolve(allowBuild: boolean, client = new QueryClient()) {
  return resolveDossier(TITLE, 8000, client, allowBuild);
}

describe("resolveDossier", () => {
  beforeEach(() => {
    for (const mock of [searchTopics, getDossier, requestDossier]) {
      mock.mockReset();
    }
  });

  describe("when building is not allowed", () => {
    it("returns the dossier that is stored and stores it in the cache", async () => {
      searchTopics.mockResolvedValue(found);
      getDossier.mockResolvedValue({ data: nestDossier(flat) });
      const client = new QueryClient();
      expect(await resolve(false, client)).toEqual({ phase: "built", pageId: PAGE_ID });
      expect(client.getQueryData(dossierQueryOptions(PAGE_ID, 8000).queryKey)).toBeDefined();
      expect(requestDossier).not.toHaveBeenCalled();
    });

    it("ends as unbuilt when the dossier answers 404, without a build request", async () => {
      searchTopics.mockResolvedValue(found);
      getDossier.mockResolvedValue({ error: problem(404, "not_built") });
      expect(await resolve(false)).toEqual({ phase: "unbuilt" });
      expect(requestDossier).not.toHaveBeenCalled();
    });

    it("ends as unbuilt when the search has no exact title match, without a build request", async () => {
      searchTopics.mockResolvedValue(notFound);
      expect(await resolve(false)).toEqual({ phase: "unbuilt" });
      expect(getDossier).not.toHaveBeenCalled();
      expect(requestDossier).not.toHaveBeenCalled();
    });

    it.each([
      [
        "a rate limited dossier request",
        () => getDossier.mockResolvedValue({ error: problem(429, "rate_limited") }),
        429,
      ],
      [
        "a failing dossier request",
        () => getDossier.mockResolvedValue({ error: problem(500, "internal") }),
        500,
      ],
    ])("shows %s as an error", async (_name, arrange, status) => {
      searchTopics.mockResolvedValue(found);
      arrange();
      expect(await resolve(false)).toMatchObject({ phase: "error", problem: { status } });
      expect(requestDossier).not.toHaveBeenCalled();
    });

    it("shows a failed search as an error, not as unbuilt", async () => {
      searchTopics.mockResolvedValue({ error: problem(429, "rate_limited") });
      expect(await resolve(false)).toMatchObject({ phase: "error", problem: { status: 429 } });
      expect(getDossier).not.toHaveBeenCalled();
      expect(requestDossier).not.toHaveBeenCalled();
    });

    it("shows a network error when the search rejects", async () => {
      searchTopics.mockRejectedValue(new TypeError("offline"));
      expect(await resolve(false)).toMatchObject({ phase: "error", problem: { code: "internal" } });
      expect(requestDossier).not.toHaveBeenCalled();
    });
  });

  describe("when building is allowed", () => {
    it("requests a build after a 404 on the dossier", async () => {
      searchTopics.mockResolvedValue(found);
      getDossier.mockResolvedValue({ error: problem(404, "not_built") });
      requestDossier.mockResolvedValue({ data: queued });
      expect(await resolve(true)).toEqual({ phase: "building", jobId: queued.id });
      expect(requestDossier).toHaveBeenCalledTimes(1);
    });

    it("requests a build when the search has no exact title match", async () => {
      searchTopics.mockResolvedValue(notFound);
      requestDossier.mockResolvedValue({ data: queued });
      expect(await resolve(true)).toEqual({ phase: "building", jobId: queued.id });
      expect(getDossier).not.toHaveBeenCalled();
    });

    it("returns the dossier that is stored without a build request", async () => {
      searchTopics.mockResolvedValue(found);
      getDossier.mockResolvedValue({ data: nestDossier(flat) });
      expect(await resolve(true)).toEqual({ phase: "built", pageId: PAGE_ID });
      expect(requestDossier).not.toHaveBeenCalled();
    });

    it("returns a stored dossier from the build request when the search failed", async () => {
      searchTopics.mockResolvedValue({ error: problem(429, "rate_limited") });
      requestDossier.mockResolvedValue({ data: nestDossier(flat) });
      expect(await resolve(true)).toEqual({ phase: "built", pageId: PAGE_ID });
      expect(requestDossier).toHaveBeenCalledTimes(1);
    });

    it("shows the build error with its suggestions for a title that is not found", async () => {
      searchTopics.mockResolvedValue(notFound);
      requestDossier.mockResolvedValue({ error: problem(404, "not_found") });
      expect(await resolve(true)).toMatchObject({
        phase: "error",
        problem: { code: "not_found" },
        didYouMean: { candidates: [], suggestion: null, searchRateLimited: false },
      });
    });
  });
});
