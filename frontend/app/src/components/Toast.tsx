import { useEffect, useRef } from "react";
import { announceLive } from "../lib/liveRegion";

export interface ToastProps {
  /** The toast text, or null when nothing should show. */
  message: string | null;
  /** Called once the toast's timer elapses. */
  onDismiss: () => void;
  /** Auto-dismiss delay in ms; a new message restarts this timer. */
  durationMs?: number;
  /** Change this on every event to restart the timer even when `message` repeats verbatim. */
  nonce?: number;
  /**
   * Lifts the toast above the fixed bottom HUD bar on narrow screens, using `--hud-h`, which already includes the safe-area inset.
   * It has no effect on wider screens.
   */
  aboveHud?: boolean;
  className?: string;
}

/**
 * Bottom-centre toast that shows one message at a time. It is hidden from assistive tech,
 * because the announcement goes through the shared live region in `__root.tsx`.
 */
export function Toast({
  message,
  onDismiss,
  durationMs = 1600,
  nonce,
  aboveHud = false,
  className = "",
}: ToastProps) {
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  // The refs hold the latest onDismiss and durationMs, so changing either while
  // a toast is showing does not restart its timer.
  const onDismissRef = useRef(onDismiss);
  const durationMsRef = useRef(durationMs);

  useEffect(() => {
    onDismissRef.current = onDismiss;
    durationMsRef.current = durationMs;
  });

  useEffect(() => {
    if (timer.current) {
      clearTimeout(timer.current);
      timer.current = null;
    }
    if (message == null) {
      return () => {};
    }
    timer.current = setTimeout(() => onDismissRef.current(), durationMsRef.current);
    return () => {
      if (timer.current) {
        clearTimeout(timer.current);
        timer.current = null;
      }
    };
    // oxlint-disable-next-line react/exhaustive-effect-dependencies -- nonce is not read here; it only restarts the timer when the same message is shown again.
  }, [message, nonce]);

  useEffect(() => {
    if (message != null) {
      announceLive(message);
    }
  }, [message]);

  const bottomClass = aboveHud
    ? "bottom-6 max-[599px]:bottom-[calc(var(--hud-h)+1.5rem)]"
    : "bottom-6";
  return (
    <div
      data-testid="toast"
      aria-hidden="true"
      className={`fixed ${bottomClass} left-1/2 z-30 -translate-x-1/2 border-(length:--hairline) border-rule-strong bg-paper px-3 py-2 text-13 text-ink shadow-pop ${message == null ? "invisible opacity-0" : "opacity-100"} ${className}`}
    >
      {message}
    </div>
  );
}
