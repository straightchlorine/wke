import { useEffect, useRef } from "react";
import { useNavigate } from "@tanstack/react-router";
import type { MouseEvent } from "react";
import { isPlainLeftClick } from "../lib/clicks";
import { focusSectionHeading } from "../lib/sectionJump";

export interface SectionChipItem {
  id: string;
  /** Short label ("1 Lead"); the full label lives in `title`. */
  label: string;
  title: string;
  /** True when the current budget folded this section. */
  held: boolean;
  /** Nesting depth from the section's heading path; 1 for top-level sections. */
  depth: number;
}

export interface SectionChipsProps {
  items: SectionChipItem[];
  currentId: string | null;
  className?: string;
}

/** Horizontally scrolling strip of section links, sticky and shown in place of the Contents rail when the rail is hidden. */
export function SectionChips({ items, currentId, className = "" }: SectionChipsProps) {
  const currentRef = useRef<HTMLAnchorElement | null>(null);
  const stripRef = useRef<HTMLElement | null>(null);
  const navigate = useNavigate();

  // Scrolls the strip itself, not the page, so a chip clipped at the strip's edge comes into view.
  // scrollIntoView is avoided because its vertical scrolling can pick the window and undo the jump that made this chip current.
  // A strip hidden by the Contents rail has zero width, so the effect returns early there.
  useEffect(() => {
    const chip = currentRef.current;
    const strip = stripRef.current;
    if (!chip || !strip || strip.clientWidth === 0) {
      return;
    }
    const target = chip.offsetLeft + chip.offsetWidth / 2 - strip.clientWidth / 2;
    strip.scrollLeft = Math.max(0, target);
    // currentRef/stripRef themselves never change; currentId is what should retrigger this.
    // oxlint-disable-next-line react/exhaustive-effect-dependencies
  }, [currentId]);

  // A plain anchor keeps middle-click and open-in-new-tab working. A plain left click goes through navigate() so the router's location.hash updates.
  // <Link> is avoided because it forces aria-current="page" on the chip whose hash matches the URL, overriding the "location" value set from currentId.
  function handleClick(event: MouseEvent<HTMLAnchorElement>, id: string) {
    if (!isPlainLeftClick(event)) {
      return;
    }
    event.preventDefault();
    void navigate({
      to: ".",
      search: true,
      hash: id,
      hashScrollIntoView: { block: "start" },
    }).then(() => focusSectionHeading(id));
  }

  return (
    <nav
      ref={stripRef}
      aria-label="Sections"
      className={`sticky z-10 flex gap-x-2 thin-scroll overflow-x-auto border-b-(length:--hairline) border-rule bg-sheet px-4 py-2 text-13 whitespace-nowrap min-[600px]:top-(--toolbar-h) max-[599px]:top-0 max-[599px]:py-3 ${className}`}
    >
      {items.map((item) => (
        <a
          key={item.id}
          ref={item.id === currentId ? currentRef : undefined}
          href={`#${item.id}`}
          onClick={(event) => handleClick(event, item.id)}
          title={item.title}
          data-depth={item.depth}
          aria-current={item.id === currentId ? "location" : undefined}
          className={`relative flex max-w-[20ch] shrink-0 items-center rounded-1 border-(length:--hairline) px-2 pointer-coarse:min-h-11 max-[599px]:after:absolute max-[599px]:after:inset-x-0 max-[599px]:after:-inset-y-3.5 max-[599px]:after:content-[''] ${
            item.id === currentId
              ? "border-accent bg-wash text-accent shadow-[inset_0_-2px_0_var(--color-accent)] font-medium"
              : item.held
                ? "border-rule-strong text-ink-3"
                : "border-rule-strong text-ink-2"
          }`}
        >
          <span className="min-w-0 truncate">
            {item.label}
            {item.held ? ", some left out" : ""}
          </span>
        </a>
      ))}
    </nav>
  );
}
