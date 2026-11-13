import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, fireEvent, render, screen } from "@testing-library/react";
import { InfoDot, type TipClearance } from "./InfoDot";

function isOpen(tooltip: HTMLElement): boolean {
  return tooltip.style.display !== "none";
}

function wrapperOf(el: HTMLElement): HTMLElement {
  const parent = el.parentElement;
  if (!parent) {
    throw new Error("expected the InfoDot button to have a parent element");
  }
  return parent;
}

function rectOf(left: number, top: number, right: number, bottom: number): DOMRect {
  return new DOMRect(left, top, right - left, bottom - top);
}

// jsdom has no layout: give the trigger a place on the page. The tooltip itself measures 0 by 0.
function stubTriggerRect(rect: DOMRect) {
  vi.spyOn(HTMLElement.prototype, "getBoundingClientRect").mockImplementation(function (
    this: HTMLElement,
  ) {
    return this.tagName === "BUTTON" ? rect : rectOf(0, 0, 0, 0);
  });
}

function besideClearance(): TipClearance {
  return {
    anchor: rectOf(100, 380, 300, 420),
    frame: rectOf(50, 300, 900, 600),
    avoid: [],
    points: [],
    besideFirst: true,
  };
}

function touchTap(button: HTMLElement) {
  fireEvent.pointerDown(button, { pointerType: "touch" });
  fireEvent.focus(button);
  const click = new MouseEvent("click", { bubbles: true });
  Object.defineProperty(click, "pointerType", { value: "touch" });
  fireEvent(button, click);
}

function renderInteractive(onOpenChange?: (open: boolean) => void) {
  render(
    <InfoDot
      interactive
      triggerLabel="Articles related to Alpha"
      onOpenChange={onOpenChange}
      text={<a href="/t/alpha">Open dossier</a>}
    >
      <span aria-hidden="true">swatch</span>
    </InfoDot>,
  );
  return screen.getByRole("button", { name: "Articles related to Alpha" });
}

