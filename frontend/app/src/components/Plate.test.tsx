import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { useContext } from "react";
import { createPortal } from "react-dom";
import { legendChipSize } from "../lib/plateLegend";
import { PLATE_BOARD_PX } from "../lib/plateSide";
import { PlateSlotsContext } from "../lib/plateSlots";
import { Plate, type PlateKeyEntry } from "./Plate";

const base = {
  hud: "40 nodes",
  captionLead: "Plate 1.",
  captionBody: "The most-read articles.",
  guide: [{ label: "Size", value: "views" }],
};

const key: PlateKeyEntry[] = [
  { name: "Alpha", cluster: 0, href: "/t/alpha?budget=8000", state: "ready" },
  { name: "Beta", cluster: 1, href: "/t/beta?budget=8000", state: "none" },
  { name: "Gamma", cluster: 2, href: "/t/gamma?budget=8000" },
];

function swatchColours(): Array<string | null> {
  return [
    ...document.querySelectorAll<HTMLElement>('[data-plate-legend] span[aria-hidden="true"]'),
  ].map((el) => el.getAttribute("style"));
}

describe("Plate legend", () => {
  it("draws swatches only, in a row named for assistive tech", () => {
    render(
      <Plate {...base} colorKey={key} colorKeyLabel="Linked groups">
        <svg />
      </Plate>,
    );
    const row = screen.getByRole("group", { name: "Linked groups" });
    expect(row.querySelectorAll('span[aria-hidden="true"]')).toHaveLength(3);
    expect(screen.queryByText("Alpha")).toBeNull();
    for (const tip of row.querySelectorAll<HTMLElement>('[role="tooltip"]')) {
      expect(tip.style.display).toBe("none");
    }
    expect(screen.queryByText("Linked groups")).toBeNull();
    for (const name of ["Alpha", "Beta", "Gamma"]) {
      expect(screen.getByRole("button", { name: `Articles related to ${name}` })).toBeTruthy();
    }
  });

  it("draws the swatches on a chip inside the frame, not in a row under it", () => {
    const { container } = render(
      <Plate {...base} colorKey={key} colorKeyLabel="Linked groups">
        <svg />
      </Plate>,
    );
    const frame = container.querySelector("[data-plate-frame]");
    const row = screen.getByRole("group", { name: "Linked groups" });
    expect(frame?.contains(row)).toBe(true);
    expect(row.hasAttribute("data-plate-legend")).toBe(true);
  });

  it("opens a tooltip with the dossier link and reports the open group", () => {
    const onKeyActive = vi.fn();
    render(
      <Plate {...base} colorKey={key} onKeyActive={onKeyActive}>
        <svg />
      </Plate>,
    );
    fireEvent.focus(screen.getByRole("button", { name: "Articles related to Alpha" }));
    const open = screen.getByRole("link", { name: "Open dossier" });
    expect(open.getAttribute("href")).toBe("/t/alpha?budget=8000");
    expect(onKeyActive).toHaveBeenLastCalledWith(0);
    fireEvent.keyDown(open, { key: "Escape" });
    expect(onKeyActive).toHaveBeenLastCalledWith(null);
  });

  it("keeps the open group when a different swatch's tooltip closes", () => {
    const onKeyActive = vi.fn();
    render(
      <Plate {...base} colorKey={key} onKeyActive={onKeyActive}>
        <svg />
      </Plate>,
    );
    fireEvent.focus(screen.getByRole("button", { name: "Articles related to Alpha" }));
    fireEvent.focus(screen.getByRole("button", { name: "Articles related to Beta" }));
    expect(onKeyActive).toHaveBeenLastCalledWith(1);
    fireEvent.keyDown(screen.getByRole("link", { name: "Open dossier" }), { key: "Escape" });
    expect(onKeyActive).toHaveBeenLastCalledWith(1);
    fireEvent.keyDown(screen.getByRole("link", { name: "Build dossier" }), { key: "Escape" });
    expect(onKeyActive).toHaveBeenLastCalledWith(null);
  });

  it("says Build dossier for a dossier that is not ready", () => {
    render(
      <Plate {...base} colorKey={key}>
        <svg />
      </Plate>,
    );
    fireEvent.focus(screen.getByRole("button", { name: "Articles related to Beta" }));
    expect(screen.getByRole("link", { name: "Build dossier" })).toBeTruthy();
  });

  it("draws no swatches when there are none", () => {
    render(
      <Plate {...base}>
        <svg />
      </Plate>,
    );
    expect(screen.queryByRole("group", { name: "Group colour" })).toBeNull();
  });
});

