import { useCallback, useEffect, useRef, useState } from "react";
import { useReducedMotion } from "./useReducedMotion";

/** How long a node stays marked as just edited. */
const PING_WINDOW_MS = 60_000;
/** The ring animation's length; the same as the `--motion-ping` token. */
const RING_ANIMATION_MS = 900;
/** How long after the first ring the second one starts. */
export const SECOND_RING_DELAY_MS = 450;
/** How long the animated rings stay: the animation, the second ring's delay, and a little slack. */
const RING_LIFETIME_MS = RING_ANIMATION_MS + SECOND_RING_DELAY_MS + 200;

interface Ring {
  id: string;
  pageId: number;
}

/**
 * Tracks which nodes were just edited. A ping marks the node for `PING_WINDOW_MS` and draws a ring
 * around it, unless the node is already marked. A repeat ping only counts and restarts the window.
 *
 * `knownIds` are the nodes that exist; a ping for any other id is ignored. Pending timers are
 * cleared when the component unmounts.
 */
export function usePings(knownIds: ReadonlySet<number>) {
  const reducedMotion = useReducedMotion();
  const [counts, setCounts] = useState<Map<number, number>>(new Map());
  const [rings, setRings] = useState<Ring[]>([]);
  // A node is marked while its expiry timer is pending.
  const expiry = useRef(new Map<number, ReturnType<typeof setTimeout>>());
  const ringTimers = useRef(new Set<ReturnType<typeof setTimeout>>());
  const ringSerial = useRef(0);

  useEffect(() => {
    const pendingExpiry = expiry.current;
    const pendingRings = ringTimers.current;
    return () => {
      pendingExpiry.forEach(clearTimeout);
      pendingExpiry.clear();
      pendingRings.forEach(clearTimeout);
      pendingRings.clear();
    };
  }, []);

  const ping = useCallback(
    (pageId: number, ring: boolean = true) => {
      if (!knownIds.has(pageId)) {
        return;
      }
      const isRepeat = expiry.current.has(pageId);
      clearTimeout(expiry.current.get(pageId));
      setCounts((prev) => new Map(prev).set(pageId, (prev.get(pageId) ?? 0) + 1));
      if (ring && !isRepeat) {
        ringSerial.current += 1;
        const ringId = `${pageId}-${ringSerial.current}`;
        setRings((prev) => [...prev, { id: ringId, pageId }]);
        // Under reduced motion the ring is static, so it stays for the whole ping window.
        const timer = setTimeout(
          () => {
            ringTimers.current.delete(timer);
            setRings((prev) => prev.filter((r) => r.id !== ringId));
          },
          reducedMotion ? PING_WINDOW_MS : RING_LIFETIME_MS,
        );
        ringTimers.current.add(timer);
      }
      expiry.current.set(
        pageId,
        setTimeout(() => {
          expiry.current.delete(pageId);
          setCounts((prev) => {
            const next = new Map(prev);
            next.delete(pageId);
            return next;
          });
        }, PING_WINDOW_MS),
      );
    },
    [knownIds, reducedMotion],
  );

  return {
    /** The marked nodes, each with how many pings arrived in its current window. */
    counts,
    /** Returns the ids of the rings drawn around a node. */
    ringIdsFor: (pageId: number) => rings.filter((r) => r.pageId === pageId).map((r) => r.id),
    ping,
  };
}
