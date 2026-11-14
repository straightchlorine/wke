import { beforeEach, describe, expect, it, vi } from "vitest";
import { act, renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import type { ApiError, Job } from "../../api/generated";
import { nestDossier } from "../../api/dossier";
import { dossierQueryOptions } from "../../api/queries";
import { fixtureText, loadDossier } from "../../test/fixtures";

const searchTopics = vi.fn();
const getDossier = vi.fn();
const requestDossier = vi.fn();
const getJob = vi.fn();
vi.mock("../../api/generated", () => ({
  searchTopics: (...args: unknown[]) => searchTopics(...args),
  getDossier: (...args: unknown[]) => getDossier(...args),
  requestDossier: (...args: unknown[]) => requestDossier(...args),
  getJob: (...args: unknown[]) => getJob(...args),
}));

const { useDossier } = await import("./useDossier");

const flat = loadDossier();
const { page_id: PAGE_ID, title: TITLE } = flat.topic;
const loadQueued = (): Job => JSON.parse(fixtureText("job_queued.json"));
const queued = loadQueued();

function problem(status: number, code: ApiError["code"]): ApiError {
  return { type: "about:blank", title: "Problem", status, code, request_id: "r", detail: "detail" };
}

function candidate(title: string, pageId = PAGE_ID) {
  return { page_id: pageId, title, dossier_state: "ready" as const };
}

const found = { data: { query: TITLE, results: [candidate(TITLE)] } };
const notFound = { data: { query: TITLE, results: [] } };

function renderDossier(client = newClient(), title = TITLE) {
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );
  return renderHook(({ name }: { name: string }) => useDossier(name, 8000), {
    wrapper,
    initialProps: { name: title },
  });
}

function newClient() {
  return new QueryClient({ defaultOptions: { queries: { retry: false } } });
}

