import { describe, expect, it, vi } from "vitest";
import { act, fireEvent, render, screen } from "@testing-library/react";
import { createPortal } from "react-dom";
import { useRovingFocus } from "./useRovingFocus";

function Row({
  count,
  onMoved,
  outside,
}: {
  count: number;
  onMoved?: (moved: boolean) => void;
  outside?: HTMLElement;
}) {
  const roving = useRovingFocus(count);
  return (
    <div
      role="toolbar"
      aria-label="row"
      tabIndex={-1}
      onKeyDown={(event) => {
        const moved = roving.moveOnKey(event);
        onMoved?.(moved);
      }}
    >
      {Array.from({ length: count }, (_, i) => (
        <button
          key={i}
          ref={roving.itemRef(i)}
          tabIndex={i === roving.current ? 0 : -1}
          onFocus={() => roving.markFocused(i)}
        >
          item {i}
        </button>
      ))}
      {outside ? createPortal(<button>portal</button>, outside) : null}
      <button onClick={roving.focusCurrent}>back</button>
    </div>
  );
}

const tabbable = () =>
  screen
    .getAllByRole("button", { name: /item/ })
    .map((b) => b.tabIndex)
    .join(",");

describe("useRovingFocus", () => {
  it("puts only the first item in the tab order at first", () => {
    render(<Row count={3} />);
    expect(tabbable()).toBe("0,-1,-1");
  });

  it("moves focus and the tab order with the arrow keys, and stops at the ends", () => {
    render(<Row count={3} />);
    const first = screen.getByRole("button", { name: "item 0" });
    act(() => first.focus());
    fireEvent.keyDown(first, { key: "ArrowRight" });
    expect(document.activeElement).toBe(screen.getByRole("button", { name: "item 1" }));
    expect(tabbable()).toBe("-1,0,-1");
    fireEvent.keyDown(document.activeElement!, { key: "End" });
    fireEvent.keyDown(document.activeElement!, { key: "ArrowDown" });
    expect(document.activeElement).toBe(screen.getByRole("button", { name: "item 2" }));
    fireEvent.keyDown(document.activeElement!, { key: "Home" });
    expect(document.activeElement).toBe(first);
    fireEvent.keyDown(first, { key: "ArrowUp" });
    expect(document.activeElement).toBe(first);
  });

  it("takes the tab order to an item that gets focus some other way", () => {
    render(<Row count={3} />);
    act(() => screen.getByRole("button", { name: "item 2" }).focus());
    expect(tabbable()).toBe("-1,-1,0");
  });

  it("reports whether a key moved focus", () => {
    const onMoved = vi.fn();
    render(<Row count={3} onMoved={onMoved} />);
    const first = screen.getByRole("button", { name: "item 0" });
    fireEvent.keyDown(first, { key: "ArrowRight" });
    expect(onMoved).toHaveBeenLastCalledWith(true);
    fireEvent.keyDown(first, { key: "Enter" });
    expect(onMoved).toHaveBeenLastCalledWith(false);
  });

  it("ignores keys that started outside the row, such as in a portal", () => {
    const outside = document.createElement("div");
    document.body.append(outside);
    const onMoved = vi.fn();
    render(<Row count={3} onMoved={onMoved} outside={outside} />);
    fireEvent.keyDown(screen.getByRole("button", { name: "portal" }), { key: "ArrowRight" });
    expect(onMoved).toHaveBeenLastCalledWith(false);
    expect(tabbable()).toBe("0,-1,-1");
    outside.remove();
  });

  it("does nothing with no items", () => {
    const onMoved = vi.fn();
    render(<Row count={0} onMoved={onMoved} />);
    fireEvent.keyDown(screen.getByRole("toolbar"), { key: "ArrowRight" });
    expect(onMoved).toHaveBeenLastCalledWith(false);
  });

  it("keeps the tab order on an item that exists when the count shrinks", () => {
    const { rerender } = render(<Row count={4} />);
    act(() => screen.getByRole("button", { name: "item 3" }).focus());
    expect(tabbable()).toBe("-1,-1,-1,0");
    rerender(<Row count={2} />);
    expect(tabbable()).toBe("-1,0");
  });

  it("puts focus back on the item in the tab order", () => {
    render(<Row count={3} />);
    act(() => screen.getByRole("button", { name: "item 1" }).focus());
    act(() => screen.getByRole("button", { name: "back" }).focus());
    fireEvent.click(screen.getByRole("button", { name: "back" }));
    expect(document.activeElement).toBe(screen.getByRole("button", { name: "item 1" }));
  });
});
