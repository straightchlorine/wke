import { useEffect, useRef } from "react";
import { isTypingTarget } from "../lib/typingTarget";

export interface SegmentedOption<T extends string> {
  value: T;
  label: string;
}

export interface SegmentedProps<T extends string> {
  /** The accessible name of the radio group, for example "Token budget". */
  ariaLabel: string;
  /** The `name` shared by the underlying radio inputs. */
  name: string;
  options: SegmentedOption<T>[];
  value: T;
  onChange: (value: T) => void;
  /** When true, the keys 1, 2 and 3 pick the first three options. They are ignored while the user types in a field or holds Ctrl, Meta or Alt. */
  numberShortcuts?: boolean;
  /** When true, the options grow to fill the control's width instead of staying at their content width. Use with a `w-full` className so they span edge to edge. */
  stretch?: boolean;
  className?: string;
}

/** A row of mutually exclusive options, built on native radio inputs. */
export function Segmented<T extends string>({
  ariaLabel,
  name,
  options,
  value,
  onChange,
  numberShortcuts = false,
  stretch = false,
  className = "",
}: SegmentedProps<T>) {
  const groupRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!numberShortcuts) {
      return () => {};
    }
    function handleKeyDown(event: KeyboardEvent) {
      if (event.ctrlKey || event.metaKey || event.altKey) {
        return;
      }
      if (isTypingTarget(event.target)) {
        return;
      }
      // The dossier page mounts two budget groups, one hidden at any width, so only the visible one answers the keys.
      if (groupRef.current?.checkVisibility?.() === false) {
        return;
      }
      const index = ["1", "2", "3"].indexOf(event.key);
      if (index === -1) {
        return;
      }
      const option = options[index];
      if (option) {
        onChange(option.value);
        // Focus moves to the picked radio, so the next key or arrow starts from there.
        const radios = groupRef.current?.querySelectorAll<HTMLInputElement>("input[type=radio]");
        radios?.[index]?.focus({ preventScroll: true });
      }
    }
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [numberShortcuts, options, onChange]);

  return (
    <div
      ref={groupRef}
      role="radiogroup"
      aria-label={ariaLabel}
      className={`inline-flex border-(length:--hairline) border-ink ${className}`}
    >
      {options.map((option) => (
        <label
          key={option.value}
          className={`relative flex h-[calc(var(--control-h)-2*var(--hairline))] cursor-pointer items-center justify-center border-r-(length:--hairline) border-ink text-13 font-medium text-ink-2 last:border-r-0 has-checked:bg-wash has-checked:text-accent-ink has-checked:shadow-[inset_0_-2px_0_var(--color-accent)] has-[:focus-visible]:outline has-[:focus-visible]:outline-2 has-[:focus-visible]:-outline-offset-2 has-[:focus-visible]:outline-accent before:absolute before:inset-x-0 before:-inset-y-px before:content-[''] ${stretch ? "min-w-0 flex-auto px-2 py-1 text-center leading-tight min-[600px]:px-3" : "whitespace-nowrap px-3"}`}
        >
          <input
            type="radio"
            name={name}
            value={option.value}
            checked={value === option.value}
            onChange={() => onChange(option.value)}
            className="sr-only"
          />
          {option.label}
        </label>
      ))}
    </div>
  );
}