describe("useDossier", () => {
  beforeEach(() => {
    for (const mock of [searchTopics, getDossier, requestDossier, getJob]) {
      mock.mockReset();
    }
    getDossier.mockResolvedValue({ data: nestDossier(flat) });
  });

  describe("outcomes", () => {
    it("shows an already built dossier without requesting a build", async () => {
      searchTopics.mockResolvedValue(found);
      const { result } = renderDossier();
      await waitFor(() => expect(result.current.dossier?.topic.title).toBe(TITLE));
      expect(result.current).toMatchObject({ phase: "built", pageId: PAGE_ID, problem: null });
      expect(requestDossier).not.toHaveBeenCalled();
      expect(getDossier).toHaveBeenCalledTimes(1);
    });

    it("finds the title whatever its letter case", async () => {
      searchTopics.mockResolvedValue({ data: { query: "x", results: [candidate(TITLE)] } });
      const { result } = renderDossier(newClient(), TITLE.toLowerCase());
      await waitFor(() => expect(result.current.phase).toBe("built"));
      expect(requestDossier).not.toHaveBeenCalled();
    });

    it("shows the dossier a build request answers with", async () => {
      searchTopics.mockResolvedValue(notFound);
      requestDossier.mockResolvedValue({ data: nestDossier(flat) });
      const { result } = renderDossier();
      await waitFor(() => expect(result.current.dossier?.topic.title).toBe(TITLE));
      expect(result.current.phase).toBe("built");
    });

    it("builds a dossier that is not built yet and follows its job to done", async () => {
      searchTopics.mockResolvedValue(found);
      getDossier.mockResolvedValueOnce({ error: problem(404, "not_built") });
      requestDossier.mockResolvedValue({ data: queued });
      getJob.mockResolvedValueOnce({ data: { ...queued, status: "running" } });
      const { result } = renderDossier();
      await waitFor(() => expect(result.current.phase).toBe("building"));
      expect(result.current.job?.id).toBe(queued.id);

      getJob.mockResolvedValue({ data: { ...queued, status: "done" } });
      await waitFor(() => expect(result.current.phase).toBe("built"), { timeout: 3000 });
      expect(result.current.pageId).toBe(PAGE_ID);
    });

    it("lists up to three suggestions when the title is not found", async () => {
      searchTopics.mockResolvedValue({
        data: {
          query: "Jesu",
          results: ["Jesus", "Jesus Christ", "Jesuit", "Jesuits"].map((t) => candidate(t)),
          did_you_mean: "Jesus",
        },
      });
      requestDossier.mockResolvedValue({ error: problem(404, "not_found") });
      const { result } = renderDossier(newClient(), "Jesu");
      await waitFor(() => expect(result.current.phase).toBe("error"));
      expect(result.current.problem?.code).toBe("not_found");
      expect(result.current.didYouMean.map((c) => c.title)).toEqual([
        "Jesus",
        "Jesus Christ",
        "Jesuit",
      ]);
      expect(result.current.suggestion).toBe("Jesus");
      expect(result.current.suggestionsPaused).toBe(false);
    });

    it("lists no suggestions for an error other than not found", async () => {
      searchTopics.mockResolvedValue({
        data: { query: "Jesu", results: [candidate("Jesus")], did_you_mean: "Jesus" },
      });
      requestDossier.mockResolvedValue({ error: problem(500, "internal") });
      const { result } = renderDossier(newClient(), "Jesu");
      await waitFor(() => expect(result.current.phase).toBe("error"));
      expect(result.current.didYouMean).toEqual([]);
      expect(result.current.suggestion).toBeNull();
    });

    it.each([
      ["a rejected search", () => searchTopics.mockRejectedValue(new TypeError("offline"))],
      ["an empty build answer", () => requestDossier.mockResolvedValue({})],
    ])("shows a network error for %s", async (_name, arrange) => {
      searchTopics.mockResolvedValue(notFound);
      arrange();
      const { result } = renderDossier();
      await waitFor(() => expect(result.current.phase).toBe("error"));
      expect(result.current.problem?.code).toBe("internal");
    });

    it("says suggestions are paused when the title search was rate limited", async () => {
      searchTopics.mockResolvedValue({ error: problem(429, "rate_limited") });
      requestDossier.mockResolvedValue({ error: problem(404, "not_found") });
      const { result } = renderDossier();
      await waitFor(() => expect(result.current.phase).toBe("error"));
      expect(result.current.didYouMean).toEqual([]);
      expect(result.current.suggestionsPaused).toBe(true);
    });

    it("shows the cached dossier with a note when a request is rate limited", async () => {
      searchTopics.mockResolvedValue(found);
      getDossier.mockResolvedValue({ error: problem(429, "rate_limited") });
      const client = newClient();
      client.setQueryData(dossierQueryOptions(PAGE_ID, 8000).queryKey, flat);
      const { result } = renderDossier(client);
      await waitFor(() => expect(result.current.phase).toBe("built"));
      expect(result.current.rateLimitNote).toBe("detail");
      expect(result.current.dossier).toEqual(flat);
    });

    it("shows the cached dossier with a note when the build request is rate limited", async () => {
      searchTopics.mockResolvedValue(found);
      getDossier.mockResolvedValue({ error: problem(404, "not_built") });
      requestDossier.mockResolvedValue({ error: problem(429, "rate_limited") });
      const client = newClient();
      client.setQueryData(dossierQueryOptions(PAGE_ID, 8000).queryKey, flat);
      const { result } = renderDossier(client);
      await waitFor(() => expect(result.current.phase).toBe("built"));
      expect(result.current.rateLimitNote).toBe("detail");
    });

    it("shows the rate limit as an error when no dossier is cached", async () => {
      searchTopics.mockResolvedValue(found);
      getDossier.mockResolvedValue({ error: problem(429, "rate_limited") });
      const { result } = renderDossier();
      await waitFor(() => expect(result.current.phase).toBe("error"));
      expect(result.current.problem?.status).toBe(429);
      expect(result.current.rateLimitNote).toBeNull();
    });
  });

  describe("a job in progress", () => {
    beforeEach(() => {
      searchTopics.mockResolvedValue(notFound);
      requestDossier.mockResolvedValue({ data: queued });
    });

    it("can be cancelled, which stops polling and shows a cancelled error", async () => {
      getJob.mockResolvedValue({ data: { ...queued, status: "running", poll_after_ms: 50 } });
      const { result } = renderDossier();
      await waitFor(() => expect(result.current.job?.status).toBe("running"));
      act(() => result.current.cancelBuild());
      expect(result.current.phase).toBe("error");
      expect(result.current.problem?.title).toBe("Cancelled");
      const polls = getJob.mock.calls.length;
      await new Promise((resolve) => setTimeout(resolve, 300));
      expect(getJob).toHaveBeenCalledTimes(polls);
    });

    it.each([
      ["its own error", problem(502, "upstream_unavailable"), "upstream_unavailable"],
      ["a generic error when it gives none", null, "internal"],
    ])("failing shows %s", async (_name, error, code) => {
      getJob.mockResolvedValue({ data: { ...queued, status: "failed", error } });
      const { result } = renderDossier();
      await waitFor(() => expect(result.current.phase).toBe("error"));
      expect(result.current.problem?.code).toBe(code);
    });

    it("is not shown under the next title", async () => {
      requestDossier.mockResolvedValueOnce({ data: queued });
      requestDossier.mockResolvedValue({ error: problem(404, "not_found") });
      getJob.mockResolvedValue({ data: { ...queued, status: "running" } });
      const seen: Array<{ title: string; job: string | null }> = [];
      const client = newClient();
      const wrapper = ({ children }: { children: ReactNode }) => (
        <QueryClientProvider client={client}>{children}</QueryClientProvider>
      );
      const { rerender } = renderHook(
        ({ name }: { name: string }) => {
          const result = useDossier(name, 8000);
          seen.push({ title: name, job: result.job?.id ?? null });
          return result;
        },
        { wrapper, initialProps: { name: TITLE } },
      );
      await waitFor(() => expect(seen.at(-1)?.job).toBe(queued.id));

      rerender({ name: "Other" });
      await waitFor(() => expect(getJob).toHaveBeenCalled());
      await new Promise((resolve) => setTimeout(resolve, 50));
      expect(seen.filter((entry) => entry.title === "Other" && entry.job !== null)).toEqual([]);
    });
  });

  describe("a job the server no longer has", () => {
    beforeEach(() => {
      searchTopics.mockResolvedValue(notFound);
      requestDossier.mockResolvedValue({ data: queued });
    });

    it("is requested again once, silently", async () => {
      getJob.mockResolvedValueOnce({ error: problem(404, "not_found") });
      getJob.mockResolvedValue({ data: { ...queued, status: "done" } });
      const { result } = renderDossier();
      await waitFor(() => expect(result.current.phase).toBe("built"));
      expect(requestDossier).toHaveBeenCalledTimes(2);
      expect(result.current.problem).toBeNull();
    });

    it("is shown as an error when the second job vanishes too", async () => {
      getJob.mockResolvedValue({ error: problem(404, "not_found") });
      const { result } = renderDossier();
      await waitFor(() => expect(result.current.phase).toBe("error"));
      expect(result.current.problem?.status).toBe(404);
      expect(requestDossier).toHaveBeenCalledTimes(2);
    });
  });

  it("runs the build request again on retry", async () => {
    searchTopics.mockResolvedValue(notFound);
    requestDossier.mockResolvedValueOnce({ error: problem(500, "internal") });
    requestDossier.mockResolvedValue({ data: nestDossier(flat) });
    const { result } = renderDossier();
    await waitFor(() => expect(result.current.phase).toBe("error"));

    act(() => result.current.retry());
    await waitFor(() => expect(result.current.phase).toBe("built"));
    expect(requestDossier).toHaveBeenCalledTimes(2);
  });

  it("never returns the previous topic's dossier under a new title", async () => {
    const other = loadDossier("dossier_214796_8000.json");
    searchTopics.mockImplementation(async ({ query }: { query: { q: string } }) => ({
      data: {
        query: query.q,
        results: [
          query.q === TITLE ? candidate(TITLE) : candidate(other.topic.title, other.topic.page_id),
        ],
      },
    }));
    getDossier.mockImplementation(async ({ path }: { path: { page_id: number } }) => ({
      data: nestDossier(path.page_id === PAGE_ID ? flat : other),
    }));
    const renders: Array<{ title: string; shown: string | null; phase: string }> = [];
    const client = newClient();
    const wrapper = ({ children }: { children: ReactNode }) => (
      <QueryClientProvider client={client}>{children}</QueryClientProvider>
    );
    const { rerender } = renderHook(
      ({ name }: { name: string }) => {
        const result = useDossier(name, 8000);
        renders.push({
          title: name,
          shown: result.dossier?.topic.title ?? null,
          phase: result.phase,
        });
        return result;
      },
      { wrapper, initialProps: { name: TITLE } },
    );
    await waitFor(() => expect(renders.at(-1)?.shown).toBe(TITLE));

    rerender({ name: other.topic.title });
    await waitFor(() => expect(renders.at(-1)?.shown).toBe(other.topic.title));
    const underNewTitle = renders.filter((entry) => entry.title === other.topic.title);
    expect(underNewTitle.filter((entry) => entry.shown === TITLE)).toEqual([]);
    expect(underNewTitle[0]?.phase).toBe("resolving");
  });
});
