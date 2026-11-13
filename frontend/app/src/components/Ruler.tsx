import { useLayoutEffect, useRef, useState } from "react";
import { formatNumber } from "../lib/format";
import { type RulerLabel, thinLabels, tokenToFraction } from "../lib/rulerLabels";

export interface RulerProps {
  /** The budget's total, in tokens. */
  total: number;
  /** Tokens included so far; the accent fill runs up to this value. */
  filled: number;
  /** Tokens between hairline ticks. */
  tickEvery: number;
  /** Tokens between numbered ticks. */
  labelEvery: number;
  /**
   * Each dossier section's start offset, labelled at the section's start.
   * `fraction`, when given, is the measured position of the label (0 to 1, top to bottom) and replaces the lookup from `offset`.
   * A heading-only section holds no tokens, so its offset equals the next section's and the offset alone cannot tell the two labels apart.
   */
  sectionOffsets?: Array<{ id: string; label: string; offset: number; fraction?: number }>;
  /**
   * Maps a token offset to its position (0 to 1, top to bottom) inside the ruler, measured from the article's rendered layout.
   * Sorted ascending by `token` and expected to span from 0 to at least `total`. Without it the scale is linear by token.
   */
  breakpoints?: Array<{ token: number; fraction: number }>;
  className?: string;
}

/** The x position of the ruler's line inside its gutter, which leaves room for the tick numbers inside the column. */
const RULE_X = 40;

/** A vertical ruler with 0 at the top: hairline ticks, numbered labels and an accent fill down to the included token count. */
export function Ruler({
  total,
  filled,
  tickEvery,
  labelEvery,
  sectionOffsets = [],
  breakpoints = [],
  className = "",
}: RulerProps) {
  const clampedFilled = Math.min(total, Math.max(0, filled));
  const fractionOf = (token: number) =>
    breakpoints.length > 0 ? tokenToFraction(token, breakpoints) : total > 0 ? token / total : 0;
  const ticks = Array.from({ length: Math.floor(total / tickEvery) + 1 }, (_, i) => i * tickEvery);
  // A tick at the total is not numbered: it sits on the end of the ruler.
  const isLabelled = (token: number) => token % labelEvery === 0 && token !== total;

  const trackRef = useRef<HTMLDivElement>(null);
  const [trackHeight, setTrackHeight] = useState(0);
  useLayoutEffect(() => {
    const track = trackRef.current;
    if (!track) {
      return () => {};
    }
    const read = () => setTrackHeight(track.offsetHeight);
    read();
    if (typeof ResizeObserver === "undefined") {
      return () => {};
    }
    const observer = new ResizeObserver(read);
    observer.observe(track);
    return () => observer.disconnect();
  }, []);

  const labelledTicks = ticks.filter(isLabelled);
  const lastLabelledTick = labelledTicks[labelledTicks.length - 1];
  const labels = thinLabels(
    [
      ...labelledTicks.map((t): RulerLabel => ({
        key: `tick-${t}`,
        text: formatNumber(t),
        pos: fractionOf(t) * trackHeight,
        kind: t === lastLabelledTick ? "end" : "tick",
      })),
      ...sectionOffsets.map((section): RulerLabel => ({
        key: `section-${section.id}`,
        text: formatNumber(section.offset),
        pos: (section.fraction ?? fractionOf(section.offset)) * trackHeight,
        kind: "section",
        title: `${section.label} starts at token ${formatNumber(section.offset)}`,
      })),
    ],
    trackHeight,
  );

  return (
    <div className={`relative tabular-nums ${className}`}>
      <span className="sr-only">
        {formatNumber(clampedFilled)} of {formatNumber(total)} tokens
      </span>
      <div ref={trackRef} aria-hidden="true" className="relative h-full w-12">
        <div
          className="absolute inset-y-0 w-(--hairline) bg-rule-strong"
          style={{ left: RULE_X }}
        />
        <div
          className="absolute top-0 w-0.5 bg-accent"
          style={{ left: RULE_X, height: `${fractionOf(clampedFilled) * 100}%` }}
        />
        {ticks.map((t) => (
          <span
            key={t}
            className="absolute h-(--hairline) bg-rule"
            style={{
              left: RULE_X - (isLabelled(t) ? 6 : 4),
              width: isLabelled(t) ? 12 : 8,
              top: `${fractionOf(t) * 100}%`,
            }}
          />
        ))}
        {labels.map((label) => (
          <span
            key={label.key}
            data-ruler-label=""
            className={`absolute right-3 -translate-y-1/2 text-12 ${label.kind === "section" ? "text-ink-2" : "text-ink-3"}`}
            style={{ top: label.pos }}
            title={label.title}
          >
            {label.text}
          </span>
        ))}
      </div>
    </div>
  );
}
