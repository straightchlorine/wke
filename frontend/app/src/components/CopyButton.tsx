import { useEffect, useRef, useState, type CSSProperties, type ReactNode } from "react";
import { Button, type ButtonVariant } from "./Button";

const COPIED_MS = 1600;

async function writeClipboardText(text: string): Promise<boolean> {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    return false;
  }
}

// Selects the text in a hidden textarea, so the "press Ctrl+C" message is true when the clipboard write fails.
// One textarea is reused by every CopyButton on the page.
function selectInHiddenTextarea(text: string) {
  const existing = document.getElementById("copy-fallback");
  let el = existing instanceof HTMLTextAreaElement ? existing : null;
  if (!el) {
    el = document.createElement("textarea");
    el.id = "copy-fallback";
    el.setAttribute("aria-hidden", "true");
    el.tabIndex = -1;
    el.readOnly = true;
    el.style.position = "fixed";
    el.style.top = "0";
    el.style.left = "0";
    el.style.width = "1px";
    el.style.height = "1px";
    el.style.opacity = "0";
    document.body.appendChild(el);
  }
  el.value = text;
  el.focus();
  el.select();
}

export interface CopyButtonProps {
  /** Produces the exact text to copy, possibly by fetching it. Null means producing the text failed, so nothing is written or selected. */
  getText: () => string | Promise<string | null> | null;
  /** Reported through `onCopy` after a successful write. */
  message: string;
  /** Reported through `onCopy` when `getText` returns null. */
  fetchFailedMessage?: string;
  /** Reported through `onCopy` when the clipboard write fails. */
  writeFailedMessage?: string;
  /** Receives the message to show, on every outcome. */
  onCopy?: (message: string) => void;
  variant?: ButtonVariant;
  ariaLabel?: string;
  /** The native title tooltip, for example an exact count a compact label leaves out. */
  title?: string;
  /** The `data-copy` attribute value, unique on the page. */
  id?: string;
  /** How long the "copied" state lasts, in milliseconds. */
  durationMs?: number;
  className?: string;
  style?: CSSProperties;
  disabled?: boolean;
  /** Renders the button's content from whether it just copied. */
  children: (copied: boolean) => ReactNode;
}

/**
 * Copies the text from `getText()` and holds a "copied" state for `durationMs`.
 * If the clipboard write fails, it selects the text in a hidden textarea so the "press Ctrl+C" message is true.
 */
export function CopyButton({
  getText,
  message,
  fetchFailedMessage = "Copy failed",
  writeFailedMessage = "Copy failed. The text is selected: press Ctrl+C to copy it.",
  onCopy,
  variant = "small",
  ariaLabel,
  title,
  id,
  durationMs = COPIED_MS,
  className = "",
  style,
  disabled = false,
  children,
}: CopyButtonProps) {
  const [copied, setCopied] = useState(false);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    return () => {
      if (timer.current) {
        clearTimeout(timer.current);
      }
    };
  }, []);

  async function handleClick() {
    const text = await getText();
    if (text == null) {
      onCopy?.(fetchFailedMessage);
      return;
    }
    const ok = await writeClipboardText(text);
    if (ok) {
      onCopy?.(message);
      setCopied(true);
      if (timer.current) {
        clearTimeout(timer.current);
      }
      timer.current = setTimeout(() => setCopied(false), durationMs);
      return;
    }
    selectInHiddenTextarea(text);
    onCopy?.(writeFailedMessage);
  }

  return (
    <Button
      variant={variant}
      waiting={disabled}
      data-copy={id}
      aria-label={ariaLabel}
      title={title}
      onClick={() => void handleClick()}
      className={className}
      style={style}
    >
      {children(copied)}
    </Button>
  );
}