describe("InfoDot", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it("opens 300ms after hover starts", () => {
    render(<InfoDot text="Keys 1, 2, 3 pick 2k, 8k, 32k." />);
    fireEvent.mouseEnter(wrapperOf(screen.getByRole("button")));

    act(() => {
      vi.advanceTimersByTime(299);
    });
    expect(isOpen(screen.getByRole("tooltip", { hidden: true }))).toBe(false);

    act(() => {
      vi.advanceTimersByTime(1);
    });
    expect(isOpen(screen.getByRole("tooltip"))).toBe(true);
  });

  it("opens at once on keyboard focus", () => {
    render(<InfoDot text="Keys 1, 2, 3 pick 2k, 8k, 32k." />);
    fireEvent.focus(screen.getByRole("button"));

    expect(isOpen(screen.getByRole("tooltip"))).toBe(true);
  });

  it("closes 100ms after the pointer leaves", () => {
    render(<InfoDot text="Keys 1, 2, 3 pick 2k, 8k, 32k." />);
    const button = screen.getByRole("button");
    fireEvent.focus(button);
    expect(isOpen(screen.getByRole("tooltip"))).toBe(true);

    fireEvent.mouseLeave(wrapperOf(button));
    act(() => {
      vi.advanceTimersByTime(99);
    });
    expect(isOpen(screen.getByRole("tooltip", { hidden: true }))).toBe(true);

    act(() => {
      vi.advanceTimersByTime(1);
    });
    expect(isOpen(screen.getByRole("tooltip", { hidden: true }))).toBe(false);
  });

  it("closes on Escape", () => {
    render(<InfoDot text="Keys 1, 2, 3 pick 2k, 8k, 32k." />);
    const button = screen.getByRole("button");
    fireEvent.focus(button);
    expect(isOpen(screen.getByRole("tooltip"))).toBe(true);

    fireEvent.keyDown(button, { key: "Escape" });
    expect(isOpen(screen.getByRole("tooltip", { hidden: true }))).toBe(false);
  });

  it("closes on a document-level Escape while focus is elsewhere", () => {
    render(<InfoDot text="Keys 1, 2, 3 pick 2k, 8k, 32k." />);
    fireEvent.mouseEnter(wrapperOf(screen.getByRole("button")));
    act(() => {
      vi.advanceTimersByTime(300);
    });
    expect(isOpen(screen.getByRole("tooltip"))).toBe(true);

    fireEvent.keyDown(document, { key: "Escape" });
    expect(isOpen(screen.getByRole("tooltip", { hidden: true }))).toBe(false);
  });

  it("always links the tooltip with aria-describedby, open or not", () => {
    render(<InfoDot text="Keys 1, 2, 3 pick 2k, 8k, 32k." />);
    const button = screen.getByRole("button");
    const tooltip = screen.getByRole("tooltip", { hidden: true });
    expect(button.getAttribute("aria-describedby")).toBe(tooltip.id);

    fireEvent.focus(button);
    expect(button.getAttribute("aria-describedby")).toBe(screen.getByRole("tooltip").id);
  });

  it("reopens on Enter or Space after Escape left focus on the trigger", () => {
    render(<InfoDot text="Keys 1, 2, 3 pick 2k, 8k, 32k." />);
    const button = screen.getByRole("button");
    fireEvent.focus(button);
    fireEvent.keyDown(button, { key: "Escape" });
    expect(isOpen(screen.getByRole("tooltip", { hidden: true }))).toBe(false);

    fireEvent.keyDown(button, { key: "Enter" });
    expect(isOpen(screen.getByRole("tooltip"))).toBe(true);
  });

  it("renders only the mark, with no button or tooltip, when decorative", () => {
    const { container } = render(<InfoDot decorative text="" />);
    expect(screen.queryByRole("button")).toBeNull();
    expect(screen.queryByRole("tooltip", { hidden: true })).toBeNull();
    expect(container.querySelector("span[aria-hidden='true']")?.textContent).toBe("i");
  });

  it("calls onReveal each time the tooltip opens, and reports the open state", () => {
    const onReveal = vi.fn();
    const onOpenChange = vi.fn();
    render(<InfoDot text="Tip" onReveal={onReveal} onOpenChange={onOpenChange} />);
    const button = screen.getByRole("button");

    fireEvent.focus(button);
    expect(onReveal).toHaveBeenCalledTimes(1);
    expect(onOpenChange).toHaveBeenLastCalledWith(true);

    fireEvent.keyDown(button, { key: "Escape" });
    expect(onOpenChange).toHaveBeenLastCalledWith(false);
    expect(onReveal).toHaveBeenCalledTimes(1);
  });

  describe("touch", () => {
    it("opens on a tap, ignores the mouse-leave that follows, and closes on a second tap", () => {
      render(<InfoDot text="Tip" />);
      const button = screen.getByRole("button");

      touchTap(button);
      expect(isOpen(screen.getByRole("tooltip"))).toBe(true);

      fireEvent.mouseLeave(wrapperOf(button));
      act(() => {
        vi.advanceTimersByTime(1000);
      });
      expect(isOpen(screen.getByRole("tooltip"))).toBe(true);

      touchTap(button);
      expect(isOpen(screen.getByRole("tooltip", { hidden: true }))).toBe(false);
    });

    it("leaves the tooltip as it is on a mouse click", () => {
      render(<InfoDot text="Tip" />);
      const button = screen.getByRole("button");
      fireEvent.focus(button);
      fireEvent.click(button);
      expect(isOpen(screen.getByRole("tooltip"))).toBe(true);
    });

    it("does not open from the focus of a tap, only from its click", () => {
      render(<InfoDot text="Tip" />);
      const button = screen.getByRole("button");
      fireEvent.pointerDown(button, { pointerType: "touch" });
      fireEvent.focus(button);
      expect(isOpen(screen.getByRole("tooltip", { hidden: true }))).toBe(false);
    });

    it("closes on a touch outside, and stays open on a touch on the dot", () => {
      render(<InfoDot text="Tip" />);
      const button = screen.getByRole("button");
      touchTap(button);

      fireEvent.pointerDown(button, { pointerType: "touch" });
      expect(isOpen(screen.getByRole("tooltip"))).toBe(true);

      fireEvent.pointerDown(document.body, { pointerType: "mouse" });
      expect(isOpen(screen.getByRole("tooltip"))).toBe(true);

      fireEvent.pointerDown(document.body, { pointerType: "touch" });
      expect(isOpen(screen.getByRole("tooltip", { hidden: true }))).toBe(false);
    });
  });

  describe("placement", () => {
    it("puts the tooltip a gap above the trigger, aligned with its left edge", () => {
      stubTriggerRect(rectOf(100, 400, 114, 414));
      render(<InfoDot text="Tip" />);
      fireEvent.focus(screen.getByRole("button"));

      const tip = screen.getByRole("tooltip");
      expect(tip.style.left).toBe("100px");
      expect(tip.style.top).toBe("394px");
    });

    it("narrows the tooltip to the bounds ancestor when it is wider", () => {
      vi.spyOn(HTMLElement.prototype, "offsetWidth", "get").mockReturnValue(500);
      vi.spyOn(HTMLElement.prototype, "getBoundingClientRect").mockImplementation(function (
        this: HTMLElement,
      ) {
        return this.tagName === "MAIN" ? rectOf(0, 0, 300, 800) : rectOf(100, 400, 114, 414);
      });
      render(
        <main>
          <InfoDot text="Tip" tipBounds="main" />
        </main>,
      );
      fireEvent.focus(screen.getByRole("button"));

      expect(screen.getByRole("tooltip").style.maxWidth).toBe("284px");
    });

    it("moves to the spot the clearance chooses", () => {
      stubTriggerRect(rectOf(100, 400, 114, 414));
      render(<InfoDot text="Tip" clearOf={besideClearance} />);
      fireEvent.focus(screen.getByRole("button"));

      const tip = screen.getByRole("tooltip");
      expect(tip.style.left).toBe("306px");
      expect(tip.style.top).toBe("400px");
    });

    it("waits longer to close a tooltip that moved away from its trigger", () => {
      stubTriggerRect(rectOf(100, 400, 114, 414));
      render(<InfoDot text="Tip" clearOf={besideClearance} />);
      const button = screen.getByRole("button");
      fireEvent.focus(button);
      fireEvent.mouseLeave(wrapperOf(button));

      act(() => {
        vi.advanceTimersByTime(699);
      });
      expect(isOpen(screen.getByRole("tooltip"))).toBe(true);
      act(() => {
        vi.advanceTimersByTime(1);
      });
      expect(isOpen(screen.getByRole("tooltip", { hidden: true }))).toBe(false);
    });
  });

  describe("interactive", () => {
    it("stays open while focus moves from the trigger into its link", () => {
      const button = renderInteractive();
      fireEvent.focus(button);
      const link = screen.getByRole("link", { name: "Open dossier" });
      fireEvent.blur(button, { relatedTarget: link });
      expect(isOpen(screen.getByRole("tooltip"))).toBe(true);
      fireEvent.blur(link, { relatedTarget: document.body });
      expect(isOpen(screen.getByRole("tooltip", { hidden: true }))).toBe(false);
    });

    it("moves focus to the link on Enter, and Esc inside the tooltip closes it and focuses the trigger", () => {
      const onOpenChange = vi.fn();
      const button = renderInteractive(onOpenChange);
      fireEvent.focus(button);
      expect(onOpenChange).toHaveBeenLastCalledWith(true);
      fireEvent.keyDown(button, { key: "Enter" });
      const link = screen.getByRole("link", { name: "Open dossier" });
      expect(document.activeElement).toBe(link);
      fireEvent.keyDown(link, { key: "Escape" });
      expect(isOpen(screen.getByRole("tooltip", { hidden: true }))).toBe(false);
      expect(document.activeElement).toBe(button);
      expect(onOpenChange).toHaveBeenLastCalledWith(false);
    });

    it("gives the pointer longer to cross into the tooltip before it closes", () => {
      const button = renderInteractive();
      fireEvent.focus(button);
      const wrapper = wrapperOf(button);
      fireEvent.mouseLeave(wrapper);
      act(() => {
        vi.advanceTimersByTime(200);
      });
      expect(isOpen(screen.getByRole("tooltip"))).toBe(true);
      fireEvent.mouseEnter(wrapper);
      act(() => {
        vi.advanceTimersByTime(1000);
      });
      expect(isOpen(screen.getByRole("tooltip"))).toBe(true);
    });
  });
});
