import { createContext } from "react";
import type { LegendSize } from "./plateLegend";

/** What the plate, the frame around a graph, gives the graph inside it. */
export interface PlateSlots {
  /** The element the graph portals its board into. The board is the box that describes the dot the pointer is on. */
  board: HTMLElement | null;
  /** The size of the legend chip the plate draws over the frame, so the graph keeps clear of it. Null when there is none. */
  legend: LegendSize | null;
}

export const PlateSlotsContext = createContext<PlateSlots | null>(null);
