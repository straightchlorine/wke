import { describe, expect, it } from "vitest";
import { slugPath, slugify, unslugify } from "./slug";

describe("slugify", () => {
  it("replaces spaces with underscores and keeps everything else, Wikipedia-style", () => {
    expect(slugify("Alan Turing")).toBe("Alan_Turing");
    expect(slugify("Lizzie Borden")).toBe("Lizzie_Borden");
  });

  it("keeps case, punctuation and diacritics untouched", () => {
    expect(slugify("C++")).toBe("C++");
    expect(slugify("Caf\u00e9 del Mar")).toBe("Caf\u00e9_del_Mar");
  });
});

describe("unslugify", () => {
  it("restores the spaces of a slugified title", () => {
    expect(unslugify("Alan_Turing")).toBe("Alan Turing");
    expect(unslugify(slugify("The Legend of Lizzie Borden"))).toBe("The Legend of Lizzie Borden");
  });

  it("URL-decodes a percent-encoded slug before restoring spaces", () => {
    expect(unslugify("Beyonc%C3%A9")).toBe("Beyonc\u00e9");
  });

  it("falls back to the raw slug when it is not valid percent-encoding", () => {
    expect(unslugify("100%_Cotton")).toBe("100% Cotton");
  });
});

describe("slugPath", () => {
  it.each([
    ["Mary, mother of Jesus", "/t/Mary,_mother_of_Jesus"],
    ["AC/DC", "/t/AC%2FDC"],
    ["What? Me worry", "/t/What%3F_Me_worry"],
    ["Godel's theorems", "/t/Godel's_theorems"],
  ])("writes %s as %s", (title, path) => {
    expect(slugPath(title)).toBe(path);
  });
});
