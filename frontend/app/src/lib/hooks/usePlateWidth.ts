import { useEffect, useState } from "react";
import { plateFrameInsetPx, readHairlinePx } from "../plateFrame";

/** The width used until the frame has been measured. */
const INITIAL_WIDTH_PX = 364;
/** The narrowest graph drawn, so a collapsed frame does not squeeze it to nothing. */
const MIN_WIDTH_PX = 200;

/**
 * Measures the width the graph has inside its bordered frame (the plate), so the SVG is drawn at
 * the size it is shown at instead of being scaled. Returns that width and the ref callback to put on the frame's wrapper.
 */
export function usePlateWidth(): [(el: HTMLDivElement | null) => void, number] {
  const [frameEl, setFrameEl] = useState<HTMLDivElement | null>(null);
  const [width, setWidth] = useState(INITIAL_WIDTH_PX);

  useEffect(() => {
    if (!frameEl || typeof ResizeObserver === "undefined") {
      return () => {};
    }
    const observer = new ResizeObserver((entries) => {
      const entry = entries[0];
      if (!entry) return;
      const inside = entry.contentRect.width - plateFrameInsetPx(readHairlinePx());
      setWidth(Math.max(MIN_WIDTH_PX, Math.round(inside)));
    });
    observer.observe(frameEl);
    return () => observer.disconnect();
  }, [frameEl]);

  return [setFrameEl, width];
}
