import { useState } from "react";
import { createFileRoute } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { getLlmsTxt } from "../api/generated";
import { FULL_PARTS, fetchDossierMarkdownText, getDossierView, nestDossier } from "../api/dossier";
import type { DossierView } from "../api/dossier";
import { trendingQueryOptions, unwrap } from "../api/queries";
import { Record, type RecordRowProps } from "../components/Record";
import { CodeBlock } from "../components/CodeBlock";
import { Toast } from "../components/Toast";
import { useSeo } from "../lib/seo";
import { publicBaseUrl } from "../lib/publicBaseUrl";
import type { Budget } from "../lib/budget";
import {
  dossierJsonUrl,
  dossierMarkdownUrl,
  llmsTxtUrl,
  mcpDossierCall,
  mcpUrl,
} from "../lib/endpoints";
import { formatNumber } from "../lib/format";
import { useInView } from "../lib/hooks/useInView";

export const Route = createFileRoute("/machines")({
  component: Machines,
});

// The example responses on this page are read from the live API.
// No revision, timestamp or text is typed in here.
const EXAMPLE_TITLE = "Jesus";
const EXAMPLE_PAGE_ID = 1095706;
const EXAMPLE_BUDGET: Budget = 8000;
const EXCERPT_LINES = 40;

const PER_MINUTE = { search: 30, reads: 120, build: 6, poll: 600, live: 12 } as const;
const perMinute = (limit: number) => `${limit} a minute`;

const LIMIT_ROWS: RecordRowProps[] = [
  { label: "Search and MCP", value: perMinute(PER_MINUTE.search), size: "normal" },
  { label: "Dossier reads (GET)", value: perMinute(PER_MINUTE.reads), size: "normal" },
  { label: "Build (POST)", value: perMinute(PER_MINUTE.build), size: "normal" },
  {
    label: "Job polling (GET /api/v1/jobs/{id})",
    value: perMinute(PER_MINUTE.poll),
    size: "normal",
  },
  { label: "Live edits", value: perMinute(PER_MINUTE.live), size: "normal" },
  { label: "Forced rebuild (refresh)", value: "2 an hour", size: "normal" },
  { label: "Wikipedia busy", value: "503, Retry-After passed through", size: "normal" },
];

/** Stands in for the part of an example that is cut for display. */
const ELIDED = "...";

const elide = (ids: string[]) => (ids.length > 1 ? [ids[0], ELIDED] : ids);

/** Returns the dossier as nested JSON cut for display: one section (the first with a summary), one source, and long lists shortened to an elision marker. */
function jsonExcerpt(dossier: DossierView): string {
  const section = dossier.sections.find((entry) => entry.summary != null) ?? dossier.sections[0];
  const { metadata, sources } = nestDossier(dossier);
  return JSON.stringify(
    {
      schema_version: dossier.schema_version,
      license_notice: dossier.license_notice,
      dossier: {
        sections: section
          ? [
              {
                ...section,
                chunk_ids: elide(section.chunk_ids),
                summary: section.summary
                  ? {
                      ...section.summary,
                      input_chunk_ids: elide(section.summary.input_chunk_ids ?? []),
                    }
                  : section.summary,
              },
            ]
          : [],
        chunks: [ELIDED],
        graph: { nodes: [ELIDED], edges: [ELIDED] },
      },
      metadata: {
        ...metadata,
        budget: { ...dossier.budget, included_chunk_ids: elide(dossier.budget.included_chunk_ids) },
      },
      sources: sources?.slice(0, 1),
    },
    null,
    2,
  );
}

/** The first lines of a text, then an elision line when more follow. */
function head(text: string, lines: number): string {
  const all = text.split("\n");
  return all.length > lines ? `${all.slice(0, lines).join("\n")}\n${ELIDED}` : text;
}

// Text for an example that has no response yet. The llms.txt and Markdown examples load when
// their section nears the viewport. The JSON example loads at once.
const placeholder = (failed: boolean, requested: boolean) => {
  if (failed) {
    return "The API did not return this example.";
  }
  return requested
    ? "Waiting for the API. The example is read from it, not typed in."
    : "Loads when scrolled into view.";
};

