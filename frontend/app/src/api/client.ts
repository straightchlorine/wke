import { client } from "./generated/client.gen";
import { serverDownProblem, toProblem } from "../lib/errors";

// The generated client defaults to the production URL. An empty base keeps
// requests on the page's own origin, and VITE_API_BASE points them elsewhere.
client.setConfig({
  baseUrl: import.meta.env.VITE_API_BASE ?? "",
});

const JSON_CONTENT_TYPES = ["application/json", "application/problem+json"];
const MARKDOWN_PATH_SUFFIXES = [".md", "/llms.txt"];

function isExpectedContentType(pathname: string, contentType: string): boolean {
  if (JSON_CONTENT_TYPES.some((ct) => contentType.startsWith(ct))) {
    return true;
  }
  if (MARKDOWN_PATH_SUFFIXES.some((suffix) => pathname.endsWith(suffix))) {
    return contentType.startsWith("text/markdown") || contentType.startsWith("text/plain");
  }
  return false;
}

// When the API paths are not proxied, every request gets the app's index.html
// with status 200, and the generated client would return that HTML as data.
// A 2xx with an unexpected content type is reported as the server being down.
client.interceptors.response.use((response, request) => {
  if (!response.ok) {
    return response;
  }
  const contentType = response.headers.get("Content-Type") ?? "";
  // request.url is the absolute URL the client asked for. response.url can be
  // empty on a Response built by hand, as in tests.
  const pathname = new URL(request.url).pathname;
  if (isExpectedContentType(pathname, contentType)) {
    return response;
  }
  throw serverDownProblem();
});

// Every failed request, a network error included, reaches the caller as an ApiError.
client.interceptors.error.use((error, response) => toProblem(error, response));

export { client };
