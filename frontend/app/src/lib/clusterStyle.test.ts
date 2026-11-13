import { describe, expect, it } from "vitest";
import { CLUSTER_COLORS, clusterVar, hullPath } from "./clusterStyle";

describe("hullPath", () => {
  it("returns an empty string for no points", () => {
    expect(hullPath([])).toBe("");
  });

  it("closes a polygon with one decimal per coordinate", () => {
    expect(
      hullPath([
        [0, 0],
        [10.25, 0],
        [5, 8],
      ]),
    ).toBe("M0.0 0.0L10.3 0.0L5.0 8.0Z");
  });
});

describe("clusterVar", () => {
  it.each([
    [0, "var(--wke-c1)"],
    [CLUSTER_COLORS.length - 1, "var(--wke-c6)"],
    [CLUSTER_COLORS.length, "var(--wke-c1)"],
    [CLUSTER_COLORS.length + 2, "var(--wke-c3)"],
  ])("maps cluster %i to %s", (cluster, expected) => {
    expect(clusterVar(cluster)).toBe(expected);
  });
});
