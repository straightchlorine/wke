import { useEffect, useId, useLayoutEffect, useRef, useState } from "react";
import type { ReactNode } from "react";
import {
  bridgeBox,
  chooseClearSpot,
  placeByTrigger,
  placeUnderFrame,
  scrollKeepsFrame,
  type TipClearance,
} from "../lib/tooltipPlacement";

export type { TipClearance };

export interface InfoDotProps {
  /** The tooltip body; a node when it carries a link (see `interactive`). */
  text: ReactNode;
  /** Accessible label for the dot itself. */
  label?: string;
  className?: string;
  /** Extra classes for the trigger button when `children` stand in for the dot, e.g. to truncate the words to one line. */
  triggerClassName?: string;
  /**
   * Renders only the dot's visual mark, with no button, tooltip or focus stop.
   * Use it where a second button would be wrong, such as inside another InfoDot's trigger.
   */
  decorative?: boolean;
  /**
   * Text that stands in for the dot as the trigger: the same tooltip, opened
   * from a few words that underline on hover and focus. The words name the
   * control, so `label` is not used.
   */
  children?: ReactNode;
  /**
   * The tooltip holds a link or button. It stays open while the pointer
   * crosses into it and while focus is inside it; Enter on the trigger moves
   * focus to its first control, and Esc returns focus to the trigger. The
   * `children` are a drawn control (a swatch) and are not underlined; they
   * are named by `triggerLabel`.
   */
  interactive?: boolean;
  /** A selector for the ancestor the tooltip stays inside; the page's `main` when omitted. */
  tipBounds?: string;
  /** Called as the tooltip opens, before it is placed: bring the thing it points at into view. */
  onReveal?: () => void;
  /** The accessible name of an interactive trigger whose children draw no words. */
  triggerLabel?: string;
  /** Called with the new state each time the tooltip opens or closes. */
  onOpenChange?: (open: boolean) => void;
  /**
   * Keeps the tooltip off other regions of the page. It is called each time the tooltip opens and returns rects and points in screen px.
   * The tooltip takes the first candidate spot clear of `avoid` and `others`, else the one covering the least, counting `avoid` far more heavily than `others`.
   * When no spot is clear and `outside` is given, the spot under `frame` is used if it fits.
   */
  clearOf?: () => TipClearance;
}

const OPEN_DELAY_MS = 300;
const CLOSE_DELAY_MS = 100;
// An interactive tooltip sits a gap away from its trigger; the pointer needs longer to cross it.
const INTERACTIVE_CLOSE_DELAY_MS = 250;
// A tooltip placed away from the trigger spot or the spot under the anchor takes the pointer longer to reach, so it closes after the longest delay.
const FAR_CLOSE_DELAY_MS = 700;
const VIEWPORT_INSET_PX = 16;
const GAP_PX = 6;
// A word joiner (U+2060) before the dot stops a line break between the last word and the mark.
const WORD_JOINER = String.raw`before:content-['\2060']`;

/**
 * Opens a tooltip from a small "i" mark, or from the `children` words, on hover, focus or touch, and closes it on pointer-leave, Esc or blur.
 * The mark aligns with vertical-align, so place it inline after the text it explains, not inside a flex or grid row.
 */
