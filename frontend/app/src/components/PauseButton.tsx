export interface PauseProps {
  paused: boolean;
  onToggle: () => void;
  /** True while the edit stream cannot be paused or resumed, for example when it is down or rate limited. */
  disabled?: boolean;
  /** The native title tooltip, for example "12 edits arrived while paused". */
  title?: string;
  className?: string;
}

/** A button that pauses and resumes the live edit stream. Its width is fixed, so it does not move when the label changes between "Pause" and "Resume". */
export function Pause({ paused, onToggle, disabled = false, title, className = "" }: PauseProps) {
  return (
    <span className={`inline-flex shrink-0 items-center ${className}`}>
      {/* No aria-pressed: the label itself switches between "Pause" and "Resume", so the button reads as a command, not a toggle. */}
      <button
        type="button"
        aria-disabled={disabled || undefined}
        title={title}
        onClick={() => {
          if (!disabled) {
            onToggle();
          }
        }}
        className={`h-(--control-h) w-20 border-(length:--hairline) border-rule-strong bg-sheet px-2 text-13 transition-colors duration-(--motion-fast) ${disabled ? "cursor-not-allowed text-ink-3" : "text-ink hover:bg-wash"}`}
      >
        {paused ? "Resume" : "Pause"}
      </button>
    </span>
  );
}
