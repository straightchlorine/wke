import type { Budget } from "../lib/budget";
import { dossierJsonUrl, dossierMarkdownUrl, llmsTxtUrl, mcpUrl } from "../lib/endpoints";
import { EndpointRow } from "./EndpointRow";
import { SectionTitle } from "./SectionTitle";

export interface MachineCellsProps {
  /** The public origin the URLs start with. */
  origin: string;
  /** The dossier the JSON and Markdown cells point at. Null shows a URL pattern and disables their buttons. */
  pageId: number | null;
  budget: Budget;
  /** Receives the message of each copy button after a successful copy. */
  onCopy: (message: string) => void;
}

/** The "For machines" section: one box per machine-readable endpoint, each with a copy button. */
export function MachineCells({ origin, pageId, budget, onCopy }: MachineCellsProps) {
  const jsonUrl = pageId != null ? dossierJsonUrl(origin, pageId, budget) : null;
  const markdownUrl = pageId != null ? dossierMarkdownUrl(origin, pageId, budget) : null;
  const llmsUrl = llmsTxtUrl(origin);
  const mcp = mcpUrl(origin);
  return (
    <div className="mt-12">
      <SectionTitle sub="Every dossier is one HTTP call, with the revision id it was built from.">
        For machines
      </SectionTitle>
      <div className="mt-2 grid grid-cols-1 gap-(--hairline) border-(length:--hairline) border-ink bg-rule-strong sm:grid-cols-2 xl:grid-cols-4">
        <EndpointRow
          id="llms"
          label="llms.txt"
          ariaLabel="Copy URL: llms.txt"
          sentence="A plain-text index of built dossiers, for a model to read directly."
          line={`GET ${llmsUrl}`}
          copyText={llmsUrl}
          message="Copied URL"
          onCopy={onCopy}
        />
        <EndpointRow
          id="json"
          label="JSON"
          ariaLabel="Copy URL: JSON"
          sentence="The full dossier as data: sections, citations and passages."
          line={`GET ${jsonUrl ?? dossierJsonUrl("", "{page_id}", budget)}`}
          copyText={jsonUrl}
          message="Copied URL"
          onCopy={onCopy}
        />
        <EndpointRow
          id="markdown"
          label="Markdown"
          ariaLabel="Copy URL: Markdown"
          sentence="The same dossier, rendered as Markdown with inline citations."
          line={`GET ${markdownUrl ?? dossierMarkdownUrl("", "{page_id}", budget)}`}
          copyText={markdownUrl}
          message="Copied URL"
          onCopy={onCopy}
        />
        <EndpointRow
          id="mcp"
          label="MCP"
          sentence="An MCP tool that builds and returns a dossier for a topic."
          line={mcp}
          copyText={`{"mcpServers":{"wke":{"url":"${mcp}"}}}`}
          copyLabel="Copy config"
          ariaLabel="Copy config: MCP"
          message="Copied MCP config"
          onCopy={onCopy}
        />
      </div>
    </div>
  );
}
