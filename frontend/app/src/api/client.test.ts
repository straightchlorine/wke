import { beforeEach, describe, expect, it, vi } from "vitest";
import { client } from "./client";
import { getDossierMarkdown, getLlmsTxt, getTrending } from "./generated";

function respondWith(body: string, status: number, contentType: string) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => new Response(body, { status, headers: { "Content-Type": contentType } })),
  );
}

const trending = () => getTrending();
const markdown = () => getDossierMarkdown({ path: { page_id: 1 } });
const llmsTxt = () => getLlmsTxt();

describe("client response interceptor", () => {
  beforeEach(() => {
    client.setConfig({ baseUrl: "http://localhost" });
  });

  it.each([
    ["JSON", trending, "application/json"],
    ["Markdown", markdown, "text/markdown; charset=utf-8"],
    ["Markdown", markdown, "text/plain; charset=utf-8"],
    ["llms.txt", llmsTxt, "text/plain; charset=utf-8"],
  ])("passes a %s endpoint's %s 2xx body through", async (_name, call, contentType) => {
    const body = contentType.startsWith("application/json") ? '{"topics":[]}' : "# Title";
    respondWith(body, 200, contentType);

    const result = await call();

    expect(result.error).toBeUndefined();
    expect(result.data).toBeDefined();
  });

  it.each([
    ["JSON", trending],
    ["Markdown", markdown],
    ["llms.txt", llmsTxt],
  ])(
    "reports index.html served for a %s endpoint as the server being down",
    async (_name, call) => {
      respondWith("<!doctype html><html></html>", 200, "text/html; charset=utf-8");

      const result = await call();

      expect(result.data).toBeUndefined();
      expect(result.error).toMatchObject({ code: "internal", status: 503 });
    },
  );

  it("passes a problem+json error from the API through as the ApiError", async () => {
    const problem = {
      type: "about:blank",
      title: "Service Unavailable",
      status: 503,
      code: "upstream_unavailable",
      request_id: "abc",
      detail: "Wikipedia is unavailable",
    };
    respondWith(JSON.stringify(problem), 503, "application/problem+json");

    const result = await getTrending();

    expect(result.error).toMatchObject({ code: "upstream_unavailable", request_id: "abc" });
  });
});
