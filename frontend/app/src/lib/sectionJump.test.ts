import { afterEach, expect, it, vi } from "vitest";
import { focusSectionHeading } from "./sectionJump";

afterEach(() => {
  document.body.innerHTML = "";
});

it("focuses the section heading without scrolling, and ignores an unknown id", () => {
  document.body.innerHTML =
    '<section id="s6"><h2 data-section-heading tabindex="-1">H</h2></section>';
  const heading = document.querySelector<HTMLElement>("h2")!;
  const focus = vi.spyOn(heading, "focus");
  focusSectionHeading("s6");
  expect(focus).toHaveBeenCalledWith({ preventScroll: true });
  expect(document.activeElement).toBe(heading);
  expect(() => focusSectionHeading("s99")).not.toThrow();
});
