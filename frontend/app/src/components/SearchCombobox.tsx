import { useEffect, useId, useState, type KeyboardEvent, type ReactNode, type Ref } from "react";
import { createPortal } from "react-dom";
import { announceLive } from "../lib/liveRegion";
import { useMediaQuery } from "../lib/hooks/useMediaQuery";
import { useTopicSuggestions } from "../lib/hooks/useTopicSuggestions";
import { buildVerbHint, notBuiltHint } from "../lib/searchButton";
import type { DossierState } from "../lib/dossierState";
import { DossierStateChip } from "./Chip";

export interface SearchComboboxProps {
  value: string;
  onChange: (value: string) => void;
  /** Called with the title of the option that was picked. */
  onPick: (title: string) => void;
  ariaLabel: string;
  placeholder?: string;
  ref?: Ref<HTMLInputElement>;
  id?: string;
  disabled?: boolean;
  /** Called on Escape when no list is open (e.g. to clear a filter). */
  onEscape?: () => void;
  /** Sits inside the field's box on the right edge, e.g. a clear button. */
  trailing?: ReactNode;
  /**
   * Reports how many titles are listed. With it the caller owns the
   * "N suggestions" announcement, so it can join it to its own message
   * instead of overwriting it.
   */
  onOptionCount?: (count: number) => void;
  /** Renders the list here, in flow, instead of under the input. */
  listContainer?: HTMLElement | null;
  /**
   * Reports the dossier state of the highlighted row, or null with none
   * highlighted, so the form's button can say Open or Build.
   */
  onActiveStateChange?: (state: DossierState | null) => void;
  /** Use the shared control height instead of the default field height, for a row of controls. */
  compact?: boolean;
}

/**
 * A text input with a listbox of matching article titles under it (the
 * ARIA combobox pattern). Arrow keys move through the titles, Enter on a
 * highlighted title picks it, Escape closes the list and keeps the text.
 * With no title highlighted, Enter falls through to the surrounding form.
 */
