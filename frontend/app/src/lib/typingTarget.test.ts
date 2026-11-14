import { describe, expect, it } from "vitest";
import { isTypingTarget } from "./typingTarget";

/** jsdom does not implement isContentEditable, so every element starts as not editable. */
function make(tag: string, type?: string, editable = false): HTMLElement {
  const element = document.createElement(tag);
  Object.defineProperty(element, "isContentEditable", { value: editable });
  if (type) {
    element.setAttribute("type", type);
  }
  return element;
}

describe("isTypingTarget", () => {
  it.each([
    ["a text input", make("input", "text")],
    ["an input with no type", make("input")],
    ["a textarea", make("textarea")],
    ["a select", make("select")],
  ])("is true for %s", (_name, element) => {
    expect(isTypingTarget(element)).toBe(true);
  });

  it("is true for an editable element", () => {
    expect(isTypingTarget(make("div", undefined, true))).toBe(true);
  });

  it.each([
    ["a radio", make("input", "radio")],
    ["a checkbox", make("input", "checkbox")],
    ["a button input", make("input", "button")],
    ["a button", make("button")],
    ["a plain element", make("div")],
    ["no target", null],
  ])("is false for %s", (_name, target) => {
    expect(isTypingTarget(target)).toBe(false);
  });
});
