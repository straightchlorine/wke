import type { ReactNode } from "react";

export interface ErrorPanelProps {
  /** The error title, for example "Rate limited". Leave it out when the page's own h1 already says it. */
  title?: string;
  /** The error's detail text from the API response. */
  detail?: string;
  /** The server's request id, shown so a report can be matched to logs. */
  requestId?: string;
  /** A Retry button, or a list of suggested links. */
  retry?: ReactNode;
  /** A countdown such as "Retry in 38 s", for a response that carries Retry-After. */
  countdown?: ReactNode;
  /**
   * "alert" (default) is for an actual failure such as rate limiting or an upstream outage. It uses the stamp colours and gives the text role="alert".
   * "muted" is for an expected outcome that is not an error, such as a mistyped or not-yet-built title. It uses neutral colours and sets no role.
   */
  tone?: "alert" | "muted";
  className?: string;
}
/** A panel that reports a failed or empty result, with optional request id, countdown and retry control. */
export function ErrorPanel({
  title,
  detail,
  requestId,
  retry,
  countdown,
  tone = "alert",
  className = "",
}: ErrorPanelProps) {
  const isAlert = tone === "alert";
  return (
    <div
      className={`border-t-[3px] px-4 py-3 ${isAlert ? "border-stamp bg-stamp-wash" : "border-rule-strong bg-wash"} ${className}`}
    >
      <div role={isAlert ? "alert" : undefined}>
        {title != null ? (
          <p className={`text-14 font-medium ${isAlert ? "text-stamp" : "text-ink"}`}>{title}</p>
        ) : null}
        {detail != null ? (
          <p className={`${title != null ? "mt-1 text-13" : "text-14"} text-ink-2`}>{detail}</p>
        ) : null}
        {requestId ? (
          <p className="mt-1 text-12 text-ink-2">
            Request ID: <code>{requestId}</code>
          </p>
        ) : null}
      </div>
      {countdown != null ? <p className="mt-1 text-13 text-ink-2">{countdown}</p> : null}
      {retry != null ? <div className="mt-2">{retry}</div> : null}
    </div>
  );
}
