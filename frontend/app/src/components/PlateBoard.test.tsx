import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { linkedValue, PlateBoard, type PlateBoardNode } from "./PlateBoard";

const node: PlateBoardNode = {
  title: "Lizzie Borden",
  description: "American woman tried for murder in 1892",
  figure: { label: "Views", value: "326,311" },
  editsLastHour: 5,
  linkedTo: ["Fall River", "Andrew Borden", "Abby Borden"],
  state: "ready",
  href: "/t/Lizzie_Borden?budget=8000",
};

/** The value cell of the record row with this label. */
function rowValue(label: string) {
  return screen.getByText(label).nextElementSibling?.nextElementSibling?.textContent;
}

/** The classes of the badge chip, which set its variant, for a node in `state`. */
function badgeClass(state: "ready" | "building") {
  const { unmount } = render(<PlateBoard node={{ ...node, state }} />);
  const chip = [...document.querySelectorAll("[data-plate-badge] span")].find((e) =>
    e.className.includes("w-17"),
  )?.className;
  unmount();
  return chip;
}

describe("PlateBoard", () => {
  it("shows the pointer hint when idle, and the tap hint on touch", () => {
    const { rerender } = render(<PlateBoard node={null} />);
    expect(screen.getByRole("region", { name: "Selected article" }).textContent).toBe(
      "Point at a dot to see it here. Click it to select, then open its dossier.",
    );
    rerender(<PlateBoard node={null} touch />);
    expect(screen.getByRole("region", { name: "Selected article" }).textContent).toBe(
      "Tap a dot to see it here. Tap it again to open its dossier.",
    );
  });

  it("previews a node with its title, description and record rows, and a badge that is not a link", () => {
    render(<PlateBoard node={node} />);
    expect(screen.getByText("Lizzie Borden")).toBeTruthy();
    expect(screen.getByText("American woman tried for murder in 1892")).toBeTruthy();
    expect(rowValue("Views")).toBe("326,311");
    expect(rowValue("Edits in the last hour")).toBe("5");
    expect(screen.getByText("Fall River, Andrew Borden, +1")).toBeTruthy();
    expect(screen.getByText("Ready").className).not.toContain("underline");
    expect(screen.queryByRole("link")).toBeNull();
  });

  it("groups the thousands of an edit count", () => {
    render(<PlateBoard node={{ ...node, editsLastHour: 1234 }} />);
    expect(rowValue("Edits in the last hour")).toBe("1,234");
  });

  it("makes the badge text an underlined dossier link once selected, and lists the neighbours in a tooltip", () => {
    render(<PlateBoard node={node} selected />);
    expect(screen.getByText("Ready").className).toContain("underline");
    expect(screen.getByRole("link", { name: "Open dossier, ready" }).getAttribute("href")).toBe(
      "/t/Lizzie_Borden?budget=8000",
    );
    expect(screen.getByRole("button", { name: /Fall River, Andrew Borden, \+1/ })).toBeTruthy();
  });

  it("opens the dossier in the app on a plain click and leaves a modified click to the browser", () => {
    const onOpen = vi.fn();
    render(<PlateBoard node={node} selected onOpen={onOpen} />);
    const link = screen.getByRole("link", { name: "Open dossier, ready" });
    expect(fireEvent.click(link)).toBe(false);
    expect(onOpen).toHaveBeenCalledOnce();
    for (const modifier of [
      { ctrlKey: true },
      { metaKey: true },
      { shiftKey: true },
      { altKey: true },
      { button: 1 },
    ]) {
      expect(fireEvent.click(link, modifier)).toBe(true);
    }
    expect(onOpen).toHaveBeenCalledOnce();
  });

  it.each([
    ["ready", "Ready", "Open dossier, ready"],
    ["partial", "Partial", "Open dossier, partial"],
    ["building", "Building", "Open dossier, building"],
    ["none", "Not built", "Build dossier, not built"],
    [undefined, "Open", "Open dossier, open"],
  ] as const)("badges a %s dossier as %s, and names its link %s", (state, text, linkName) => {
    render(<PlateBoard node={{ ...node, state }} selected />);
    expect(screen.getByText(text)).toBeTruthy();
    expect(screen.getByRole("link", { name: linkName })).toBeTruthy();
  });

  it("draws a building dossier with the same hairline chip as a ready one", () => {
    expect(badgeClass("building")).toBe(badgeClass("ready"));
    expect(badgeClass("ready")).toContain("bg-transparent");
  });

  it("gives the Linked to value a native tooltip with every neighbour while previewing, not once selected", () => {
    const names = "Fall River, Andrew Borden, Abby Borden";
    const { unmount } = render(<PlateBoard node={node} />);
    expect(document.querySelector(`[title="${names}"]`)).not.toBeNull();
    unmount();
    render(<PlateBoard node={node} selected />);
    expect(document.querySelector(`[title="${names}"]`)).toBeNull();
  });

  it.each(
    (["ready", "partial", "building", "none"] as const).flatMap((state) =>
      [false, true].map((selected) => [state, selected] as const),
    ),
  )("gives the badge the same width for a %s dossier, selected %s", (state, selected) => {
    render(<PlateBoard node={{ ...node, state }} selected={selected} />);
    const chip = [...document.querySelectorAll("[data-plate-badge] span")].find((e) =>
      e.className.includes("w-17"),
    );
    expect(chip).toBeTruthy();
  });

  it("keeps every row when the node has no figure, no edit figure and no links", () => {
    render(
      <PlateBoard
        node={{
          ...node,
          description: undefined,
          figure: undefined,
          figureLabel: "Similarity",
          editsLastHour: null,
          editsMissing: "not tracked",
          state: undefined,
          linkedTo: [],
        }}
      />,
    );
    expect(rowValue("Similarity")).toBe("not measured");
    expect(rowValue("Edits in the last hour")).toBe("not tracked");
    expect(rowValue("Linked to")).toBe("Not linked today");
    expect(screen.getByText("Open")).toBeTruthy();
  });

  it("falls back to the Views label and to 'not measured' for edits", () => {
    render(<PlateBoard node={{ ...node, figure: undefined, editsLastHour: undefined }} />);
    expect(rowValue("Views")).toBe("not measured");
    expect(rowValue("Edits in the last hour")).toBe("not measured");
  });

  it("says no edit data while the feed is down, whatever count the node has", () => {
    render(<PlateBoard node={{ ...node, editsUnavailable: true }} />);
    expect(rowValue("Edits in the last hour")).toBe("no edit data");
  });

  it("marks the selected box apart from the preview", () => {
    const { rerender } = render(<PlateBoard node={node} />);
    expect(screen.getByRole("region").getAttribute("data-plate-board")).toBe("preview");
    rerender(<PlateBoard node={node} selected />);
    expect(screen.getByRole("region").getAttribute("data-plate-board")).toBe("selected");
  });
});

describe("linkedValue", () => {
  it.each([
    [[], "Not linked today"],
    [["A"], "A"],
    [["A", "B"], "A, B"],
    [["A", "B", "C"], "A, B, +1"],
    [["A", "B", "C", "D"], "A, B, +2"],
  ])("writes %j as %s", (titles, expected) => {
    expect(linkedValue(titles)).toBe(expected);
  });
});
