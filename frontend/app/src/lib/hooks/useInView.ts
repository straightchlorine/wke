import { useCallback, useState } from "react";

/**
 * Returns a callback ref and whether the element has ever come within `rootMargin` of the viewport.
 * The flag never goes back to false, so a query enabled by it stays enabled. It is true at once
 * where IntersectionObserver is missing.
 */
export function useInView(
  rootMargin = "200px",
): [(node: Element | null) => (() => void) | undefined, boolean] {
  const [inView, setInView] = useState(false);
  const ref = useCallback(
    (node: Element | null) => {
      if (node == null) {
        return undefined;
      }
      if (typeof IntersectionObserver === "undefined") {
        setInView(true);
        return undefined;
      }
      const observer = new IntersectionObserver(
        (entries) => {
          if (entries.some((entry) => entry.isIntersecting)) {
            setInView(true);
            observer.disconnect();
          }
        },
        { rootMargin },
      );
      observer.observe(node);
      return () => observer.disconnect();
    },
    [rootMargin],
  );
  return [ref, inView];
}
