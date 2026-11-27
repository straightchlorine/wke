import type { LinkSpan } from "../api/generated";

/** A stretch of a chunk's text, as UTF-16 offsets into it (end exclusive), the unit a JavaScript string indexes in. */
export interface Range {
  start: number;
  end: number;
}

/** The "(N rows; M shown)" line a table or list ends with when it was cut at a row or item boundary. */
export interface CountNote {
  total: number;
  shown: number;
  noun: "rows" | "items";
}

/** A table chunk read into a caption, a header row and body rows, every cell a range of the chunk's text. */
export interface TableLayout {
  caption: string;
  header: Range[];
  rows: Range[][];
  note: CountNote | null;
}

/** A list item as a range of the chunk's text, with the items nested under it. */
export interface ListItem extends Range {
  children: ListItem[];
}

/** A list chunk read into its items, nested where the text indents, and its count note. */
export interface ListLayout {
  items: ListItem[];
  note: CountNote | null;
}

/** A run of a cell's or item's text; `title` names the Wikipedia article when the run is a link. */
export interface Piece {
  text: string;
  title: string | null;
}

/** A link span with UTF-16 offsets. */
export interface TextLink extends Range {
  title: string;
}

interface Line {
  text: string;
  offset: number;
}

const NOTE = /^\((\d+) (rows|items); (\d+) shown\)$/;
const SEPARATOR_CELL = /^:?-+:?$/;
const ITEM = /^( *)- (\S.*)$/;
const ESCAPED_PIPE = /\\\|/g;
const SURROGATE = /[\ud800-\udfff]/;

function readLines(text: string): { lines: Line[]; note: CountNote | null } {
  let offset = 0;
  const lines = text.split("\n").map((line) => {
    const read = { text: line.trimEnd(), offset };
    offset += line.length + 1;
    return read;
  });
  while (lines.length > 0 && lines[lines.length - 1]!.text === "") {
    lines.pop();
  }
  const match = NOTE.exec(lines[lines.length - 1]?.text ?? "");
  if (!match) {
    return { lines, note: null };
  }
  lines.pop();
  return {
    lines,
    note: {
      total: Number(match[1]),
      shown: Number(match[3]),
      noun: match[2] === "rows" ? "rows" : "items",
    },
  };
}

function trimmed(line: string, from: number, to: number, offset: number): Range {
  let start = from;
  let end = to;
  while (start < end && /\s/.test(line[start]!)) {
    start += 1;
  }
  while (end > start && /\s/.test(line[end - 1]!)) {
    end -= 1;
  }
  return { start: offset + start, end: offset + end };
}

/** Splits a "| a | b |" line at its unescaped pipes, or returns null when the line is not a pipe row. */
function splitRow(line: Line): Range[] | null {
  const { text, offset } = line;
  if (text.length < 2 || !text.startsWith("|") || !text.endsWith("|")) {
    return null;
  }
  const cells: Range[] = [];
  let from = 1;
  for (let i = 1; i < text.length; i += 1) {
    if (text[i] === "\\" && text[i + 1] === "|") {
      i += 1;
    } else if (text[i] === "|") {
      cells.push(trimmed(text, from, i, offset));
      from = i + 1;
    }
  }
  return cells;
}

const isEmpty = (text: string, range: Range) => text.slice(range.start, range.end) === "";

function isSeparator(text: string, line: Line): boolean {
  const cells = splitRow(line);
  return (
    cells != null &&
    cells.length > 0 &&
    cells.every((cell) => SEPARATOR_CELL.test(text.slice(cell.start, cell.end)))
  );
}

/**
 * Reads a table chunk's text: a caption line, a header row, a `| --- |` row, pipe rows and an optional count note.
 * Returns null when the text has any other shape, so the caller shows it as plain text.
 * A column with no header and no cell text is dropped, and a short row is padded with empty cells.
 */
