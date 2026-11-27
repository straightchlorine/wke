import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { parseTable, textLinks } from "../lib/structuredPassage";
import { PassageTable, countNoteText } from "./PassageTable";

const TEXT = [
  "Other personnel",
  "| Name | Activities | |",
  "| --- | --- | --- |",
  "| Farouk El-Baz | Geologist | |",
  "| Kurt Debus | Rocket scientist | |",
  "(21 rows; 2 shown)",
].join("\n");
const marker = { n: 3, href: "https://wiki/rev" };

function renderTable(
  text = TEXT,
  links = textLinks(text, undefined),
  mark: typeof marker | null = marker,
) {
  const layout = parseTable(text)!;
  return render(
    <PassageTable text={text} layout={layout} links={links} id="chunk-t1" marker={mark} />,
  );
}

describe("PassageTable", () => {
  it("renders a real table with its caption, header cells and body rows", () => {
    renderTable();
    const table = screen.getByRole("table");
    expect(table.querySelector("caption")?.textContent).toBe("Other personnel[3]");
    expect([...table.querySelectorAll("thead th")].map((th) => th.textContent)).toEqual([
      "Name",
      "Activities",
    ]);
    expect(table.querySelectorAll("tbody tr")).toHaveLength(2);
    expect(table.querySelectorAll("tbody tr:first-child td")).toHaveLength(2);
    expect(table.closest("[id]")?.id).toBe("chunk-t1");
  });

  it("puts the citation marker in the caption and links it", () => {
    renderTable();
    const link = screen.getByRole("link", { name: "[3]" });
    expect(link.getAttribute("href")).toBe("https://wiki/rev");
    expect(link.closest("caption")).not.toBeNull();
  });

  it("says how many rows are shown", () => {
    renderTable();
    expect(screen.getByText("2 of 21 rows shown")).toBeTruthy();
    expect(countNoteText({ total: 5, shown: 3, noun: "items" })).toBe("3 of 5 items shown");
  });

  it("shows no note and no marker when there are none", () => {
    renderTable(TEXT.replace("\n(21 rows; 2 shown)", ""), [], null);
    expect(screen.queryByText(/shown$/)).toBeNull();
    expect(screen.queryByRole("link")).toBeNull();
  });

  it("puts the marker under a table that has no caption", () => {
    renderTable(TEXT.split("\n").slice(1).join("\n"));
    expect(screen.getByRole("table").querySelector("caption")).toBeNull();
    expect(screen.getByRole("link", { name: "[3]" })).toBeTruthy();
  });

  it("makes a link span inside a cell a link to the article", () => {
    const start = TEXT.indexOf("Geologist");
    renderTable(TEXT, textLinks(TEXT, [{ start, end: start + 9, title: "Geologist (job)" }]), null);
    const link = screen.getByRole("link", { name: "Geologist" });
    expect(link.getAttribute("href")).toBe("https://en.wikipedia.org/wiki/Geologist_(job)");
    expect(link.closest("td")).not.toBeNull();
  });

  it("names a column that has cells but no header", () => {
    renderTable("T\n| A |  |\n| --- | --- |\n| 1 | note |", [], null);
    expect(screen.getByRole("columnheader", { name: "Unlabelled column" })).toBeTruthy();
  });
});
