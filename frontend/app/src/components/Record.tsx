import type { ReactNode } from "react";

export interface RecordRowProps {
  /** The key label, for example "Model". */
  label: ReactNode;
  /** The value, right of the dotted leader. */
  value: ReactNode;
  /** A second fact about the value, shown inline after it unless `subBlock` or `lines` is set. */
  sub?: ReactNode;
  /** Renders `sub` as a full-width line below the value instead of inline after it. Use it for a second line that needs its own layout, such as a URL next to a copy button. */
  subBlock?: boolean;
  /** Size of the value: "big" for a count, "normal" for any text value such as a title, a URL or a state, and "name" for an article title that links to its dossier. */
  size?: "big" | "normal" | "name";
  /** The native title tooltip over the value, for values that may end in an ellipsis. A plain string `value` is used when this is not set. */
  title?: string;
  /** Lets a "normal" value wrap onto further lines instead of ending in an ellipsis. Use it only for prose, such as the parameter lists on the machines page. */
  wrap?: boolean;
  /** Draws the dotted leader between label and value. */
  leader?: boolean;
  /** Puts label, leader and value on one baseline, with the value right-aligned to the record's edge. `sub` is right-aligned under the value and `below` under that. `Record` sets it when its own `lines` is on. */
  lines?: boolean;
  /** Lines mode only: content shown under the `sub` line, such as the value's own actions. */
  below?: ReactNode;
  /** A shorter row, for a "normal" row packed into the fixed-height panel in PlateBoard. */
  dense?: boolean;
}

/** One row of a `Record`: a label and a value, with an optional dotted leader between them and an optional second fact. */
export function RecordRow({
  label,
  value,
  sub,
  subBlock = false,
  size = "big",
  title,
  leader = true,
  wrap = false,
  lines = false,
  below,
  dense = false,
}: RecordRowProps) {
  const big = size === "big";
  if (lines) {
    const valueClass =
      size === "big"
        ? "shrink-0 text-18 text-ink tabular-nums"
        : size === "name"
          ? "min-w-0 truncate font-serif text-15 text-ink [@media(pointer:coarse)]:-my-3.5 [@media(pointer:coarse)]:py-3.5"
          : "shrink-0 text-13 text-ink-2 tabular-nums";
    return (
      <div className="py-1">
        <div
          data-record-row=""
          className="flex min-h-7 items-baseline gap-x-2 text-13 pointer-coarse:min-h-11"
        >
          <span className="shrink-0 whitespace-nowrap text-ink-2">{label}</span>
          {leader ? (
            <span
              aria-hidden="true"
              className="min-w-3 flex-1 border-b-(length:--hairline) border-dotted border-rule-strong"
            />
          ) : null}
          <span
            title={title ?? (typeof value === "string" ? value : undefined)}
            className={`whitespace-nowrap text-right ${valueClass}`}
          >
            {value}
          </span>
        </div>
        <p
          data-record-sub=""
          className={`min-h-4 text-right text-12 text-ink-3 tabular-nums ${sub != null && typeof sub !== "string" ? "pointer-coarse:flex pointer-coarse:min-h-11 pointer-coarse:items-center pointer-coarse:justify-end" : ""}`}
        >
          {sub}
        </p>
        {below}
      </div>
    );
  }
  const unitInColumn = big && !subBlock;
  // A text row with no second fact keeps its label and value on one line.
  // The value ends in an ellipsis, or wraps inside its own box when `wrap` is set. Every other row may wrap as a whole.
  const oneLine = !big && !subBlock && sub == null;
  const truncates = oneLine && !wrap;
  // A row that holds a link, chip or tooltip gets a thumb-high row under a coarse pointer.
  const hasControl = [label, value, sub].some(
    (part) => part != null && typeof part !== "string" && typeof part !== "number",
  );
  return (
    <div
      data-record-row=""
      className={`flex items-baseline gap-x-2 text-13 ${oneLine ? "" : "flex-wrap"} ${big ? "min-h-9 py-1" : dense ? "min-h-6 py-[3px]" : "min-h-8 py-1.5"} ${hasControl ? "pointer-coarse:min-h-11 pointer-coarse:items-center" : ""}`}
    >
      <span className={`text-ink-2 whitespace-nowrap ${oneLine ? "shrink-0" : ""}`}>{label}</span>
      {leader ? (
        <span
          aria-hidden="true"
          className="min-w-3 flex-1 border-b-(length:--hairline) border-dotted border-rule-strong"
        />
      ) : null}
      <span
        title={title ?? (typeof value === "string" ? value : undefined)}
        className={`${big ? "text-18" : "text-13"} text-ink tabular-nums text-right ${truncates ? `min-w-0 truncate ${hasControl ? "pointer-coarse:-my-3.5 pointer-coarse:py-3.5" : ""}` : oneLine ? "min-w-0 wrap-anywhere" : ""}`}
      >
        {value}
      </span>
      {sub != null ? (
        <span
          className={
            subBlock
              ? "basis-full text-12 text-ink-3 tabular-nums"
              : `text-13 text-ink-3 tabular-nums ${unitInColumn ? "basis-full text-right @min-[360px]:basis-auto @min-[360px]:text-left @min-[460px]:basis-[190px] @min-[460px]:shrink-0" : ""}`
          }
        >
          {sub}
        </span>
      ) : null}
    </div>
  );
}

export interface RecordProps {
  rows: RecordRowProps[];
  /** The accessible name of the record's group of rows. */
  label?: string;
  /** Lets every "normal" row's value wrap, as `RecordRowProps.wrap` does for one row. */
  wrap?: boolean;
  /** A block under the last row, flush with the record's left edge. */
  footer?: ReactNode;
  /** Puts each row's label, leader and value on one baseline, with the value right-aligned to the record's edge. Each row's second fact sits right-aligned under the value. */
  lines?: boolean;
  className?: string;
}

/** A block of key/value rows with an ink rule on top. */
export function Record({ rows, label, wrap, footer, lines = false, className = "" }: RecordProps) {
  return (
    <div
      data-record=""
      role={label ? "group" : undefined}
      aria-label={label}
      className={`@container border-t-(length:--hairline) border-ink ${className}`}
    >
      {lines
        ? rows.map((row, index) => <RecordRow key={index} lines {...row} />)
        : rows.map((row, index) => <RecordRow key={index} wrap={wrap} {...row} />)}
      {footer != null ? <div className="pb-2 pt-1">{footer}</div> : null}
    </div>
  );
}
