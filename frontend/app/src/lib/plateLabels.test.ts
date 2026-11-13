import { describe, expect, it } from "vitest";
import { ALWAYS_NAMED } from "./labelLayout";
import { namesShownText } from "./plateLabels";

const INDEX_RULE = `A name is shown for the ${ALWAYS_NAMED} most-read dots, every dot with no other close by, the most-read dot of each group, and as many more as fit.`;
const RELATED_RULE =
  "Every dot is named, and a name crosses a line only where there is no clear space.";

describe("namesShownText", () => {
  it.each([
    [
      "the index graph's rule, then pointing",
      "index",
      false,
      `${INDEX_RULE} Point at any dot for its name.`,
    ],
    [
      "the index graph's rule, then tapping",
      "index",
      true,
      `${INDEX_RULE} Tap any dot for its name.`,
    ],
    [
      "that every dot is named in the related graph",
      "related",
      false,
      `${RELATED_RULE} Point at any dot for its name.`,
    ],
    [
      "that every dot is named in the related graph, then tapping",
      "related",
      true,
      `${RELATED_RULE} Tap any dot for its name.`,
    ],
  ] as const)("states %s", (_name, variant, touch, expected) => {
    expect(namesShownText(variant, touch)).toBe(expected);
  });
});
