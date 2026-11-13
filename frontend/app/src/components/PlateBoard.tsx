import type { MouseEvent } from "react";
import { isPlainLeftClick } from "../lib/clicks";
import type { PlateBoardNode } from "../lib/graphNodeInfo";
import { Chip, DOSSIER_STATE_CHIP } from "./Chip";
import { InfoDot } from "./InfoDot";
import { RecordRow } from "./Record";

export type { PlateBoardNode };

export interface PlateBoardProps {
  /** The node to show; null shows the idle hint. */
  node: PlateBoardNode | null;
  /** True for the selected node: the badge becomes the dossier link. */
  selected?: boolean;
  /** True on a touch screen, where the hint says "tap". */
  touch?: boolean;
  /** Called when the badge link is clicked, in place of following its href. */
  onOpen?: () => void;
}

/** Returns the "Linked to" value: the first two titles, then "+n" for the rest, or "Not linked today" for none. */
export function linkedValue(linkedTo: string[]): string {
  const [first, second] = linkedTo;
  if (first == null) {
    return "Not linked today";
  }
  if (second == null) {
    return first;
  }
  return linkedTo.length > 2
    ? `${first}, ${second}, +${linkedTo.length - 2}`
    : `${first}, ${second}`;
}

/**
 * The box under a graph's frame that shows the pointed-at or selected node, or a hint while idle.
 * The slot in `Plate` fixes its height (`PLATE_BOARD_PX`). The badge in its Dossier row becomes a
 * link once the node is selected.
 */
export function PlateBoard({ node, selected = false, touch = false, onOpen }: PlateBoardProps) {
  const base = `h-full overflow-hidden border-(length:--hairline) px-3 py-2 text-13 ${selected ? "border-ink bg-sunken" : "border-rule-strong bg-sheet"}`;
  if (!node) {
    return (
      <section
        aria-label="Selected article"
        data-plate-board="idle"
        className={`${base} flex items-center justify-center`}
      >
        <p className="text-center text-13 text-ink-3">
          {touch
            ? "Tap a dot to see it here. Tap it again to open its dossier."
            : "Point at a dot to see it here. Click it to select, then open its dossier."}
        </p>
      </section>
    );
  }
  function handleClick(event: MouseEvent<HTMLAnchorElement>) {
    if (!isPlainLeftClick(event)) {
      return;
    }
    event.preventDefault();
    onOpen?.();
  }
  const edits =
    node.editsUnavailable === true
      ? "no edit data"
      : node.editsLastHour == null
        ? (node.editsMissing ?? "not measured")
        : node.editsLastHour.toLocaleString("en-US");
  const badge =
    node.state == null
      ? { variant: "built" as const, text: "Open" }
      : DOSSIER_STATE_CHIP[node.state];
  // The badge has a fixed width that fits the widest state text, so its words do not shift when
  // the node is selected.
  const badgeChip = (
    <Chip
      variant={badge.variant}
      className={`w-17 justify-center ${selected ? "text-accent!" : ""}`}
    >
      <span className={selected ? "underline decoration-1 underline-offset-2" : undefined}>
        {badge.text}
      </span>
    </Chip>
  );
  const linked = linkedValue(node.linkedTo);
  return (
    <section
      aria-label="Selected article"
      data-plate-board={selected ? "selected" : "preview"}
      className={`${base} flex flex-col`}
    >
      <p title={node.title} className="h-6 shrink-0 truncate font-serif text-16 leading-6 text-ink">
        {node.title}
      </p>
      <p
        data-plate-description=""
        title={node.description}
        className="h-4 shrink-0 truncate text-12 leading-4 text-ink-3"
      >
        {node.description}
      </p>
      <RecordRow
        dense
        size="normal"
        label={node.figure?.label ?? node.figureLabel ?? "Views"}
        value={node.figure?.value ?? "not measured"}
      />
      <RecordRow dense size="normal" label="Edits in the last hour" value={edits} />
      <RecordRow
        dense
        size="normal"
        label="Linked to"
        title={selected ? undefined : node.linkedTo.join(", ")}
        value={
          selected && node.linkedTo.length > 0 ? (
            <InfoDot
              text={node.linkedTo.join(", ")}
              className="flex min-w-0 justify-end"
              triggerClassName="block min-w-0 max-w-full truncate"
            >
              {linked}
            </InfoDot>
          ) : (
            linked
          )
        }
      />
      <RecordRow
        dense
        size="normal"
        label="Dossier"
        value={
          <span data-plate-badge="" className="inline-flex">
            {selected ? (
              <a
                href={node.href}
                onClick={handleClick}
                className="inline-flex"
                aria-label={
                  node.state === "none"
                    ? "Build dossier, not built"
                    : `Open dossier, ${badge.text.toLowerCase()}`
                }
              >
                {badgeChip}
              </a>
            ) : (
              <span className="pointer-events-none inline-flex">{badgeChip}</span>
            )}
          </span>
        }
      />
    </section>
  );
}
