import { describe, expect, it } from "vitest";
import { matchTier, mergeStoredFirst, rankBuiltFirst } from "./searchRank";

const row = (title: string, dossier_state: "ready" | "partial" | "building" | "none") => ({
  title,
  dossier_state,
});

describe("rankBuiltFirst", () => {
  it("puts built titles first and keeps the API order inside each group", () => {
    const ranked = rankBuiltFirst([
      row("Lizzie Borden House", "none"),
      row("Lizzie Borden Trial", "none"),
      row("Lizzie Borden", "ready"),
      row("Lizzie Borden (film)", "partial"),
      row("Lizzie", "none"),
    ]);
    expect(ranked.map((r) => r.title)).toEqual([
      "Lizzie Borden",
      "Lizzie Borden (film)",
      "Lizzie Borden House",
      "Lizzie Borden Trial",
      "Lizzie",
    ]);
  });

  it("does not change the input list", () => {
    const input = [row("B", "none"), row("A", "ready")];
    rankBuiltFirst(input);
    expect(input.map((r) => r.title)).toEqual(["B", "A"]);
  });
});

const wiki = (page_id: number, title: string, dossier_state: "ready" | "none" = "none") => ({
  page_id,
  title,
  dossier_state,
});

describe("mergeStoredFirst", () => {
  it("lists a page found by both sources once, with Wikipedia's description", () => {
    const merged = mergeStoredFirst(
      "pac",
      [{ page_id: 7, title: "Pac (wrestler)" }],
      [wiki(3, "PAC"), { ...wiki(7, "Pac (Wrestler)", "ready"), description: "Mexican wrestler" }],
      5,
    );
    expect(merged.map((entry) => entry.title)).toEqual(["Pac (wrestler)", "PAC"]);
    expect(merged[0]?.description).toBe("Mexican wrestler");
  });

  it("dedupes by title when the page ids differ", () => {
    const merged = mergeStoredFirst("pac", [{ page_id: 7, title: "Pac" }], [wiki(8, "pac")], 5);
    expect(merged).toHaveLength(1);
  });

  it("lists a renamed page once, matched by page id, with Wikipedia's description", () => {
    const merged = mergeStoredFirst(
      "pac",
      [
        { page_id: 7, title: "Pac" },
        { page_id: 7, title: "Pac (old title)" },
      ],
      [{ ...wiki(7, "Pacman"), description: "Arcade game" }],
      5,
    );
    expect(merged).toEqual([
      { page_id: 7, title: "Pac", description: "Arcade game", dossier_state: "ready" },
    ]);
  });

  it("caps the list", () => {
    const stored = [1, 2, 3].map((id) => ({ page_id: id, title: `Pac ${id}` }));
    const merged = mergeStoredFirst(
      "pac",
      stored,
      [wiki(10, "a"), wiki(11, "b"), wiki(12, "c")],
      4,
    );
    expect(merged.map((entry) => entry.page_id)).toEqual([1, 2, 3, 10]);
  });

  it("falls back to Wikipedia's order when nothing is stored", () => {
    const merged = mergeStoredFirst("pac", [], [wiki(1, "a"), wiki(2, "b", "ready")], 5);
    expect(merged.map((entry) => entry.page_id)).toEqual([2, 1]);
  });
});

describe("matchTier", () => {
  it.each([
    ["Lizzie Borden", "Liz", 0],
    ["Mad Max (film)", "mad", 0],
    ["Anything", "  ", 0],
    ["Monster: The Lizzie Borden Story", "Liz", 1],
    ["Mr. Madison", "mad", 1],
    ["Church-Turing thesis", "turing", 1],
    ["Elizabeth Holmes", "Liz", 2],
    ["Mahathir Mohamad", "Mad", 2],
    ["Nothing here", "xyz", 2],
  ] as const)("ranks %s for %s as tier %i", (title, query, tier) => {
    expect(matchTier(title, query)).toBe(tier);
  });
});

describe("mergeStoredFirst ranking", () => {
  it("ranks word-start matches above infix ones for Liz", () => {
    const merged = mergeStoredFirst(
      "Liz",
      [
        { page_id: 3, title: "Elizabeth Holmes" },
        { page_id: 2, title: "Monster: The Lizzie Borden Story" },
        { page_id: 1, title: "Lizzie Borden" },
      ],
      [wiki(4, "Elizabeth II"), wiki(5, "Liz Truss")],
      6,
    );
    expect(merged.map((r) => r.title)).toEqual([
      "Lizzie Borden",
      "Monster: The Lizzie Borden Story",
      "Elizabeth Holmes",
      "Liz Truss",
      "Elizabeth II",
    ]);
    expect(merged.map((r) => r.dossier_state)).toEqual(["ready", "ready", "ready", "none", "none"]);
  });

  it("keeps the API order between a title that starts with the query and one with a later word that does", () => {
    const merged = mergeStoredFirst(
      "turing",
      [],
      [
        wiki(1, "Alan Turing", "ready"),
        wiki(2, "Turing machine", "ready"),
        wiki(3, "Church-Turing thesis"),
        wiki(4, "Returing"),
      ],
      6,
    );
    expect(merged.map((r) => r.title)).toEqual([
      "Alan Turing",
      "Turing machine",
      "Church-Turing thesis",
      "Returing",
    ]);
  });
});
