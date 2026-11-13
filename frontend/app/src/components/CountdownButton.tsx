import { useEffect, useState } from "react";
import { Button } from "./Button";

export interface CountdownButtonProps {
  /** Seconds to count down from, for example the API's Retry-After. */
  seconds: number;
  onClick: () => void;
}

/** Counts down from `seconds` as "Retry in X s", then accepts clicks. It never retries by itself. */
export function CountdownButton({ seconds, onClick }: CountdownButtonProps) {
  const [remaining, setRemaining] = useState(seconds);
  const [startedFrom, setStartedFrom] = useState(seconds);
  // A new `seconds` restarts the count; adjusting state while rendering avoids an extra render pass.
  if (startedFrom !== seconds) {
    setStartedFrom(seconds);
    setRemaining(seconds);
  }
  useEffect(() => {
    if (remaining <= 0) {
      return () => {};
    }
    const t = setTimeout(() => setRemaining((n) => n - 1), 1000);
    return () => clearTimeout(t);
  }, [remaining]);
  return (
    <Button variant="small" waiting={remaining > 0} onClick={onClick}>
      {remaining > 0 ? `Retry in ${remaining} s` : "Retry"}
    </Button>
  );
}