function Machines() {
  useSeo({
    title: "For machines",
    description:
      "llms.txt, JSON, Markdown and MCP: every dossier as an HTTP call, with the revision it was built from.",
    path: "/machines",
  });
  const [toast, setToastState] = useState<{ text: string | null; n: number }>({ text: null, n: 0 });
  const setToast = (text: string | null) => setToastState((prev) => ({ text, n: prev.n + 1 }));
  const [llmsRef, llmsInView] = useInView();
  const [jsonRef, jsonInView] = useInView();
  const [markdownRef, markdownInView] = useInView();
  // Home's trending fetch has the same query key, so both pages share one cached request and show
  // the same date. The date only labels the example headings, so it waits for the first of them.
  const trendingQuery = useQuery({
    ...trendingQueryOptions,
    enabled: llmsInView || jsonInView || markdownInView,
  });
  const snapshotDate = trendingQuery.data?.date;
  // The example dossier with the headers the API sent. Its links.self also gives the origin that
  // the example URLs on this page use.
  const exampleQuery = useQuery({
    queryKey: ["machines-example", EXAMPLE_PAGE_ID, EXAMPLE_BUDGET],
    queryFn: async () => {
      const result = await getDossierView({
        path: { page_id: EXAMPLE_PAGE_ID },
        query: { budget: EXAMPLE_BUDGET },
      });
      const headers = result.response?.headers;
      return {
        dossier: unwrap(result),
        etag: headers?.get("etag") ?? null,
        tokens: headers?.get("wke-dossier-tokens") ?? null,
        freshness: headers?.get("wke-freshness") ?? null,
      };
    },
    retry: false,
    staleTime: 30_000,
  });
  const markdownQuery = useQuery({
    queryKey: ["machines-example-md", EXAMPLE_PAGE_ID, EXAMPLE_BUDGET],
    queryFn: async () => {
      const text = await fetchDossierMarkdownText(EXAMPLE_PAGE_ID, EXAMPLE_BUDGET);
      if (text == null) {
        throw new Error("the API did not return the Markdown example");
      }
      return text;
    },
    retry: false,
    enabled: markdownInView,
    staleTime: 30_000,
  });
  const llmsQuery = useQuery({
    queryKey: ["machines-example-llms"],
    queryFn: async () => unwrap(await getLlmsTxt()),
    retry: false,
    enabled: llmsInView,
    staleTime: 30_000,
  });
  const exampleDossier = exampleQuery.data?.dossier;
  const base = publicBaseUrl(exampleDossier?.links.self);
  const snapshotLabel = snapshotDate ? `, snapshot ${snapshotDate}` : "";

  return (
    <div className="py-8">
      <section className="border-b-(length:--hairline) border-rule-strong pb-6">
        <div className="grid grid-cols-1 gap-8 lg:grid-cols-[minmax(0,1fr)_360px]">
          <div>
            <h1 tabIndex={-1} className="font-serif text-36 text-ink lg:text-44">
              For machines
            </h1>
            <p className="mt-3 max-w-(--container-prose) font-serif text-16 text-ink-2 lg:text-18 [@media(pointer:coarse)]:max-lg:leading-6">
              Every dossier is one HTTP call, pinned to the Wikipedia revision it was built from. No
              key, no account: the same text shown on the site, as{" "}
              <a
                href="#llms"
                className="hit-coarse text-accent underline underline-offset-2 decoration-1"
              >
                llms.txt
              </a>
              ,{" "}
              <a
                href="#json"
                className="hit-coarse text-accent underline underline-offset-2 decoration-1"
              >
                JSON
              </a>
              ,{" "}
              <a
                href="#markdown"
                className="hit-coarse text-accent underline underline-offset-2 decoration-1"
              >
                Markdown
              </a>{" "}
              or through an{" "}
              <a
                href="#mcp"
                className="hit-coarse text-accent underline underline-offset-2 decoration-1"
              >
                MCP server
              </a>
              .
            </p>
          </div>
          <Record
            label="Basics"
            rows={[
              {
                label: "Base URL",
                value: <code className="font-mono">{base}</code>,
                size: "normal",
              },
              { label: "Auth", value: "none", size: "normal" },
              { label: "Errors", value: "application/problem+json", size: "normal" },
              {
                label: "Rate limit",
                value: `${perMinute(PER_MINUTE.search)} per client IP on search and MCP, ${perMinute(PER_MINUTE.live)} on live edits`,
                size: "normal",
                wrap: true,
              },
              {
                label: "Over the limit",
                value: (
                  <>
                    429 with Retry-After,{" "}
                    <a
                      href="#limits"
                      className="hit-44 inline-block text-accent underline underline-offset-2 decoration-1"
                    >
                      details
                    </a>
                  </>
                ),
                size: "normal",
                wrap: true,
              },
            ]}
          />
        </div>
      </section>

      <section
        ref={llmsRef}
        id="llms"
        aria-labelledby="h-llms"
        className="grid grid-cols-1 gap-8 border-b-(length:--hairline) border-rule-strong py-6 lg:grid-cols-[minmax(0,5fr)_minmax(0,7fr)]"
      >
        <div className="lg:sticky lg:top-4 lg:self-start">
          <h2 id="h-llms" className="font-serif text-22 font-medium text-ink">
            llms.txt
          </h2>
          <p className="mt-1 font-mono text-12 text-ink-2">GET /llms.txt</p>
          <p className="mt-3 max-w-(--container-prose) text-13 text-ink-2">
            The file an agent reads first: one line per ready dossier from the latest most-read
            list, linking to the Markdown dossier at an {formatNumber(EXAMPLE_BUDGET)} token budget.
            Regenerated every 5 minutes; dossiers still building are left out, so every link
            resolves 200.
          </p>
          <CodeBlock
            className="mt-4"
            heading="Request"
            code={`curl -s ${llmsTxtUrl(base)}`}
            copy={{
              id: "llms_req",
              message: "Copied curl request",
              ariaLabel: "Copy llms.txt request",
            }}
            onCopy={setToast}
          />
        </div>
        <div className="flex flex-col gap-3">
          <CodeBlock
            className="min-h-(--size-example-llms)"
            heading={`Response excerpt${snapshotLabel}, text/markdown`}
            comments={false}
            code={
              llmsQuery.data
                ? head(llmsQuery.data, EXCERPT_LINES)
                : placeholder(llmsQuery.isError, llmsInView)
            }
          />
        </div>
      </section>

      <section
        ref={jsonRef}
        id="json"
        aria-labelledby="h-json"
        className="grid grid-cols-1 gap-8 border-b-(length:--hairline) border-rule-strong py-6 lg:grid-cols-[minmax(0,5fr)_minmax(0,7fr)]"
      >
        <div className="lg:sticky lg:top-4 lg:self-start">
          <h2 id="h-json" className="font-serif text-22 font-medium text-ink">
            Dossier as JSON
          </h2>
          <p className="mt-1 font-mono text-12 text-ink-2">
            {`GET ${dossierJsonUrl("", "{page_id}", EXAMPLE_BUDGET)}`}
          </p>
          <p className="mt-3 max-w-(--container-prose) text-13 text-ink-2">
            Sections with their model summaries, the source sections that fit the budget (
            <code className="font-mono">chunks</code>), citations and freshness, as typed JSON in
            three parts. Without <code className="font-mono">parts</code> the response holds the
            dossier part alone: no revision pin, no budget line, no citations. The example below
            asks for all three. GET never builds; a dossier that has never been built answers 404{" "}
            <code className="font-mono">not_built</code>, use POST or find the page_id via{" "}
            <code className="font-mono">GET /api/v1/search?q={EXAMPLE_TITLE}</code>. Page URLs on
            this site write the numeric form,{" "}
            <code className="font-mono">?budget={EXAMPLE_BUDGET}</code>; the API also accepts{" "}
            <code className="font-mono">2k</code>, <code className="font-mono">8k</code> and{" "}
            <code className="font-mono">32k</code> as aliases for{" "}
            <code className="font-mono">budget=</code>, though this app's own URLs never write them.
          </p>
          <CodeBlock
            className="mt-4"
            heading="Request"
            code={`curl -s '${dossierJsonUrl(base, EXAMPLE_PAGE_ID, EXAMPLE_BUDGET, FULL_PARTS)}'`}
            copy={{
              id: "json_req",
              message: "Copied curl request",
              ariaLabel: "Copy JSON request",
            }}
            onCopy={setToast}
          />
          <Record
            className="mt-4"
            label="Dossier JSON parameters"
            wrap
            rows={[
              { label: "page_id", value: "integer, from search", size: "normal" },
              { label: "budget", value: "2000, 8000 (default) or 32000", size: "normal" },
              { label: "format", value: "json (default) or md", size: "normal" },
              {
                label: "summaries",
                value: "false (default); true adds labelled model summaries",
                size: "normal",
              },
              {
                label: "parts",
                value: "dossier (default), plus metadata and sources; dossier is required",
                size: "normal",
              },
              {
                label: "Headers",
                value: "ETag, WKE-Dossier-Tokens, WKE-Total-Tokens, WKE-Freshness",
                size: "normal",
              },
              {
                label: "Pinned revision",
                value: (
                  <>
                    <code className="font-mono">
                      /api/v1/dossiers/{"{page_id}"}/rev/{"{rev_id}"}
                    </code>
                    , cached for a year
                  </>
                ),
                size: "normal",
              },
            ]}
          />
        </div>
        <div className="flex flex-col gap-3">
          <CodeBlock
            className="min-h-(--size-example-json)"
            heading={`Example response for ${EXAMPLE_TITLE}${snapshotLabel}, application/json`}
            code={
              exampleQuery.data && exampleDossier
                ? `HTTP/1.1 200 OK
Content-Type: application/json
ETag: ${exampleQuery.data.etag ?? ELIDED}
WKE-Dossier-Tokens: ${exampleQuery.data.tokens ?? exampleDossier.budget.used_est_tokens}
WKE-Freshness: ${exampleQuery.data.freshness ?? exampleDossier.freshness.state}

${jsonExcerpt(exampleDossier)}`
                : placeholder(exampleQuery.isError, true)
            }
          />
        </div>
      </section>

      <section
        ref={markdownRef}
        id="markdown"
        aria-labelledby="h-md"
        className="grid grid-cols-1 gap-8 border-b-(length:--hairline) border-rule-strong py-6 lg:grid-cols-[minmax(0,5fr)_minmax(0,7fr)]"
      >
        <div className="lg:sticky lg:top-4 lg:self-start">
          <h2 id="h-md" className="font-serif text-22 font-medium text-ink">
            Dossier as Markdown
          </h2>
          <p className="mt-1 font-mono text-12 text-ink-2">
            {`GET ${dossierMarkdownUrl("", "{page_id}", EXAMPLE_BUDGET)}`}
          </p>
          <p className="mt-3 max-w-(--container-prose) text-13 text-ink-2">
            The same dossier as Markdown, ready to paste into a prompt. With all three parts, as in
            the example, a header line pins the revision and permalink; Wikipedia text is quoted
            with its citation tag; each model summary is headed Machine summary (model output) and
            followed by its model, revision and generation time; a section without one says so.
          </p>
          <CodeBlock
            className="mt-4"
            heading="Request"
            code={`curl -s '${dossierMarkdownUrl(base, EXAMPLE_PAGE_ID, EXAMPLE_BUDGET, FULL_PARTS)}'`}
            copy={{
              id: "md_req",
              message: "Copied curl request",
              ariaLabel: "Copy Markdown request",
            }}
            onCopy={setToast}
          />
        </div>
        <div className="flex flex-col gap-3">
          <CodeBlock
            className="min-h-(--size-example-markdown)"
            heading={`Example response for ${EXAMPLE_TITLE}${snapshotLabel}, text/markdown`}
            comments={false}
            code={
              markdownQuery.data
                ? head(markdownQuery.data, EXCERPT_LINES)
                : placeholder(markdownQuery.isError, markdownInView)
            }
          />
        </div>
      </section>

      <section
        id="build"
        aria-labelledby="h-build"
        className="grid grid-cols-1 gap-8 border-b-(length:--hairline) border-rule-strong py-6 lg:grid-cols-[minmax(0,5fr)_minmax(0,7fr)]"
      >
        <div className="lg:sticky lg:top-4 lg:self-start">
          <h2 id="h-build" className="font-serif text-22 font-medium text-ink">
            Build a dossier
          </h2>
          <p className="mt-1 font-mono text-12 text-ink-2">
            POST /api/v1/dossiers, then GET /api/v1/jobs/{"{job_id}"}
          </p>
          <p className="mt-3 max-w-(--container-prose) text-13 text-ink-2">
            If the current revision is already built, you get the dossier back with 200. Otherwise
            the build is queued: 202, a job id and a Location to poll every poll_after_ms. Two
            requests for the same page share one job. Jobs expire after an hour; a 404 on the job
            means POST again.
          </p>
          <CodeBlock
            className="mt-4"
            heading="Request, then poll"
            code={`curl -s -X POST ${base}/api/v1/dossiers \\
  -H 'Content-Type: application/json' \\
  -d '{"title": "${EXAMPLE_TITLE}"}'

curl -s ${base}/api/v1/jobs/4c1e9b07a2d35f86`}
            copy={{
              id: "job_req",
              message: "Copied curl request",
              ariaLabel: "Copy build request",
            }}
            onCopy={setToast}
          />
          <Record
            className="mt-4"
            label="Build parameters"
            wrap
            rows={[
              {
                label: "Body",
                value: (
                  <>
                    <code className="font-mono">{'{"title": "..."}'}</code>, redirects followed
                  </>
                ),
                size: "normal",
              },
              {
                label: "Force a rebuild",
                value: <code className="font-mono">"refresh": true</code>,
                size: "normal",
              },
              {
                label: "Limits per client IP",
                value: perMinute(PER_MINUTE.build),
                size: "normal",
              },
            ]}
          />
        </div>
        <div className="flex flex-col gap-3">
          <CodeBlock
            heading="Responses, application/json"
            code={`# POST, not built yet
HTTP/1.1 202 Accepted
Location: /api/v1/jobs/4c1e9b07a2d35f86
Retry-After: 1

{ "id": "4c1e9b07a2d35f86", "page_id": ${EXAMPLE_PAGE_ID},
  "title": "${EXAMPLE_TITLE}", "status": "queued", "stage": "resolve",
  "progress": { "done": 0, "total": 1 }, "queue_position": 1,
  "poll_after_ms": 1000, "partial_available": false,
  "created_at": "<UTC time>", "updated_at": "<UTC time>" }

# GET the job every poll_after_ms, 4 s later
{ "id": "4c1e9b07a2d35f86", "status": "running", "stage": "summarize",
  "progress": { "done": 3, "total": 6 }, "poll_after_ms": 1000,
  "partial_available": true, "updated_at": "<UTC time>" }

# 7 s later
{ "id": "4c1e9b07a2d35f86", "status": "done", "stage": "persist",
  "progress": { "done": 1, "total": 1 },
  "result_url": "${dossierJsonUrl(base, EXAMPLE_PAGE_ID, EXAMPLE_BUDGET)}",
  "finished_at": "<UTC time>" }`}
          />
        </div>
      </section>

      <section
        id="mcp"
        aria-labelledby="h-mcp"
        className="grid grid-cols-1 gap-8 border-b-(length:--hairline) border-rule-strong py-6 lg:grid-cols-[minmax(0,5fr)_minmax(0,7fr)]"
      >
        <div className="lg:sticky lg:top-4 lg:self-start">
          <h2 id="h-mcp" className="font-serif text-22 font-medium text-ink">
            MCP server
          </h2>
          <p className="mt-1 font-mono text-12 text-ink-2">{mcpUrl(base)}</p>
          <p className="mt-3 max-w-(--container-prose) text-13 text-ink-2">
            Streamable HTTP, stateless, no sign-in. Add it to Claude Desktop, Cursor or any MCP
            client and the model can search titles, read the latest most-read list and pull a cited
            dossier itself.
          </p>
          <Record
            className="mt-4"
            label="MCP tools"
            wrap
            rows={[
              {
                label: <code className="font-mono">search_topics</code>,
                value: "query, limit; returns page_id, title, dossier_state",
                size: "normal",
              },
              {
                label: <code className="font-mono">get_dossier</code>,
                value: "title, budget, format; JSON or Markdown",
                size: "normal",
              },
              {
                label: <code className="font-mono">get_trending</code>,
                value: "limit; the latest most-read list with dossier_state",
                size: "normal",
              },
            ]}
          />
          <CodeBlock
            className="mt-4"
            heading="Tool call"
            code={`${mcpDossierCall(EXAMPLE_TITLE, EXAMPLE_BUDGET, "markdown")}

# returns the Markdown above; if the dossier is not built, it waits up
# to 20 s for a partial build, then returns the job status instead`}
            copy={{
              id: "mcp_call",
              message: "Copied MCP tool call",
              ariaLabel: "Copy MCP tool call",
            }}
            onCopy={setToast}
          />
        </div>
        <div className="flex flex-col gap-3">
          <CodeBlock
            heading="Cursor, ~/.cursor/mcp.json"
            code={`{
  "mcpServers": {
    "wke": { "url": "${mcpUrl(base)}" }
  }
}`}
            copy={{
              id: "cursor",
              label: "Copy config",
              message: "Copied MCP config for Cursor",
              ariaLabel: "Copy config: Cursor",
            }}
            onCopy={setToast}
          />
          <CodeBlock
            heading="Claude Desktop, claude_desktop_config.json"
            code={`{
  "mcpServers": {
    "wke": {
      "command": "npx",
      "args": ["-y", "mcp-remote", "${mcpUrl(base)}"]
    }
  }
}`}
            copy={{
              id: "claude",
              label: "Copy config",
              message: "Copied MCP config for Claude Desktop",
              ariaLabel: "Copy config: Claude Desktop",
            }}
            onCopy={setToast}
          />
        </div>
      </section>

      <section
        id="limits"
        aria-labelledby="h-limits"
        className="grid grid-cols-1 gap-8 py-6 lg:grid-cols-[minmax(0,5fr)_minmax(0,7fr)]"
      >
        <div>
          <h2 id="h-limits" className="font-serif text-22 font-medium text-ink">
            Rate limits and errors
          </h2>
          <p className="mt-1 font-mono text-12 text-ink-2">
            429 Too Many Requests, Retry-After in seconds
          </p>
          <p className="mt-3 max-w-(--container-prose) text-13 text-ink-2">
            Limits are per client IP and there is no key to raise them. Every error is{" "}
            <code className="font-mono">application/problem+json</code> with a{" "}
            <code className="font-mono">code</code> and a{" "}
            <code className="font-mono">request_id</code>; quote the request id if you report a
            problem.
          </p>
          <Record className="mt-4" label="Rate limits per route class" wrap rows={LIMIT_ROWS} />
        </div>
        <div className="flex flex-col gap-3">
          <CodeBlock
            heading="Response, application/problem+json"
            code={`HTTP/1.1 429 Too Many Requests
Content-Type: application/problem+json
Retry-After: 38

{ "type": "about:blank", "title": "Too Many Requests", "status": 429,
  "code": "rate_limited",
  "detail": "${PER_MINUTE.search} requests per minute per client IP on /mcp.",
  "request_id": "7d2f0c9a4b1e8365", "retry_after": 38 }`}
          />
        </div>
      </section>

      <Toast message={toast.text} nonce={toast.n} onDismiss={() => setToast(null)} />
    </div>
  );
}