export function InfoDot({
  text,
  label = "More information",
  className = "",
  triggerClassName = "",
  decorative = false,
  children,
  interactive = false,
  tipBounds,
  onReveal,
  triggerLabel,
  onOpenChange,
  clearOf,
}: InfoDotProps) {
  const id = useId();
  const buttonRef = useRef<HTMLButtonElement>(null);
  const tooltipRef = useRef<HTMLDivElement>(null);
  const bridgeRef = useRef<HTMLDivElement>(null);
  const farSpot = useRef(false);
  const clearOfRef = useRef(clearOf);
  useEffect(() => {
    clearOfRef.current = clearOf;
  });
  const openTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const closeTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  // A tap focuses the button before its click fires. Recording the pointer type lets focus skip opening for touch, so the click handler does not close the tooltip the focus just opened.
  const lastPointerType = useRef<string | null>(null);
  const [open, setOpen] = useState(false);
  // Esc hands focus back to the trigger; that focus must not reopen the tooltip.
  const skipFocusOpen = useRef(false);
  // A tooltip opened by a tap stays until a tap elsewhere: the compatibility
  // mouse events a touch screen sends after the tap include a mouse-leave.
  const touchOpened = useRef(false);
  const onOpenChangeRef = useRef(onOpenChange);
  useEffect(() => {
    onOpenChangeRef.current = onOpenChange;
  });
  const reported = useRef(false);
  useEffect(() => {
    if (!open) {
      touchOpened.current = false;
    }
    if (open !== reported.current) {
      reported.current = open;
      onOpenChangeRef.current?.(open);
    }
  }, [open]);

  function clearTimers() {
    if (openTimer.current) {
      clearTimeout(openTimer.current);
      openTimer.current = null;
    }
    if (closeTimer.current) {
      clearTimeout(closeTimer.current);
      closeTimer.current = null;
    }
  }

  function show() {
    clearTimers();
    setOpen(true);
  }

  function hide() {
    touchOpened.current = false;
    clearTimers();
    setOpen(false);
  }

  function scheduleShow() {
    clearTimers();
    openTimer.current = setTimeout(show, OPEN_DELAY_MS);
  }

  function scheduleHide() {
    if (touchOpened.current) {
      return;
    }
    clearTimers();
    closeTimer.current = setTimeout(
      hide,
      farSpot.current
        ? FAR_CLOSE_DELAY_MS
        : interactive
          ? INTERACTIVE_CLOSE_DELAY_MS
          : CLOSE_DELAY_MS,
    );
  }

  useLayoutEffect(() => {
    const btn = buttonRef.current;
    const tip = tooltipRef.current;
    if (!open || !btn || !tip) {
      return () => {};
    }
    try {
      tip.showPopover?.();
    } catch {
      // A failed showPopover is ignored: the inline display style still decides whether the tooltip is visible.
    }
    onReveal?.();
    // Rects and the viewport are in screen px, but offset sizes and style values are CSS px scaled by the root zoom (see tokens.css).
    // Converting once makes the tooltip land on its trigger.
    const zoom = Number.parseFloat(getComputedStyle(document.documentElement).zoom) || 1;
    const btnRect = btn.getBoundingClientRect();
    const mainRect = btn.closest(tipBounds ?? "main")?.getBoundingClientRect();
    const limits = {
      minLeft: Math.max(VIEWPORT_INSET_PX * zoom, mainRect?.left ?? 0),
      maxRight: Math.min(
        window.innerWidth - VIEWPORT_INSET_PX * zoom,
        mainRect?.right ?? window.innerWidth,
      ),
      viewportHeight: window.innerHeight,
      inset: VIEWPORT_INSET_PX * zoom,
      gap: GAP_PX * zoom,
      zoom,
    };
    tip.style.maxHeight = "";
    tip.style.overflowY = "";
    tip.style.maxWidth = "";
    if (tipBounds && tip.offsetWidth * zoom > limits.maxRight - limits.minLeft) {
      tip.style.maxWidth = `${(limits.maxRight - limits.minLeft) / zoom}px`;
    }
    const natural = { width: tip.offsetWidth * zoom, height: tip.offsetHeight * zoom };
    const byTrigger = placeByTrigger(btnRect, natural, limits);
    if (byTrigger.maxHeight !== null) {
      tip.style.maxHeight = `${byTrigger.maxHeight / zoom}px`;
      tip.style.overflowY = "auto";
    }
    const tipSize = { width: natural.width, height: byTrigger.maxHeight ?? natural.height };
    let { x: left, y: top } = byTrigger;
    farSpot.current = false;
    const bridge = bridgeRef.current;
    if (bridge) {
      bridge.style.display = "none";
    }
    const clearance = clearOfRef.current?.();
    if (clearance) {
      const choice = chooseClearSpot({ x: left, y: top }, tipSize, clearance, limits);
      let best = choice.spot;
      const under = choice.overlap > 0 ? placeUnderFrame(tipSize, clearance, limits) : null;
      if (under) {
        // Below the fold: scroll just far enough to bring the tooltip in, if the frame loses at most a strip of its top.
        let moved = 0;
        let accepted = true;
        if (under.scrollBy > 0) {
          window.scrollBy({ top: under.scrollBy, behavior: "instant" });
          moved = btnRect.top - btn.getBoundingClientRect().top;
          accepted = scrollKeepsFrame(moved, under.scrollBy, clearance.frame.top, zoom);
          if (!accepted) {
            window.scrollBy({ top: -moved, behavior: "instant" });
            moved = 0;
          }
        }
        if (accepted) {
          best = { ...under.spot, y: under.spot.y - moved };
          if (bridge) {
            const box = bridgeBox(under.spot, tipSize.width, clearance.anchor);
            bridge.style.display = "block";
            bridge.style.left = `${box.left / zoom}px`;
            bridge.style.width = `${box.width / zoom}px`;
            bridge.style.height = `${box.height / zoom}px`;
          }
        }
      }
      if (best) {
        left = best.x;
        top = best.y;
        farSpot.current = best.far;
      }
    }
    tip.style.left = `${left / zoom}px`;
    tip.style.top = `${top / zoom}px`;
    return () => {
      try {
        tip.hidePopover?.();
      } catch {
        // Nothing to undo when the popover is not open.
      }
    };
  }, [open, tipBounds, onReveal]);

  useEffect(() => {
    if (!open) {
      return () => {};
    }
    function handleDocumentKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        setOpen(false);
      }
    }
    document.addEventListener("keydown", handleDocumentKeyDown);
    return () => document.removeEventListener("keydown", handleDocumentKeyDown);
  }, [open]);

  useEffect(() => {
    if (!open) {
      return () => {};
    }
    // A touch on the dot, or inside an interactive tooltip, is left to the click handler.
    // This listener closes the tooltip for any other touch.
    function handleDocumentPointerDown(event: PointerEvent) {
      if (event.pointerType !== "touch") {
        return;
      }
      if (
        event.target instanceof Node &&
        (buttonRef.current?.contains(event.target) ||
          (interactive && tooltipRef.current?.contains(event.target)))
      ) {
        return;
      }
      setOpen(false);
    }
    document.addEventListener("pointerdown", handleDocumentPointerDown);
    return () => document.removeEventListener("pointerdown", handleDocumentPointerDown);
  }, [open, interactive]);

  function handleKeyDown(event: React.KeyboardEvent) {
    if (event.key === "Escape" && open) {
      event.stopPropagation();
      hide();
      return;
    }
    if (!open && (event.key === "Enter" || event.key === " ")) {
      // The tooltip is closed while the trigger holds focus, for example after Esc, so Enter or Space reopens it.
      event.preventDefault();
      show();
      return;
    }
    if (interactive && open && event.key === "Enter") {
      const control = tooltipRef.current?.querySelector<HTMLElement>("a[href], button");
      if (control) {
        event.preventDefault();
        control.focus();
      }
    }
  }

  function handleTooltipKeyDown(event: React.KeyboardEvent) {
    if (event.key === "Escape") {
      event.stopPropagation();
      skipFocusOpen.current = true;
      hide();
      buttonRef.current?.focus();
    }
  }

  // Focus leaving the trigger for the tooltip, or back, keeps it open.
  function focusStaysInside(event: React.FocusEvent) {
    return (
      event.relatedTarget instanceof Node &&
      (buttonRef.current?.contains(event.relatedTarget) ||
        tooltipRef.current?.contains(event.relatedTarget))
    );
  }

  function handleTooltipBlur(event: React.FocusEvent) {
    if (!focusStaysInside(event)) {
      hide();
    }
  }

  function handlePointerDown(event: React.PointerEvent) {
    // A timer reset could run between a tap's pointerdown and its later focus and click events, so handleClick and handleBlur clear the pointer type instead.
    lastPointerType.current = event.pointerType;
  }

  function handleFocus() {
    if (skipFocusOpen.current) {
      skipFocusOpen.current = false;
      return;
    }
    if (lastPointerType.current === "touch") {
      return;
    }
    show();
  }

  function handleBlur(event: React.FocusEvent) {
    lastPointerType.current = null;
    if (interactive && focusStaysInside(event)) {
      return;
    }
    hide();
  }

  function handleClick(event: React.MouseEvent) {
    // Hover and focus already cover mouse and keyboard, so only a touch click toggles here.
    // A touch tap's click carries nativeEvent.pointerType "touch"; mouse clicks and jsdom's synthetic clicks do not.
    const pointerType = (event.nativeEvent as MouseEvent & { pointerType?: string }).pointerType;
    lastPointerType.current = null;
    if (pointerType !== "touch") {
      return;
    }
    if (open) {
      hide();
    } else {
      show();
      touchOpened.current = true;
    }
  }

  if (decorative) {
    return (
      <span
        aria-hidden="true"
        className={`relative ml-1 inline-flex size-[14px] shrink-0 items-center justify-center rounded-full border-(length:--hairline) border-ink-3 align-middle font-serif text-12 italic text-ink-2 ${className}`}
      >
        i
      </span>
    );
  }

  return (
    <span
      className={`relative ${children == null ? `ml-1 ${WORD_JOINER}` : ""} ${className}`}
      data-open={open}
      onMouseEnter={scheduleShow}
      onMouseLeave={scheduleHide}
    >
      <button
        ref={buttonRef}
        type="button"
        aria-describedby={id}
        aria-label={children == null ? label : triggerLabel}
        data-info-text={children == null ? undefined : ""}
        onPointerDown={handlePointerDown}
        onFocus={handleFocus}
        onBlur={handleBlur}
        onKeyDown={handleKeyDown}
        onClick={handleClick}
        className={
          interactive
            ? `relative inline-flex [@media(pointer:coarse)]:before:absolute [@media(pointer:coarse)]:before:inset-[-16px] [@media(pointer:coarse)]:before:content-[''] ${triggerClassName}`
            : children == null
              ? "relative inline-flex size-[14px] items-center justify-center rounded-full border-(length:--hairline) align-middle border-ink-3 font-serif text-12 italic text-ink-2 before:content-none [@media(pointer:coarse)]:before:absolute [@media(pointer:coarse)]:before:inset-[-16px] [@media(pointer:coarse)]:before:content-['']"
              : `relative [word-spacing:inherit] underline decoration-transparent decoration-1 underline-offset-2 transition-colors duration-(--motion-fast) hover:decoration-current focus-visible:decoration-current [@media(pointer:coarse)]:before:absolute [@media(pointer:coarse)]:before:inset-x-[-8px] [@media(pointer:coarse)]:before:-inset-y-3.5 [@media(pointer:coarse)]:before:content-[''] ${triggerClassName}`
        }
      >
        {children ?? "i"}
      </button>
      {/* oxlint-disable-next-line jsx-a11y/no-noninteractive-element-interactions -- Esc and focus-out are heard from the link inside the tooltip */}
      <div
        ref={tooltipRef}
        id={id}
        role="tooltip"
        popover="manual"
        style={{ display: open ? "block" : "none", position: "fixed" }}
        onKeyDown={interactive ? handleTooltipKeyDown : undefined}
        onBlur={interactive ? handleTooltipBlur : undefined}
        className="inset-auto m-0 w-max max-w-[min(320px,calc(100vw-32px))] overflow-visible whitespace-normal border-(length:--hairline) border-rule-strong bg-sheet px-3 py-2 text-left text-13 not-italic text-ink-2 shadow-pop [word-spacing:normal]"
      >
        {text}
        <div
          ref={bridgeRef}
          aria-hidden="true"
          data-tip-bridge=""
          style={{ display: "none", position: "absolute", bottom: "calc(100% + 1px)" }}
        />
      </div>
    </span>
  );
}
