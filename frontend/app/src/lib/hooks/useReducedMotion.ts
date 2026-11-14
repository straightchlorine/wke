import { useMediaQuery } from "./useMediaQuery";

/** Tracks the `prefers-reduced-motion` media query. The app has no toggle of its own, so the OS setting decides. */
export function useReducedMotion(): boolean {
  return useMediaQuery("(prefers-reduced-motion: reduce)");
}
