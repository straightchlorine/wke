import type { Budget } from "./budget";

/** Where the dossier a URL points at is given: by page id, or by the "{page_id}" placeholder in a pattern. */
type PageRef = number | "{page_id}";

function dossierQuery(budget: Budget, parts?: string): string {
  return parts ? `budget=${budget}&parts=${parts}` : `budget=${budget}`;
}

/** The llms.txt URL. */
export function llmsTxtUrl(base: string): string {
  return `${base}/llms.txt`;
}

/**
 * The URL of a dossier as JSON.
 * Pass an empty `base` for the bare path, and "{page_id}" as the page for a pattern.
 */
export function dossierJsonUrl(
  base: string,
  page: PageRef,
  budget: Budget,
  parts?: string,
): string {
  return `${base}/api/v1/dossiers/${page}?${dossierQuery(budget, parts)}`;
}

/** The URL of a dossier as Markdown, built like `dossierJsonUrl`. */
export function dossierMarkdownUrl(
  base: string,
  page: PageRef,
  budget: Budget,
  parts?: string,
): string {
  return `${base}/api/v1/dossiers/${page}.md?${dossierQuery(budget, parts)}`;
}

/** The URL of the MCP server. */
export function mcpUrl(base: string): string {
  return `${base}/mcp`;
}

/** The text of a `get_dossier` call on the MCP server. */
export function mcpDossierCall(title: string, budget: Budget, format: "json" | "markdown"): string {
  return `get_dossier({ "title": ${JSON.stringify(title)}, "budget": ${budget}, "format": "${format}" })`;
}