describe("Plate legend colours", () => {
  it("colours each swatch by its group's colour index, not by its place in the row", () => {
    const entries: PlateKeyEntry[] = [
      { name: "A", cluster: 4, href: "/a" },
      { name: "B", cluster: 0, href: "/b" },
      { name: "C", cluster: 2, href: "/c" },
    ];
    render(
      <Plate {...base} colorKey={entries}>
        <svg />
      </Plate>,
    );
    const [a, b, c] = swatchColours();
    expect(a).toContain("var(--wke-c5)");
    expect(b).toContain("var(--wke-c1)");
    expect(c).toContain("var(--wke-c3)");
  });

  it("cycles the colours for a group index past the last colour", () => {
    render(
      <Plate {...base} colorKey={[{ name: "A", cluster: 7, href: "/a" }]}>
        <svg />
      </Plate>,
    );
    expect(swatchColours()[0]).toContain("var(--wke-c2)");
  });

  it("draws no more swatches than there are group colours", () => {
    const many = Array.from({ length: 8 }, (_, i) => ({
      name: `G${i}`,
      cluster: i,
      href: `/g${i}`,
    }));
    render(
      <Plate {...base} colorKey={many}>
        <svg />
      </Plate>,
    );
    expect(swatchColours()).toHaveLength(6);
  });
});

/** Draws a plate with one legend swatch and opens its tooltip; returns the dossier link in it. */
function openTip(onOpen?: () => void) {
  render(
    <Plate
      {...base}
      colorKey={[{ name: "Alpha", cluster: 0, href: "/t/alpha", state: "ready", onOpen }]}
    >
      <svg />
    </Plate>,
  );
  fireEvent.focus(screen.getByRole("button", { name: "Articles related to Alpha" }));
  return screen.getByRole("link", { name: "Open dossier" });
}

describe("Plate legend link", () => {
  it("opens the dossier in the app on a plain click and leaves a modified click to the browser", () => {
    const onOpen = vi.fn();
    const link = openTip(onOpen);
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

  it("follows the link as usual when there is no handler", () => {
    expect(fireEvent.click(openTip())).toBe(true);
  });
});

/** Shows what a plate gives its children: the legend chip's size, and a node inside the board slot. */
function SlotProbe() {
  const slots = useContext(PlateSlotsContext);
  return (
    <>
      <output data-testid="legend">{JSON.stringify(slots?.legend ?? null)}</output>
      {slots?.board ? createPortal(<p data-testid="in-slot" />, slots.board) : null}
    </>
  );
}

describe("Plate frame", () => {
  it("names the figure by its caption and shows the stats chip", () => {
    render(
      <Plate {...base}>
        <svg />
      </Plate>,
    );
    expect(screen.getByRole("figure", { name: "Plate 1. The most-read articles." })).toBeTruthy();
    expect(screen.getByText("40 nodes")).toBeTruthy();
  });

  it("shows the how-to-read rows and the note in a tooltip", () => {
    render(
      <Plate {...base} guideNote="Names are shown for the top ten.">
        <svg />
      </Plate>,
    );
    fireEvent.focus(screen.getByRole("button", { name: "How to read the plate" }));
    expect(screen.getByText("Size")).toBeTruthy();
    expect(screen.getByText("views")).toBeTruthy();
    expect(screen.getByText("Names are shown for the top ten.")).toBeTruthy();
  });

  it("gives its children a slot of fixed height for the node box, and the legend chip's size", () => {
    render(
      <Plate {...base} colorKey={key}>
        <SlotProbe />
      </Plate>,
    );
    expect(screen.getByTestId("in-slot").parentElement?.style.height).toBe(`${PLATE_BOARD_PX}px`);
    expect(JSON.parse(screen.getByTestId("legend").textContent)).toEqual(legendChipSize(3, false));
  });

  it("gives no legend size when there are no swatches", () => {
    render(
      <Plate {...base}>
        <SlotProbe />
      </Plate>,
    );
    expect(screen.getByTestId("legend").textContent).toBe("null");
  });
});
