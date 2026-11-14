import type { DossierView } from "../api/dossier";
import type { Budget } from "../lib/budget";
import { stageDurationRows } from "../lib/buildProgress";
import { llmsTxtUrl, mcpDossierCall } from "../lib/endpoints";
import { formatSummaryScope } from "../lib/format";
import { publicBaseUrl } from "../lib/publicBaseUrl";
import { endpointRecordRow } from "./EndpointRow";
import { Record } from "./Record";
import { SectionTitle } from "./SectionTitle";

export interface DossierDataRecordsProps {
  dossier: DossierView;
  budget: Budget;
  /** Called with the message of every successful copy. */
  onCopy: (message: string) => void;
}

/** The addresses the dossier can be fetched from, each with a copy button, and the record of how it was built. */
export function DossierDataRecords({ dossier, budget, onCopy }: DossierDataRecordsProps) {
  const mcpCall = mcpDossierCall(dossier.topic.title, budget, "json");
  const llmsTxt = llmsTxtUrl(publicBaseUrl(dossier.links.self));
  const { build } = dossier;
  return (
    <>
      <SectionTitle>This dossier as data</SectionTitle>
      <Record
        className="mt-2"
        rows={[
          endpointRecordRow({
            label: "JSON",
            line: `GET ${dossier.links.self}`,
            copyText: dossier.links.self,
            ariaLabel: "Copy JSON URL",
            message: "Copied JSON URL",
            onCopy,
          }),
          endpointRecordRow({
            label: "Markdown",
            line: `GET ${dossier.links.markdown}`,
            copyText: dossier.links.markdown,
            ariaLabel: "Copy Markdown URL",
            message: "Copied Markdown URL",
            onCopy,
          }),
          endpointRecordRow({
            label: "llms.txt",
            line: `GET ${llmsTxt}`,
            copyText: llmsTxt,
            ariaLabel: "Copy llms.txt URL",
            message: "Copied llms.txt URL",
            onCopy,
          }),
          endpointRecordRow({
            label: "MCP",
            line: mcpCall,
            copyText: mcpCall,
            copyLabel: "Copy",
            ariaLabel: "Copy MCP tool call",
            message: "Copied MCP tool call",
            onCopy,
          }),
        ]}
      />

      <SectionTitle className="mt-6">Build</SectionTitle>
      <Record
        className="mt-2"
        rows={[
          {
            label: "State",
            value: build.state === "complete" ? "Ready" : "Partial",
            size: "normal",
          },
          {
            label: "Analysis",
            value: build.analysis === "ml" ? "k-means on MiniLM" : "headings only",
            size: "normal",
          },
          {
            label: "Model summaries",
            value: formatSummaryScope(
              build.summaries_done,
              build.summaries_total,
              dossier.sections.length,
            ),
            size: "normal",
          },
          ...(build.truncated
            ? [{ label: "Parsed", value: "first 400 passages only", size: "normal" as const }]
            : []),
          ...stageDurationRows(build.stage_seconds),
        ]}
      />
    </>
  );
}
