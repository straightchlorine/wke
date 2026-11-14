import { InfoDot } from "./InfoDot";
import { Chip } from "./Chip";
import { formatDuration, formatNumber, formatRecordDate } from "../lib/format";
import type { MachineSummary } from "../api/generated";

export interface ModelPanelProps {
  summary: MachineSummary;
  /** The rendered passages the summary drew on, each linking to its anchored passage below. */
  chunkLinks?: Array<{ id: string; index: number }>;
  className?: string;
}

/** Sorts chunk links by index and groups consecutive indexes into runs, e.g. 4, 5, 6, 8 gives [4, 5, 6] and [8]. */
function groupChunkRanges(
  chunkLinks: Array<{ id: string; index: number }>,
): Array<Array<{ id: string; index: number }>> {
  const sorted = chunkLinks.toSorted((a, b) => a.index - b.index);
  const groups: Array<Array<{ id: string; index: number }>> = [];
  for (const link of sorted) {
    const last = groups.at(-1);
    const lastLink = last?.at(-1);
    if (last && lastLink && link.index === lastLink.index + 1) {
      last.push(link);
    } else {
      groups.push([link]);
    }
  }
  return groups;
}

/** A passage number: a thumb-sized target under a coarse pointer, plain inline text otherwise. */
const PASSAGE_LINK =
  "text-accent underline pointer-coarse:inline-flex pointer-coarse:min-h-11 pointer-coarse:min-w-11 pointer-coarse:items-center pointer-coarse:justify-center";

/** A panel for a model-written summary. Its dashed border marks the text as model output, not Wikipedia text. */
export function ModelPanel({ summary, chunkLinks = [], className = "" }: ModelPanelProps) {
  const inputTokens = summary.params.input_tokens;
  const chunkRanges = groupChunkRanges(chunkLinks);
  return (
    <div
      data-model-panel=""
      className={`border-(length:--hairline) border-dashed border-rule-strong bg-model p-3 ${className}`}
    >
      <div className="flex flex-wrap items-baseline gap-x-2 text-13 text-ink-2">
        <span className="font-medium">Model summary</span>
        <Chip variant="model">model output</Chip>
        <span className="text-12 text-ink-3">
          {summary.model} revision {summary.model_revision}, generated{" "}
          {formatRecordDate(summary.generated_at)}
          {summary.infer_seconds != null ? ` in ${formatDuration(summary.infer_seconds)}` : ""}
          {inputTokens != null ? `, from ${formatNumber(inputTokens)} tokens of source` : ""}
        </span>
      </div>
      {/* summary.text is rendered verbatim. It is model output, so no client-side cleanup may rewrite it. */}
      <p className="mt-2 max-w-[78ch] text-14 text-ink-2">{summary.text}</p>
      {chunkLinks.length > 0 ? (
        <p className="mt-2 text-12 text-ink-3">
          Summarised from {chunkLinks.length === 1 ? "passage " : "passages "}
          {chunkRanges.map((group, i) => {
            const first = group[0];
            const last = group.at(-1);
            if (!first || !last) {
              return null;
            }
            return (
              <span key={first.id}>
                <a href={`#chunk-${first.id}`} className={PASSAGE_LINK}>
                  {first.index}
                </a>
                {group.length > 1 ? (
                  <>
                    {" to "}
                    <a href={`#chunk-${last.id}`} className={PASSAGE_LINK}>
                      {last.index}
                    </a>
                  </>
                ) : null}
                {i < chunkRanges.length - 1 ? ", " : ""}
              </span>
            );
          })}{" "}
          below.
        </p>
      ) : null}
      <p className="mt-2 text-12 text-ink-3">
        Model output, not Wikipedia. It can be wrong: the section text is the source.
        <InfoDot
          text={`Written by ${summary.model} (revision ${summary.model_revision}), not by Wikipedia. It read the source text of this section.`}
          label="About model summaries"
        />
      </p>
    </div>
  );
}
