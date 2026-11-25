import { useEffect, useRef } from "react";

/**
 * Puts focus back on the page's h1 when `phaseKey` changes, because each phase renders its own h1
 * and React unmounts the focused one, which drops focus to the body.
 * `arrivedViaNavigation` must be true for it to act; on a direct load nothing was focused, so
 * focusing later would draw a focus ring nobody asked for.
 */
export function useHeadingRefocus(phaseKey: string, arrivedViaNavigation: boolean): void {
  const previousKey = useRef(phaseKey);
  useEffect(() => {
    if (previousKey.current === phaseKey) {
      return;
    }
    previousKey.current = phaseKey;
    if (!arrivedViaNavigation) {
      return;
    }
    if (document.activeElement === document.body || document.activeElement == null) {
      // preventScroll stops focus() from fighting the router's scroll restoration.
      document.querySelector<HTMLElement>("main h1")?.focus({ preventScroll: true });
    }
  }, [phaseKey, arrivedViaNavigation]);
}
