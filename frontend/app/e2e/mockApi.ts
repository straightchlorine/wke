import { createHash, randomUUID } from "node:crypto";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import type { Page } from "@playwright/test";

const FIXTURES_DIR = fileURLToPath(new URL("./fixtures", import.meta.url));

export function readFixture(name: string): string {
  return readFileSync(`${FIXTURES_DIR}/${name}`, "utf-8");
}

type JsonObject = Record<string, unknown>;

function asObject(value: unknown): JsonObject {
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    throw new Error("expected a JSON object");
  }
  return Object.fromEntries(Object.entries(value));
}

function parseObject(text: string): JsonObject {
  const value: unknown = JSON.parse(text);
  return asObject(value);
}

function stringField(object: JsonObject, key: string): string {
  const value = object[key];
  if (typeof value !== "string") {
    throw new Error(`expected "${key}" to be a string`);
  }
  return value;
}

function numberField(object: JsonObject, key: string): number {
  const value = object[key];
  if (typeof value !== "number") {
    throw new Error(`expected "${key}" to be a number`);
  }
  return value;
}

function objectsField(object: JsonObject, key: string): JsonObject[] {
  const value = object[key];
  if (!Array.isArray(value)) {
    throw new Error(`expected "${key}" to be an array`);
  }
  return value.map(asObject);
}

/** The title of a POST /dossiers body, or undefined when the body has none. */
function requestedTitle(body: unknown): string | undefined {
  if (typeof body === "object" && body !== null && "title" in body) {
    return typeof body.title === "string" ? body.title : undefined;
  }
  return undefined;
}

/** Nests a flat dossier build into the schema-2 body the API serves for parts=dossier,metadata,sources. */
export function dossierEnvelope(flat: object): object {
  const {
    schema_version: _schema,
    license_notice,
    sections,
    chunks,
    graph,
    citations,
    ...metadata
  }: JsonObject = Object.fromEntries(Object.entries(flat));
  return {
    schema_version: "2",
    license_notice,
    dossier: { sections, chunks, graph },
    metadata,
    sources: citations,
  };
}

/** Reads a recorded dossier fixture, applies the optional edit to its flat build, and returns the nested body as JSON text. */
export function dossierBody(name: string, edit?: (flat: Record<string, unknown>) => void): string {
  const flat = parseObject(readFixture(name));
  edit?.(flat);
  return JSON.stringify(dossierEnvelope(flat));
}

function weakEtagFor(body: string): string {
  const hash = createHash("sha256").update(body).digest("hex").slice(0, 16);
  return `"${hash}"`;
}

// The dossiers built for this mock stack, by page id. Each has a build at
// every budget in BUDGETS and a Markdown rendering at 8000, and any other
// page id has no dossier built. A POST for "Mercury" answers with a
// disambiguation, "Kamchatka" with its own job and "Nonexistent Title" with
// a 404, and any other title gets the Jesus job.
const BUDGETS = [2000, 8000, 32000];
// The origin every recorded link and result_url points at.
const API_ORIGIN = "http://localhost:8010";
const DOSSIER_PAGE_IDS = [1095706, 214796, 58863, 19694, 662, 27697009, 678671];
const DOSSIER_FIXTURES: Record<number, Record<number, string>> = Object.fromEntries(
  DOSSIER_PAGE_IDS.map((id) => [
    id,
    Object.fromEntries(BUDGETS.map((budget) => [budget, `dossier_${id}_${budget}.json`])),
  ]),
);

// "yesterday" only when the snapshot is exactly one UTC day old, the same
// rule the app applies to its own labels.
function mostReadWhen(date: string): string {
  const today = new Date();
  const days = Math.round(
    (Date.UTC(today.getUTCFullYear(), today.getUTCMonth(), today.getUTCDate()) - Date.parse(date)) /
      86_400_000,
  );
  return days === 1 ? `yesterday (${date} UTC)` : `on ${date} (UTC)`;
}

// The recorded search answer a query gets; any other query gets Jesus.
function searchTopic(
  query: string,
): "jesus" | "lizzie" | "godel" | "mercury" | "apollo" | "api" | "kamchatka" {
  const rules = [
    ["lizzie", /^lizzie borden$/i],
    ["godel", /^g(o|\u00f6)del/i],
    ["mercury", /^mercury$/i],
    ["apollo", /^apollo/i],
    ["api", /^api\b/i],
    ["kamchatka", /^kamchatka/i],
  ] as const;
  return rules.find(([, pattern]) => pattern.test(query))?.[0] ?? "jesus";
}

function notBuiltProblem(pageId: number): string {
  return JSON.stringify({
    type: "about:blank",
    title: "Not Found",
    status: 404,
    detail: `No dossier has been built for page ${pageId}.`,
    code: "not_built",
    request_id: randomUUID(),
  });
}

