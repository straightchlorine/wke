import type { RecordRowProps } from "./Record";
import { CopyButton } from "./CopyButton";

export interface EndpointProps {
  /** What the endpoint is called, for example "JSON". */
  label: string;
  /** The line shown for the endpoint, for example "GET https://example.org/llms.txt". */
  line: string;
  /** The text the button copies. Null disables the button, for an endpoint whose address is not known yet. */
  copyText: string | null;
  /** The button text while idle. */
  copyLabel?: string;
  /** Reported through `onCopy` after a successful copy. */
  message: string;
  /** The button's accessible name, for a page with several buttons of the same text. */
  ariaLabel?: string;
  /** The `data-copy` id of the button, unique on the page. */
  id?: string;
  onCopy?: (message: string) => void;
}

function EndpointCopyButton({
  copyText,
  copyLabel = "Copy URL",
  message,
  ariaLabel,
  id,
  onCopy,
  variant,
  className,
}: Omit<EndpointProps, "label" | "line"> & { variant?: "secondary"; className: string }) {
  return (
    <CopyButton
      id={id}
      variant={variant}
      ariaLabel={ariaLabel}
      getText={() => copyText}
      message={message}
      disabled={copyText == null}
      onCopy={onCopy}
      className={className}
    >
      {(copied) => (copied ? "Copied" : copyLabel)}
    </CopyButton>
  );
}

/** Returns the row of a `Record` that shows an endpoint's line with a copy button after its label. */
export function endpointRecordRow({ label, line, ...copy }: EndpointProps): RecordRowProps {
  return {
    label,
    value: <EndpointCopyButton {...copy} className="w-22" />,
    sub: <span className="font-mono text-12 break-all">{line}</span>,
    subBlock: true,
    size: "normal",
  };
}

/** A box that names an endpoint, shows its line in one clipped row, says what it returns and offers a copy button. */
export function EndpointRow({
  label,
  line,
  sentence,
  ...copy
}: EndpointProps & {
  /** What the endpoint returns, in one short sentence. */
  sentence: string;
}) {
  return (
    <div className="flex flex-col bg-paper p-3">
      <h3 className="font-serif text-14 text-ink">{label}</h3>
      <code className="mt-1 block truncate text-12 whitespace-nowrap text-ink-2" title={line}>
        {line}
      </code>
      <p className="mt-2 flex-1 text-12 text-ink-3">{sentence}</p>
      <EndpointCopyButton {...copy} variant="secondary" className="mt-2 self-start" />
    </div>
  );
}
