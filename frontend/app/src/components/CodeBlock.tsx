import { useEffect, useRef, type ReactNode } from "react";
import { CopyButton } from "./CopyButton";

const MODEL_BLOCK_START = "**Machine summary (model output)**";
const MODEL_BLOCK_END = "Model: ";

function modelSpan(key: string, lines: string[]): ReactNode {
  return (
    <span key={key} className="bg-model shadow-[0_0_0_2px_var(--color-model)]">
      {lines.join("\n")}
    </span>
  );
}

/**
 * Dims "#" comment lines when `comments` is true and tints the model-summary block.
 * The block runs from the "**Machine summary (model output)**" line through the next "Model: " line, or to the end of the text when none follows.
 */
function renderCode(code: string, comments: boolean): ReactNode[] {
  const lines = code.split("\n");
  const nodes: ReactNode[] = [];
  let modelLines: string[] | null = null;
  lines.forEach((line, index) => {
    const isLast = index === lines.length - 1;
    const trimmed = line.trimStart();
    if (modelLines) {
      modelLines.push(line);
      if (trimmed.startsWith(MODEL_BLOCK_END)) {
        nodes.push(modelSpan(`m${index}`, modelLines));
        modelLines = null;
      }
    } else if (trimmed.startsWith(MODEL_BLOCK_START)) {
      modelLines = [line];
    } else if (comments && trimmed.startsWith("#")) {
      nodes.push(
        <span key={`c${index}`} className="text-ink-3">
          {line}
        </span>,
      );
    } else {
      nodes.push(line);
    }
    if (!isLast && modelLines === null) {
      nodes.push("\n");
    }
  });
  if (modelLines) {
    nodes.push(modelSpan("m-end", modelLines));
  }
  return nodes;
}

export interface CodeBlockCopyProps {
  /** The `data-copy` id, unique on the page. */
  id: string;
  /** The exact text written to the clipboard; defaults to `code`. */
  text?: string;
  /** Toast message after a successful copy. */
  message?: string;
  /** Button text while idle. */
  label?: string;
  /** Accessible name; defaults to `label`. Include the section name when the page has several Copy buttons. */
  ariaLabel?: string;
}

export interface CodeBlockProps {
  /** Header label, e.g. "Request" or "Response excerpt, application/json". */
  heading: ReactNode;
  code: string;
  /** When set, a Copy button renders in the header. */
  copy?: CodeBlockCopyProps;
  /** Receives the toast message after every copy attempt, including a failed one. */
  onCopy?: (message: string) => void;
  /** Dim "#" lines as comments; false when "#" starts a Markdown heading. */
  comments?: boolean;
  className?: string;
}

/** A code frame with a heading row and an optional Copy button. Long lines scroll sideways inside the frame instead of widening the page. */
export function CodeBlock({
  heading,
  code,
  copy,
  onCopy,
  comments = true,
  className = "",
}: CodeBlockProps) {
  const wrapRef = useRef<HTMLDivElement>(null);
  const preRef = useRef<HTMLPreElement>(null);
  useEffect(() => {
    const wrap = wrapRef.current;
    const pre = preRef.current;
    if (!wrap || !pre) {
      return () => {};
    }
    function update() {
      if (!wrap || !pre) {
        return;
      }
      const more = pre.scrollWidth - pre.clientWidth - pre.scrollLeft > 1;
      wrap.dataset["codeMore"] = String(more);
      wrap.style.setProperty("--code-scrollbar", `${pre.offsetHeight - pre.clientHeight}px`);
    }
    update();
    pre.addEventListener("scroll", update, { passive: true });
    const resize = typeof ResizeObserver === "undefined" ? null : new ResizeObserver(update);
    resize?.observe(pre);
    // New text can change the scroll width without resizing the pane's box, which the resize observer would miss.
    const mutate = new MutationObserver(update);
    mutate.observe(pre, { childList: true, subtree: true, characterData: true });
    return () => {
      pre.removeEventListener("scroll", update);
      resize?.disconnect();
      mutate.disconnect();
    };
  }, []);
  return (
    <div className={`border-(length:--hairline) border-rule-strong bg-sheet min-w-0 ${className}`}>
      <div className="flex min-h-8 items-center justify-between gap-x-2 border-b-(length:--hairline) border-rule pl-3 pr-1 text-12 text-ink-3">
        <span>{heading}</span>
        {copy ? (
          <CopyButton
            variant="quiet"
            id={copy.id}
            getText={() => copy.text ?? code}
            message={copy.message ?? "Copied"}
            ariaLabel={copy.ariaLabel ?? copy.label ?? "Copy"}
            onCopy={onCopy}
          >
            {(copied) => (copied ? "Copied" : (copy.label ?? "Copy"))}
          </CopyButton>
        ) : null}
      </div>
      {/* The fade marks a pane with more code to the right; it is hidden once the pane is scrolled to its end, where a phone shows no scrollbar to say so. */}
      <div
        ref={wrapRef}
        data-code-more="false"
        className="relative after:pointer-events-none after:absolute after:top-0 after:right-0 after:bottom-[var(--code-scrollbar,0px)] after:w-6 after:bg-linear-to-r after:from-transparent after:via-sunken after:to-sunken after:opacity-0 after:transition-opacity after:duration-(--motion-fast) motion-reduce:after:transition-none data-[code-more=true]:after:opacity-100"
      >
        <pre
          ref={preRef}
          // oxlint-disable-next-line jsx-a11y/no-noninteractive-tabindex -- a scrolling <pre> needs its own tab stop so keyboard users can scroll it; it has no landmark role, which would repeat region names across sections.
          tabIndex={0}
          className="overflow-x-auto py-3 pr-6 pl-3 font-mono text-12 leading-[18px] [tab-size:2] text-ink"
        >
          {renderCode(code, comments)}
        </pre>
      </div>
    </div>
  );
}