/**
 * Routes the wke-api endpoints the frontend uses to the recorded fixtures in e2e/fixtures.
 * The JSON dossier answer carries the ETag, WKE-Dossier-Tokens and WKE-Freshness headers the app reads.
 */
export async function mockApi(page: Page): Promise<void> {
  const trending = readFixture("trending.json");
  const live = readFixture("live.json");
  const dossiers = readFixture("dossiers.json");
  const markdownByPage = new Map(
    DOSSIER_PAGE_IDS.map((id) => [
      id,
      stringField(parseObject(readFixture(`dossier_${id}_md.json`)), "markdown"),
    ]),
  );
  const jobQueued = readFixture("job_queued.json");
  const jobDone = readFixture("job_done.json");
  const jobRunning = readFixture("job_running_partial.json");
  const searchByTopic = {
    jesus: readFixture("search_jesus.json"),
    lizzie: readFixture("search_lizzie.json"),
    godel: readFixture("search_godel.json"),
    mercury: readFixture("search_mercury.json"),
    apollo: readFixture("search_apollo.json"),
    api: readFixture("search_api.json"),
    kamchatka: readFixture("search_kamchatka.json"),
  };
  const disambiguationMercury = readFixture("disambiguation_mercury.json");
  const dossiersApi = readFixture("dossiers_api.json");
  const queuedJobId = stringField(parseObject(jobQueued), "id");
  const runningJobId = stringField(parseObject(jobRunning), "id");

  // The job a POST for "Kamchatka" starts: the recorded queued and done jobs
  // re-pointed at the Kamchatka Peninsula dossier.
  const kamchatkaId = 678671;
  const kamchatkaJobId = "5c0a1d9e3b7f4a26";
  const kamchatkaJob = {
    id: kamchatkaJobId,
    page_id: kamchatkaId,
    rev_id: numberField(
      asObject(parseObject(readFixture(`dossier_${kamchatkaId}_8000.json`))["freshness"]),
      "pinned_rev_id",
    ),
    title: "Kamchatka Peninsula",
  };
  const kamchatkaQueued = JSON.stringify({ ...parseObject(jobQueued), ...kamchatkaJob });
  const kamchatkaDone = JSON.stringify({
    ...parseObject(jobDone),
    ...kamchatkaJob,
    result_url: `${API_ORIGIN}/api/v1/dossiers/${kamchatkaId}?budget=8000`,
  });

  // The index an agent reads first, built from the recorded trending
  // snapshot the way the API builds its own (one line per ready dossier).
  const trendingSnapshot = parseObject(trending);
  const snapshotDate = stringField(trendingSnapshot, "date");
  const snapshotTopics = objectsField(trendingSnapshot, "topics").map((topic) => ({
    pageId: numberField(topic, "page_id"),
    title: stringField(topic, "title"),
  }));
  const llmsTxt = [
    "# Wikipedia Knowledge Explorer",
    "",
    "> Cited context from Wikipedia for people and LLMs.",
    "",
    "## API",
    "",
    `- Dossier (Markdown): \`${API_ORIGIN}/api/v1/dossiers/{page_id}.md?budget=8000\``,
    "",
    `## Most read on Wikipedia ${mostReadWhen(snapshotDate)}`,
    "",
    ...snapshotTopics
      .filter((topic) => DOSSIER_FIXTURES[topic.pageId] != null)
      .map(
        (topic) =>
          `- [${topic.title}](${API_ORIGIN}/api/v1/dossiers/${topic.pageId}.md?budget=8000)`,
      ),
    "",
  ].join("\n");
  await page.route("**/llms.txt", async (route) => {
    if (route.request().resourceType() === "document") {
      await route.continue();
      return;
    }
    await route.fulfill({
      status: 200,
      contentType: "text/markdown; charset=utf-8",
      body: llmsTxt,
    });
  });

  await page.route("**/api/v1/trending", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      headers: { etag: weakEtagFor(trending), "cache-control": "public, max-age=60" },
      body: trending,
    });
  });

  const liveStream = stringField(parseObject(live), "stream");
  await page.route(/\/api\/v1\/status$/, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        version: "0.1.0",
        redis: true,
        ml_ready: true,
        watcher_connected: liveStream === "connected",
        trending_date: snapshotDate,
        queue_depth: 0,
      }),
    });
  });

  await page.route("**/api/v1/live**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      headers: { etag: weakEtagFor(live) },
      body: live,
    });
  });

  // A bare glob for the dossiers path does not match a query string, so a regex routes the list endpoint with or without one.
  // A single dossier fetch has its own route below.
  await page.route(/\/api\/v1\/dossiers(\?[^/]*)?$/, async (route) => {
    const method = route.request().method();
    if (method === "POST") {
      const requested = requestedTitle(route.request().postDataJSON());
      if (requested != null && /^mercury$/i.test(requested)) {
        await route.fulfill({
          status: 409,
          contentType: "application/problem+json",
          body: disambiguationMercury,
        });
        return;
      }
      if (requested === "Nonexistent Title") {
        await route.fulfill({
          status: 404,
          contentType: "application/problem+json",
          body: JSON.stringify({
            type: "about:blank",
            title: "Not Found",
            status: 404,
            detail: 'No article titled "Nonexistent Title" on en.wikipedia.',
            code: "not_found",
            request_id: "mock-not-found",
          }),
        });
        return;
      }
      if (requested != null && /^kamchatka$/i.test(requested)) {
        await route.fulfill({
          status: 202,
          contentType: "application/json",
          headers: { location: `/api/v1/jobs/${kamchatkaJobId}` },
          body: kamchatkaQueued,
        });
        return;
      }
      await route.fulfill({
        status: 202,
        contentType: "application/json",
        headers: { location: `/api/v1/jobs/${queuedJobId}` },
        body: jobQueued,
      });
      return;
    }
    if (method !== "GET") {
      await route.continue();
      return;
    }
    // The title filter the suggestions use; the recorded answer for "api"
    // holds the stored titles that start with it.
    const titleFilter = new URL(route.request().url()).searchParams.get("q");
    if (titleFilter != null && /^api\b/i.test(titleFilter)) {
      await route.fulfill({ status: 200, contentType: "application/json", body: dossiersApi });
      return;
    }
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      headers: { etag: weakEtagFor(dossiers) },
      body: titleFilter == null ? dossiers : JSON.stringify({ items: [], next_cursor: null }),
    });
  });

  await page.route(/\/api\/v1\/dossiers\/(\d+)\.md(\?[^/]*)?$/, async (route) => {
    if (route.request().method() !== "GET") {
      await route.continue();
      return;
    }
    const pageId = Number(
      new URL(route.request().url()).pathname.match(/\/dossiers\/(\d+)\.md$/)?.[1],
    );
    const markdown = markdownByPage.get(pageId);
    if (markdown == null) {
      await route.fulfill({
        status: 404,
        contentType: "application/problem+json",
        body: notBuiltProblem(pageId),
      });
      return;
    }
    await route.fulfill({
      status: 200,
      contentType: "text/markdown; charset=utf-8",
      body: markdown,
    });
  });

  // A single dossier fetch. Without this route the request falls through
  // to Vite's SPA fallback, which answers unmatched GET with index.html
  // (200 text/html). Page ids without a built dossier return a real 404
  // problem+json instead of falling back to a loaded fixture.
  await page.route(/\/api\/v1\/dossiers\/(\d+)(\?[^/]*)?$/, async (route) => {
    if (route.request().method() !== "GET") {
      await route.continue();
      return;
    }
    const url = new URL(route.request().url());
    const pageId = Number(url.pathname.match(/\/dossiers\/(\d+)$/)?.[1]);
    const requestedBudget = Number(url.searchParams.get("budget") ?? 8000);
    const fixtureName = DOSSIER_FIXTURES[pageId]?.[requestedBudget];
    if (!fixtureName) {
      await route.fulfill({
        status: 404,
        contentType: "application/problem+json",
        body: notBuiltProblem(pageId),
      });
      return;
    }
    const body = dossierBody(fixtureName);
    const metadata = asObject(parseObject(body)["metadata"]);
    const usedTokens = numberField(asObject(metadata["budget"]), "used_est_tokens");
    const freshness = stringField(asObject(metadata["freshness"]), "state");
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      headers: {
        etag: weakEtagFor(body),
        "wke-dossier-tokens": String(usedTokens),
        "wke-freshness": freshness,
      },
      body,
    });
  });

  await page.route(/\/api\/v1\/jobs\/[^/?]+(\?[^/]*)?$/, async (route) => {
    if (route.request().method() !== "GET") {
      await route.continue();
      return;
    }
    const jobId = new URL(route.request().url()).pathname.split("/").pop();
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body:
        jobId === runningJobId ? jobRunning : jobId === kamchatkaJobId ? kamchatkaDone : jobDone,
    });
  });

  await page.route(/\/api\/v1\/search(\?[^/]*)?$/, async (route) => {
    if (route.request().method() !== "GET") {
      await route.continue();
      return;
    }
    const query = new URL(route.request().url()).searchParams.get("q") ?? "";
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: searchByTopic[searchTopic(query)],
    });
  });
}
