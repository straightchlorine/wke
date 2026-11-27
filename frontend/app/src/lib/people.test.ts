import { describe, expect, it } from "vitest";
import { AUTHOR, CONTRIBUTORS_2025, CURRENT_VERSION, PROJECT_2025, joinNames } from "./people";

describe("people", () => {
  it("credits only the author for the current version", () => {
    expect(CURRENT_VERSION).toEqual([AUTHOR]);
  });

  it("lists the four people of the 2025 project, the author first", () => {
    expect(PROJECT_2025.map((person) => person.name)).toEqual([
      "Piotr Krzysztof Lis",
      "Jakub Kucharski",
      "Wiktor Jarosi\u0144ski",
      "Daniel Ka\u0142mucki",
    ]);
    expect(PROJECT_2025[0]).toBe(AUTHOR);
    expect(CONTRIBUTORS_2025).toEqual(PROJECT_2025.slice(1));
  });

  it("keeps the Polish letters in the names", () => {
    const names = PROJECT_2025.map((person) => person.name).join(" ");
    expect(names).toContain("\u0144");
    expect(names).toContain("\u0142");
    expect(names.normalize("NFC")).toBe(names);
  });

  it("links each person to the agreed places, Codeberg only for the author", () => {
    const hrefs = Object.fromEntries(PROJECT_2025.map((p) => [p.name, p.links.map((l) => l.href)]));
    expect(hrefs).toEqual({
      "Piotr Krzysztof Lis": [
        "https://piotrkrzysztof.dev",
        "https://github.com/straightchlorine",
        "https://codeberg.org/piotrkrzysztof",
        "https://www.linkedin.com/in/straightchlorine",
      ],
      "Jakub Kucharski": [
        "https://github.com/kubson2002k",
        "https://www.linkedin.com/in/jakub-kucharski-360811305/",
      ],
      "Wiktor Jarosi\u0144ski": ["https://www.linkedin.com/in/wiktor-jarosi%C5%84ski-719885244/"],
      "Daniel Ka\u0142mucki": ["https://www.linkedin.com/in/danielkalmucki/"],
    });
  });

  it("marks only the Codeberg link as About-page only", () => {
    const marked = PROJECT_2025.flatMap((person) =>
      person.links.filter((link) => link.aboutOnly).map((link) => link.label),
    );
    expect(marked).toEqual(["Codeberg"]);
  });

  it("has no duplicate names, hrefs or ids", () => {
    const ids = PROJECT_2025.flatMap((person) => (person.id ? [person.id] : []));
    const hrefs = PROJECT_2025.flatMap((person) => person.links.map((link) => link.href));
    expect(new Set(PROJECT_2025.map((person) => person.name)).size).toBe(PROJECT_2025.length);
    expect(new Set(ids).size).toBe(ids.length);
    expect(new Set(hrefs).size).toBe(hrefs.length);
  });

  it("gives the author and Jakub a shared id and the others none", () => {
    expect(PROJECT_2025.map((person) => person.id)).toEqual([
      "https://piotrkrzysztof.dev/#piotr",
      "https://piotrkrzysztof.dev/#jakub",
      undefined,
      undefined,
    ]);
  });
});

describe("joinNames", () => {
  it("joins with commas and a last 'and'", () => {
    expect(joinNames([])).toBe("");
    expect(joinNames(["A"])).toBe("A");
    expect(joinNames(["A", "B"])).toBe("A and B");
    expect(joinNames(["A", "B", "C"])).toBe("A, B and C");
  });
});
