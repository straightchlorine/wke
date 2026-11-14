import { describe, expect, it } from "vitest";
import type { ApiError } from "../api/generated";
import {
  errorTitle,
  isServerDown,
  jobFailedProblem,
  networkErrorProblem,
  serverDownProblem,
  toProblem,
} from "./errors";

function problem(code: ApiError["code"]): ApiError {
  return { type: "about:blank", title: "t", status: 400, code, request_id: "r" };
}

describe("errorTitle", () => {
  it.each<[ApiError["code"], string]>([
    ["not_found", "No article by that title"],
    ["not_article", "Not an article"],
    ["disambiguation", "Several articles match"],
    ["rate_limited", "Too many builds"],
    ["queue_full", "Build queue is full"],
    ["upstream_rate_limited", "Wikipedia is rate-limiting this server"],
    ["upstream_budget", "Wikipedia request limit reached for now"],
    ["upstream_unavailable", "Wikipedia is unavailable"],
    ["not_built", "Not built yet"],
    ["validation_error", "That title is not valid"],
    ["internal", "Could not build that dossier"],
  ])("titles %s", (code, title) => {
    expect(errorTitle(problem(code))).toBe(title);
  });

  it("says the server is unavailable for the synthetic server-down problems", () => {
    expect(errorTitle(networkErrorProblem())).toBe("The server is unavailable");
    expect(errorTitle(serverDownProblem())).toBe("The server is unavailable");
    expect(errorTitle(jobFailedProblem())).toBe("Could not build that dossier");
  });

  it.each([
    [0, true],
    [502, true],
    [503, true],
    [504, true],
    [500, false],
    [400, false],
  ])("isServerDown for an internal problem with status %i is %s", (status, expected) => {
    expect(isServerDown({ ...problem("internal"), status })).toBe(expected);
  });

  it("keeps Wikipedia is unavailable for the API's own upstream_unavailable", () => {
    expect(isServerDown({ ...problem("upstream_unavailable"), status: 503 })).toBe(false);
    expect(isServerDown(serverDownProblem())).toBe(true);
  });
});

describe("synthetic problems", () => {
  it("networkErrorProblem is an internal status 0 with a detail that fits one line", () => {
    expect(networkErrorProblem()).toMatchObject({
      code: "internal",
      status: 0,
      detail: "Try again in a moment.",
    });
  });

  it("jobFailedProblem is an internal status 500", () => {
    expect(jobFailedProblem()).toMatchObject({ code: "internal", status: 500 });
  });
});

describe("toProblem", () => {
  it("passes an ApiError through unchanged", () => {
    const p = problem("not_found");
    expect(toProblem(p)).toBe(p);
  });

  it.each<[string, unknown]>([
    ["a numeric code", { code: 7, status: 400, request_id: "r" }],
    ["a string status", { code: "not_found", status: "400", request_id: "r" }],
    ["a missing request_id", { code: "not_found", status: 400 }],
    ["a numeric request_id", { code: "not_found", status: 400, request_id: 5 }],
  ])("does not treat %s as an ApiError", (_name, value) => {
    expect(toProblem(value)).toMatchObject({ code: "internal", status: 503 });
  });

  it("maps a fetch TypeError to the network problem", () => {
    expect(toProblem(new TypeError("Failed to fetch"))).toEqual(networkErrorProblem());
  });

  it("maps a 429 with a numeric Retry-After to rate_limited with retry_after", () => {
    const response = new Response(null, { status: 429, headers: { "Retry-After": "30" } });
    expect(toProblem("boom", response)).toMatchObject({
      code: "rate_limited",
      status: 429,
      retry_after: 30,
    });
  });

  it("drops a Retry-After that is an HTTP date", () => {
    const response = new Response(null, {
      status: 429,
      headers: { "Retry-After": "Wed, 21 Oct 2026 07:28:00 GMT" },
    });
    expect(toProblem("boom", response)).toMatchObject({
      code: "rate_limited",
      retry_after: undefined,
    });
  });

  it("leaves retry_after undefined on a 429 without the header", () => {
    expect(toProblem("boom", new Response(null, { status: 429 }))).toMatchObject({
      code: "rate_limited",
      retry_after: undefined,
    });
  });

  it("adds the Retry-After header to a 429 ApiError that lacks retry_after", () => {
    const response = new Response(null, { status: 429, headers: { "Retry-After": "12" } });
    expect(toProblem(problem("rate_limited"), response).retry_after).toBe(12);
    expect(toProblem({ ...problem("rate_limited"), retry_after: 3 }, response).retry_after).toBe(3);
    const other = new Response(null, { status: 503, headers: { "Retry-After": "12" } });
    expect(toProblem(problem("internal"), other).retry_after).toBeUndefined();
  });

  it("maps any other status, or no response, to the server-down problem", () => {
    expect(toProblem({}, new Response(null, { status: 502 }))).toMatchObject({
      code: "internal",
      status: 503,
    });
    expect(toProblem("boom")).toMatchObject({ code: "internal", status: 503 });
  });

  it("keeps a numeric Retry-After on a non-429 response", () => {
    const response = new Response(null, { status: 503, headers: { "Retry-After": "5" } });
    expect(toProblem("boom", response)).toMatchObject({ code: "internal", retry_after: 5 });
  });
});
