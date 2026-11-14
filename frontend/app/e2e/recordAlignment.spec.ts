import type { Page } from "@playwright/test";
import { expect, lightOnly, only, test } from "./support";

/**
 * Measures every visible record row in `scope` (default: all records) and
 * returns what is wrong with it: baselines of label, value and unit that
 * differ by more than 1 px, anything past the record's right edge, and a
 * clipped value with no title.
 */
async function audit(page: Page, scope?: string): Promise<{ rows: number; issues: string[] }> {
  return page.evaluate((scopeSel) => {
    const issues: string[] = [];
    // First-line baseline: a zero-size inline-block placed before the text sits on it.
    // oxlint-disable-next-line unicorn/consistent-function-scoping -- the callback runs in the page, so its helpers cannot live outside it
    const baseline = (el: Element) => {
      const probe = document.createElement("span");
      probe.style.cssText = "display:inline-block;width:0;height:0;";
      el.prepend(probe);
      const y = probe.getBoundingClientRect().bottom;
      probe.remove();
      return y;
    };
    const roots = [...document.querySelectorAll(scopeSel ?? "[data-record]")].filter(
      (r) => r.getBoundingClientRect().width > 0,
    );
    let count = 0;
    for (const root of roots) {
      const box = root.getBoundingClientRect();
      const name =
        root.getAttribute("aria-label") ?? root.getAttribute("data-plate-board") ?? "record";
      for (const row of root.querySelectorAll("[data-record-row]")) {
        if (row.getBoundingClientRect().width === 0) {
          continue;
        }
        count += 1;
        const cells = Array.from(row.children);
        const label = cells[0]!;
        const hasLeader = cells[1]?.getAttribute("aria-hidden") === "true";
        const value = cells[hasLeader ? 2 : 1]!;
        const unit = cells[hasLeader ? 3 : 2];
        const where = `${name} / ${label.textContent?.slice(0, 20)}`;
        const labelY = baseline(label);
        if (value.textContent?.trim() && !value.querySelector("button")) {
          const diff = Math.abs(baseline(value) - labelY);
          if (diff > 1) {
            issues.push(`${where}: value baseline off by ${diff.toFixed(1)}`);
          }
        }
        if (unit && unit.textContent?.trim()) {
          const onLine =
            unit.getBoundingClientRect().top < value.getBoundingClientRect().bottom - 2;
          const inline = !unit.className.includes("basis-full") || onLine;
          if (onLine && inline && Math.abs(baseline(unit) - labelY) > 1) {
            issues.push(
              `${where}: unit baseline off by ${Math.abs(baseline(unit) - labelY).toFixed(1)}`,
            );
          }
        }
        const clipped = value.scrollWidth > value.clientWidth + 1;
        if (clipped && value.className.includes("truncate") && !value.getAttribute("title")) {
          issues.push(`${where}: clipped value without title`);
        }
        for (const el of [row, ...row.querySelectorAll("*")]) {
          const inClip = el !== value && !!el.closest(".truncate") && value.contains(el);
          if (inClip) {
            continue;
          }
          const r = el.getBoundingClientRect();
          if (r.width > 0 && r.right > box.right + 0.5) {
            issues.push(
              `${where}: <${el.tagName.toLowerCase()}> right ${r.right.toFixed(1)} > ${box.right.toFixed(1)}`,
            );
            break;
          }
        }
      }
    }
    return { rows: count, issues };
  }, scope ?? null);
}

lightOnly(() => {
  for (const [path, ready] of [
    ["/", "Cited context"],
    // A title narrower than the 44px tap target (Jesus) is clipped by its value box and reads as a clipped value, so this uses a longer one.
    ["/t/Apollo_11", "Apollo 11"],
    ["/machines", "For machines"],
  ] as const) {
    test(
      `records on ${path} share baselines and stay inside`,
      only("mobile-390", "desktop-1440"),
      async ({ page, open }) => {
        await open(path, {
          ready: page.getByRole("heading", { level: 1 }).filter({ hasText: ready }).first(),
        });
        const { rows, issues } = await audit(page);
        expect(rows).toBeGreaterThan(0);
        expect(issues).toEqual([]);
      },
    );
  }
});
