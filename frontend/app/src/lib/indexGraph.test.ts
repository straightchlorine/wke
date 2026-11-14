import { describe, expect, it } from "vitest";
import type { TrendingTopic } from "../api/generated";
import { colorKeyGroups, toGraphNodes } from "./indexGraph";

function topic(
  id: number,
  title: string,
  views: number,
  over: Partial<TrendingTopic> = {},
): TrendingTopic {
  return {
    rank: id,
    page_id: id,
    title,
    views,
    rev_id: 1,
    dossier_state: "none",
    ...over,
  };
}

const edge = (source: number, target: number) => ({ source, target, weight: 0.5 });

describe("toGraphNodes", () => {
  it("maps a topic to a node with the slug of its title", () => {
    const nodes = toGraphNodes([
      topic(7, "Mary, mother of Jesus", 99, {
        description: "d",
        edits_last_hour: 3,
        dossier_state: "ready",
      }),
    ]);
    expect(nodes).toEqual([
      {
        id: 7,
        title: "Mary, mother of Jesus",
        slug: "Mary,_mother_of_Jesus",
        views: 99,
        description: "d",
        editsLastHour: 3,
        state: "ready",
      },
    ]);
  });
});

describe("colorKeyGroups", () => {
  const nodes = toGraphNodes([
    topic(1, "Low", 10),
    topic(2, "High", 50, { dossier_state: "ready" }),
    topic(3, "Alone", 500),
    topic(4, "Other pair low", 5),
    topic(5, "Other pair high", 6, { dossier_state: "partial" }),
  ]);

  it("names each group of two or more by its most-read member, in colour order", () => {
    const groups = colorKeyGroups(nodes, [edge(1, 2), edge(4, 5)]);
    expect(groups.map((g) => g.name)).toEqual(["High", "Other pair high"]);
    expect(groups.map((g) => g.state)).toEqual(["ready", "partial"]);
    expect(groups.map((g) => g.cluster)).toEqual([0, 1]);
  });

  it("leaves out an article with no link", () => {
    expect(colorKeyGroups(nodes, [edge(1, 2)]).map((g) => g.name)).toEqual(["High"]);
  });

  it("returns nothing without edges", () => {
    expect(colorKeyGroups(nodes, [])).toEqual([]);
  });
});
