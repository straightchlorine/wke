import type { Page } from "@playwright/test";

/** The Home concept graph's svg, which is the only graph Home draws. */
export const HOME_GRAPH = 'svg[role="group"]';

/** The svg of the related-articles graph on a dossier page, found by its aria-label. */
export const RELATED_GRAPH = 'svg[role="group"][aria-label^="Articles related to"]';

/** The panel under a graph that describes the node the pointer is on or that is selected. */
export const BOARD = "[data-plate-board]";

/**
 * Returns the indexes of the graph's nodes whose hit centre is the topmost element under the pointer.
 * A centre also has to lie at least 130px from the top of the viewport, 40px from the bottom and 20px from either side.
 */
export function reachableNodes(page: Page, graph: string): Promise<number[]> {
  return page.evaluate((sel) => {
    const found: number[] = [];
    [...document.querySelectorAll(`${sel} a`)].forEach((a, i) => {
      const hit = a.querySelector("[data-plate-hit]")!.getBoundingClientRect();
      const x = hit.left + hit.width / 2;
      const y = hit.top + hit.height / 2;
      const top = document.elementFromPoint(x, y);
      if (
        top &&
        a.contains(top) &&
        y > 130 &&
        y < window.innerHeight - 40 &&
        x > 20 &&
        x < window.innerWidth - 20
      ) {
        found.push(i);
      }
    });
    return found;
  }, graph);
}
