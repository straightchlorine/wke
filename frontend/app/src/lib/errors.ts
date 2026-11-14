import type { ApiError } from "../api/generated";

const SERVER_DOWN_DETAIL = "Try again in a moment.";

/**
 * Returns the error panel title for a problem's code, with a generic title for a code it does not
 * know. For the code "internal", the title depends on whether our own server answered at all.
 */
export function errorTitle(problem: ApiError): string {
  switch (problem.code) {
    case "not_found":
      return "No article by that title";
    case "not_article":
      return "Not an article";
    case "disambiguation":
      return "Several articles match";
    case "rate_limited":
      return "Too many builds";
    case "queue_full":
      return "Build queue is full";
    case "upstream_rate_limited":
      return "Wikipedia is rate-limiting this server";
    case "upstream_budget":
      return "Wikipedia request limit reached for now";
    case "upstream_unavailable":
      return "Wikipedia is unavailable";
    case "not_built":
      return "Not built yet";
    case "validation_error":
      return "That title is not valid";
    case "internal":
      return isServerDown(problem) ? "The server is unavailable" : "Could not build that dossier";
    default:
      return "Could not build that dossier";
  }
}

/**
 * True when the problem has code "internal" and a status that means our own server gave no usable
 * answer: no response, or a gateway error. An ApiError the API itself sent, such as
 * upstream_unavailable, is not one.
 */
export function isServerDown(problem: ApiError): boolean {
  return (
    problem.code === "internal" &&
    (problem.status === 0 ||
      problem.status === 502 ||
      problem.status === 503 ||
      problem.status === 504)
  );
}

/**
 * Builds an ApiError that this client made up, with no type, request id or candidates from the
 * server.
 */
function syntheticProblem(
  fields: Pick<ApiError, "title" | "status" | "code" | "detail" | "retry_after">,
): ApiError {
  return { type: "about:blank", request_id: "", ...fields };
}

/**
 * Reads a numeric Retry-After header in seconds, or undefined when it is missing or an HTTP date.
 */
function parseRetryAfter(response?: Response): number | undefined {
  const header = response?.headers.get("Retry-After");
  const seconds = header != null ? Number(header) : Number.NaN;
  return Number.isFinite(seconds) ? seconds : undefined;
}

/**
 * Builds the ApiError used when our own server gave no usable answer: a gateway error, a non-JSON
 * body or an unreadable response.
 */
export function serverDownProblem(retryAfter?: number): ApiError {
  return syntheticProblem({
    title: "The server is unavailable",
    status: 503,
    code: "internal",
    retry_after: retryAfter,
    detail: SERVER_DOWN_DETAIL,
  });
}

/**
 * Builds the ApiError for a request that never reached the server, because fetch threw instead of
 * resolving.
 */
export function networkErrorProblem(): ApiError {
  return syntheticProblem({
    title: "The server is unavailable",
    status: 0,
    code: "internal",
    detail: SERVER_DOWN_DETAIL,
  });
}

/** Builds the ApiError for a job that reached "failed" without an error of its own. */
export function jobFailedProblem(): ApiError {
  return syntheticProblem({
    title: "Build failed",
    status: 500,
    code: "internal",
    detail: "Build failed on the server.",
  });
}

function isProblem(value: unknown): value is ApiError {
  return (
    typeof value === "object" &&
    value !== null &&
    "code" in value &&
    typeof value.code === "string" &&
    "status" in value &&
    typeof value.status === "number" &&
    "request_id" in value &&
    typeof value.request_id === "string"
  );
}

/**
 * Turns whatever the generated client throws into an ApiError, and is installed as its error
 * interceptor. A TypeError from fetch becomes the network-error problem.
 */
export function toProblem(error: unknown, response?: Response): ApiError {
  if (isProblem(error)) {
    // The limiter sets Retry-After as a header; carry it on the ApiError.
    const seconds = response?.status === 429 ? parseRetryAfter(response) : undefined;
    return error.retry_after == null && seconds !== undefined
      ? { ...error, retry_after: seconds }
      : error;
  }
  if (error instanceof TypeError) {
    return networkErrorProblem();
  }
  const retryAfter = parseRetryAfter(response);
  if (response?.status === 429) {
    return syntheticProblem({
      title: "Too many requests",
      status: 429,
      code: "rate_limited",
      retry_after: retryAfter,
      detail: "Too many requests; wait and try again.",
    });
  }
  return serverDownProblem(retryAfter);
}
