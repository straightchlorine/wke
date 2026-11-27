import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { parseList, textLinks } from "../lib/structuredPassage";
import { PassageBullets } from "./PassageBullets";

const TEXT = "- one\n- two\n  - two a\n  - two b\n- three\n(9 items; 3 shown)";
const marker = { n: 2, href: "https://wiki/rev" };

function renderList(
  text = TEXT,
  links = textLinks(text, undefined),
  mark: typeof marker | null = marker,
) {
  return render(
    <PassageBullets
      text={text}
      layout={parseList(text)!}
      links={links}
      id="chunk-l1"
      marker={mark}
    />,
  );
}

describe("PassageBullets", () => {
  it("renders a real list, nested where the text nests", () => {
    renderList();
    const lists = screen.getAllByRole("list");
    expect(lists).toHaveLength(2);
    expect(screen.getAllByRole("listitem")).toHaveLength(5);
    expect(lists[0]!.querySelectorAll(":scope > li")).toHaveLength(3);
    expect(lists[1]!.closest("li")?.firstChild?.textContent).toBe("two");
    expect(lists[1]!.querySelectorAll(":scope > li")).toHaveLength(2);
  });

  it("ends the last item with the citation marker, in one no-wrap span with its last word", () => {
    renderList();
    const link = screen.getByRole("link", { name: "[2]" });
    expect(link.closest("li")?.textContent).toBe("three[2]");
    expect(link.closest("span")?.textContent).toBe("three[2]");
  });

  it("puts the marker on the deepest last item", () => {
    renderList("- one\n- two\n  - two a\n    - two a i");
    expect(screen.getByRole("link", { name: "[2]" }).closest("li")?.textContent).toBe("two a i[2]");
  });

  it("says how many items are shown", () => {
    renderList();
    expect(screen.getByText("3 of 9 items shown")).toBeTruthy();
  });

  it("makes a link span inside an item a link, and keeps the marker after it", () => {
    const text = "- see Moon";
    const start = text.indexOf("Moon");
    renderList(text, textLinks(text, [{ start, end: start + 4, title: "Moon" }]));
    const link = screen.getByRole("link", { name: "Moon" });
    expect(link.getAttribute("href")).toBe("https://en.wikipedia.org/wiki/Moon");
    expect(link.closest("li")?.textContent).toBe("see Moon[2]");
  });
});