export function parseTable(text: string): TableLayout | null {
  const { lines, note } = readLines(text);
  const first = lines[0] ? splitRow(lines[0]) : null;
  const headAt = first && lines[1] && isSeparator(text, lines[1]) ? 0 : 1;
  const head = lines[headAt] ? splitRow(lines[headAt]) : null;
  if (!head || !lines[headAt + 1] || !isSeparator(text, lines[headAt + 1]!)) {
    return null;
  }
  const rows: Range[][] = [];
  for (const line of lines.slice(headAt + 2)) {
    const cells = splitRow(line);
    if (!cells) {
      return null;
    }
    rows.push(cells);
  }
  if (rows.length === 0) {
    return null;
  }
  const width = Math.max(head.length, ...rows.map((row) => row.length));
  const blank: Range = { start: 0, end: 0 };
  const fill = (row: Range[]) => Array.from({ length: width }, (_unused, i) => row[i] ?? blank);
  const header = fill(head);
  const body = rows.map(fill);
  const keep = Array.from({ length: width }, (_unused, i) => i).filter(
    (i) => !isEmpty(text, header[i]!) || body.some((row) => !isEmpty(text, row[i]!)),
  );
  if (keep.length === 0) {
    return null;
  }
  return {
    caption: headAt === 1 ? (lines[0]?.text.trim() ?? "") : "",
    header: keep.map((i) => header[i]!),
    rows: body.map((row) => keep.map((i) => row[i]!)),
    note,
  };
}

/**
 * Reads a list chunk's text: "- item" lines, a nested item indented by two spaces per level, and an optional count note.
 * Returns null when a line is not an item, so the caller shows the text as it is.
 */
export function parseList(text: string): ListLayout | null {
  const { lines, note } = readLines(text);
  if (lines.length === 0) {
    return null;
  }
  const items: ListItem[] = [];
  const levels: ListItem[][] = [items];
  for (const line of lines) {
    const match = ITEM.exec(line.text);
    if (!match) {
      return null;
    }
    const indent = match[1]!.length;
    const depth = Math.min(Math.floor(indent / 2), levels.length - 1);
    const item: ListItem = {
      start: line.offset + indent + 2,
      end: line.offset + line.text.length,
      children: [],
    };
    levels.length = depth + 1;
    levels[depth]!.push(item);
    levels.push(item.children);
  }
  return { items, note };
}

/** The link spans of a chunk with their code-point offsets turned into UTF-16 offsets of its text. */
export function textLinks(text: string, links: readonly LinkSpan[] | undefined): TextLink[] {
  if (!links || links.length === 0) {
    return [];
  }
  if (!SURROGATE.test(text)) {
    return links.map(({ start, end, title }) => ({ start, end, title }));
  }
  const at = [0];
  for (const char of text) {
    at.push(at[at.length - 1]! + char.length);
  }
  return links
    .filter((link) => link.end < at.length)
    .map(({ start, end, title }) => ({ start: at[start]!, end: at[end]!, title }));
}

/**
 * Cuts the text of one cell or item into plain runs and the runs the links cover.
 * A link that is not wholly inside the range is left out; `unescape` turns an escaped pipe back into a pipe.
 */
export function pieces(
  text: string,
  range: Range,
  links: readonly TextLink[],
  unescape: boolean,
): Piece[] {
  const clean = (value: string) => (unescape ? value.replace(ESCAPED_PIPE, "|") : value);
  const inside = links
    .filter((link) => link.start >= range.start && link.end <= range.end && link.end > link.start)
    .toSorted((a, b) => a.start - b.start);
  const out: Piece[] = [];
  let cursor = range.start;
  for (const link of inside) {
    if (link.start < cursor) {
      continue;
    }
    if (link.start > cursor) {
      out.push({ text: clean(text.slice(cursor, link.start)), title: null });
    }
    out.push({ text: clean(text.slice(link.start, link.end)), title: link.title });
    cursor = link.end;
  }
  if (cursor < range.end) {
    out.push({ text: clean(text.slice(cursor, range.end)), title: null });
  }
  return out;
}
