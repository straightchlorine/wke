import { afterEach, describe, expect, it } from "vitest";
import { plateFrameInsetPx, readHairlinePx } from "./plateFrame";

describe("plateFrameInsetPx", () => {
  it.each([
    [1, 10],
    [0.8, 9.2],
    [1.1429, 10.5716],
  ])("takes the borders and padding of both sides at a %s px rule", (hairline, expected) => {
    expect(plateFrameInsetPx(hairline)).toBeCloseTo(expected, 4);
  });
});

describe("readHairlinePx", () => {
  afterEach(() => document.documentElement.style.removeProperty("--hairline"));

  it("reads the token from the page root", () => {
    document.documentElement.style.setProperty("--hairline", "1.0667px");
    expect(readHairlinePx()).toBe(1.0667);
  });

  it("is 1 when the token is not set", () => {
    expect(readHairlinePx()).toBe(1);
  });
});