export function SearchCombobox({
  value,
  onChange,
  onPick,
  ariaLabel,
  placeholder,
  ref,
  id,
  disabled = false,
  onEscape,
  trailing,
  onOptionCount,
  listContainer,
  onActiveStateChange,
  compact = false,
}: SearchComboboxProps) {
  // A device that cannot hover counts as touch, so its hint for a title with no dossier says tap instead of Enter.
  // The row text and the live region both use that wording.
  const inputKind = useMediaQuery("(hover: none)") ? "touch" : "keyboard";
  const notBuilt = notBuiltHint(inputKind);
  const buildVerb = buildVerbHint(inputKind);
  const listId = useId();
  const [dismissed, setDismissed] = useState(false);
  // The highlighted row belongs to one answer; a new answer starts unhighlighted.
  const [highlight, setHighlight] = useState<{ key: string; index: number }>({
    key: "",
    index: -1,
  });

  const { term, suggestions } = useTopicSuggestions(value);
  const active = highlight.key === term ? highlight.index : -1;
  const setActive = (index: number) => setHighlight({ key: term, index });
  const options = dismissed ? [] : suggestions;
  const open = options.length > 0;
  const optionId = (index: number) => `${listId}-${index}`;

  useEffect(() => {
    if (onOptionCount) {
      onOptionCount(open ? options.length : 0);
    } else if (open) {
      announceLive(`${options.length} suggestion${options.length === 1 ? "" : "s"}`);
    }
    // Only the count is reported, so the effect depends on it and not on the list.
    // oxlint-disable-next-line react/exhaustive-effect-dependencies
  }, [open, options.length, onOptionCount]);

  // A title with no dossier yet builds one on Enter or click; say so when
  // the reader lands on it, since the row's own text is not re-read by
  // every screen reader on an active-descendant change.
  const activeOption = open && active >= 0 ? options[active] : undefined;
  const activeIsUnbuilt = activeOption?.dossier_state === "none";
  const activeTitle = activeOption?.title;
  const activeState = activeOption?.dossier_state ?? null;
  useEffect(() => {
    onActiveStateChange?.(activeState);
  }, [activeState, onActiveStateChange]);
  useEffect(() => {
    if (activeIsUnbuilt && activeTitle) {
      announceLive(`${activeTitle}, ${notBuilt}`);
    }
  }, [activeIsUnbuilt, activeTitle, notBuilt]);

  function handleKeyDown(event: KeyboardEvent<HTMLInputElement>) {
    if (event.nativeEvent.isComposing) return;
    if (event.key === "Escape") {
      if (open) {
        event.preventDefault();
        event.stopPropagation();
        setDismissed(true);
        setActive(-1);
      } else {
        onEscape?.();
      }
      return;
    }
    if (!open) {
      if (event.key === "ArrowDown" && options.length === 0 && dismissed) {
        setDismissed(false);
      }
      return;
    }
    if (event.key === "ArrowDown") {
      event.preventDefault();
      setActive((active + 1) % options.length);
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      setActive(active <= 0 ? options.length - 1 : active - 1);
    } else if (event.key === "Enter" && active >= 0) {
      const picked = options[active];
      if (picked) {
        event.preventDefault();
        setDismissed(true);
        onPick(picked.title);
      }
    }
  }

  const inFlow = listContainer != null;
  /* oxlint-disable jsx-a11y/no-noninteractive-element-to-interactive-role, jsx-a11y/prefer-tag-over-role, jsx-a11y/click-events-have-key-events -- the ARIA combobox pattern: the input keeps focus and drives the listbox through aria-activedescendant, so the options take no key events of their own; a native <select> cannot sit under a text input. */
  const list = (
    <ul
      id={listId}
      role="listbox"
      aria-label="Suggested titles"
      hidden={!open}
      className={
        inFlow
          ? "mt-4 max-w-(--container-prose) border-(length:--hairline) border-ink bg-sheet"
          : "absolute inset-x-0 top-full z-30 border-(length:--hairline) border-t-0 border-ink bg-sheet"
      }
    >
      {options.map((option, index) => (
        <li
          key={option.page_id}
          id={optionId(index)}
          role="option"
          aria-selected={index === active}
          // Keeps the input focused, so a click picks before blur closes the list.
          onMouseDown={(event) => event.preventDefault()}
          onClick={() => {
            setDismissed(true);
            onPick(option.title);
          }}
          onMouseMove={() => setActive(index)}
          className={`flex min-h-11 cursor-pointer items-center justify-between gap-x-3 px-3 py-1.5 text-14 ${
            index === active ? "bg-wash text-accent-ink" : "text-ink"
          }`}
        >
          <span className="min-w-0">
            <span className="block truncate">{option.title}</span>
            {option.dossier_state === "none" || option.description ? (
              <span className="block truncate text-12 text-ink-2">
                {option.dossier_state === "none" ? buildVerb : null}
                {option.dossier_state === "none" && option.description ? " - " : null}
                {option.description}
              </span>
            ) : null}
          </span>
          <span className="shrink-0">
            <DossierStateChip
              state={option.dossier_state}
              showNone
              className="w-19 justify-center"
            />
          </span>
        </li>
      ))}
    </ul>
  );
  /* oxlint-enable jsx-a11y/no-noninteractive-element-to-interactive-role, jsx-a11y/prefer-tag-over-role, jsx-a11y/click-events-have-key-events */

  return (
    <div className="relative min-w-0 flex-1">
      <input
        ref={ref}
        id={id}
        disabled={disabled}
        type="text"
        role="combobox"
        aria-expanded={open}
        aria-controls={listId}
        aria-autocomplete="list"
        aria-activedescendant={open && active >= 0 ? optionId(active) : undefined}
        autoComplete="off"
        value={value}
        onChange={(event) => {
          setDismissed(false);
          onChange(event.target.value);
        }}
        onKeyDown={handleKeyDown}
        onBlur={() => setDismissed(true)}
        onFocus={() => setDismissed(false)}
        placeholder={placeholder}
        aria-label={ariaLabel}
        className={`${compact ? "h-(--control-h)" : "h-11"} w-full border-(length:--hairline) border-ink bg-sheet px-3 text-14 text-ink placeholder:text-ink-3 focus-visible:outline focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-accent`}
      />
      {trailing}
      {inFlow ? createPortal(list, listContainer) : list}
    </div>
  );
}
