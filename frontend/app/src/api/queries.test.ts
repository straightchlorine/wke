import { beforeEach, describe, expect, it, vi } from "vitest";
import { QueryClient, skipToken } from "@tanstack/react-query";
import { client } from "./client";
import { nestDossier } from "./dossier";
import {
  dossierQueryOptions,
  dossiersListQueryOptions,
  trendingQueryOptions,
  unwrap,
} from "./queries";
import { fixtureText, loadDossier } from "../test/fixtures";

describe("unwrap", () => {
  it("returns the data of a successful result", () => {
    expect(unwrap({ data: { id: 1 }, error: undefined })).toEqual({ id: 1 });
  });

  it("throws the error object itself, not a copy", () => {
    const error = { status: 404, code: "not_found" };
    let thrown: unknown;
    try {
      unwrap({ data: undefined, error });
    } catch (caught) {
      thrown = caught;
    }
    expect(thrown).toBe(error);
  });

  it.each([[0], [""], [false]])("returns the falsy body %j", (body) => {
    expect(unwrap({ data: body })).toBe(body);
  });

  it("refuses a result with neither data nor error", () => {
    expect(() => unwrap({})).toThrow(/without a body/);
  });
});

describe("query options", () => {
  const flat = loadDossier("dossier_1095706_2000.json");
  let requested: URL[] = [];

  beforeEach(() => {
    client.setConfig({ baseUrl: "http://localhost" });
    requested = [];
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        const url = new URL(input instanceof Request ? input.url : String(input));
        requested.push(url);
        const body = url.pathname.includes("/dossiers/")
          ? JSON.stringify(nestDossier(flat))
          : fixtureText(url.pathname.endsWith("/trending") ? "trending.json" : "dossiers_api.json");
        return new Response(body, {
          headers: { "Content-Type": "application/json" },
        });
      }),
    );
  });

  it("fetches a dossier at its budget and returns the flat view", async () => {
    const data = await new QueryClient().fetchQuery(dossierQueryOptions(flat.topic.page_id, 2000));
    expect(data).toEqual(flat);
    expect(requested[0]?.pathname).toBe(`/api/v1/dossiers/${flat.topic.page_id}`);
    expect(requested[0]?.searchParams.get("budget")).toBe("2000");
  });

  it("keys a dossier by page and budget, and has no fetcher without a page", () => {
    expect(dossierQueryOptions(7, 8000).queryKey).toEqual(["dossier", 7, 8000]);
    expect(dossierQueryOptions(null, 8000).queryFn).toBe(skipToken);
    expect(dossierQueryOptions(7, 8000).queryFn).not.toBe(skipToken);
  });

  it("asks the dossier list for its limit", async () => {
    await new QueryClient().fetchQuery(dossiersListQueryOptions);
    expect(requested[0]?.pathname).toBe("/api/v1/dossiers");
    expect(requested[0]?.searchParams.get("limit")).toBe("100");
  });

  it("fetches the trending topics", async () => {
    const data = await new QueryClient().fetchQuery(trendingQueryOptions);
    expect(requested[0]?.pathname).toBe("/api/v1/trending");
    expect(data.topics.length).toBeGreaterThan(0);
  });
});

describe("retry policy", () => {
  it.each([
    ["dossier", dossierQueryOptions(1, 8000)],
    ["dossiers list", dossiersListQueryOptions],
    ["trending", trendingQueryOptions],
  ])("the %s query does not retry by itself", (_name, options) => {
    expect(options.retry).toBe(false);
  });
});
