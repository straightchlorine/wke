import type { Locator, Page } from "@playwright/test";

/**
 * The height of the clickable strip around a control: from its vertical
 * centre, the contiguous run of points where a click still lands on the
 * control (or something inside it), at a horizontal point `dx` from its left edge.
 */
export async function hitExtent(target: Locator, dx = 6): Promise<number> {
  await target.scrollIntoViewIfNeeded();
  return target.evaluate((el, offset) => {
    el.scrollIntoView({ block: "center" });
    const box = el.getBoundingClientRect();
    const x = box.left + Math.min(offset, Math.max(box.width - 1, 1));
    const mid = box.top + box.height / 2;
    const lands = (y: number) => {
      const hit = document.elementFromPoint(x, y);
      return hit != null && (hit === el || el.contains(hit));
    };
    let up = 0;
    while (up < 80 && lands(mid - up - 1)) up += 1;
    let down = 0;
    while (down < 80 && lands(mid + down)) down += 1;
    return up + down;
  }, dx);
}

/** The width of the clickable strip, measured the way `hitExtent` measures height. */
export async function hitWidth(target: Locator): Promise<number> {
  await target.scrollIntoViewIfNeeded();
  return target.evaluate((el) => {
    el.scrollIntoView({ block: "center" });
    const box = el.getBoundingClientRect();
    const mid = box.left + box.width / 2;
    const y = box.top + box.height / 2;
    const lands = (x: number) => {
      const hit = document.elementFromPoint(x, y);
      return hit != null && (hit === el || el.contains(hit));
    };
    let left = 0;
    while (left < 80 && lands(mid - left - 1)) left += 1;
    let right = 0;
    while (right < 80 && lands(mid + right)) right += 1;
    return left + right;
  });
}

// A point above and below the control's box, `reach` px from its centre,
// must still land on the control: a bigger hit area around a smaller box.
export async function hitsControl(
  page: Page,
  selector: string,
  index: number,
  reach: number,
): Promise<boolean> {
  return page.evaluate(
    ({ selector: sel, index: i, reach: r }) => {
      const el = document.querySelectorAll(sel)[i];
      if (!el) {
        return false;
      }
      el.scrollIntoView({ block: "center" });
      const box = el.getBoundingClientRect();
      const x = box.left + Math.min(box.width / 2, 20);
      return [-r, 0, r].every((dy) => {
        const hit = document.elementFromPoint(x, box.top + box.height / 2 + dy);
        return hit === el || el.contains(hit);
      });
    },
    { selector, index, reach },
  );
}
