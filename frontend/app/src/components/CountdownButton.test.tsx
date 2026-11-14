import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, fireEvent, render, screen } from "@testing-library/react";
import { CountdownButton } from "./CountdownButton";

describe("CountdownButton", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("counts down once a second and ignores clicks until it reaches zero", () => {
    const onClick = vi.fn();
    render(<CountdownButton seconds={2} onClick={onClick} />);
    const button = screen.getByRole("button");
    expect(button.textContent).toBe("Retry in 2 s");

    fireEvent.click(button);
    expect(onClick).not.toHaveBeenCalled();

    act(() => {
      vi.advanceTimersByTime(999);
    });
    expect(button.textContent).toBe("Retry in 2 s");
    act(() => {
      vi.advanceTimersByTime(1);
    });
    expect(button.textContent).toBe("Retry in 1 s");

    act(() => {
      vi.advanceTimersByTime(1000);
    });
    expect(button.textContent).toBe("Retry");
    expect(vi.getTimerCount()).toBe(0);
    expect(button.getAttribute("aria-disabled")).toBeNull();
    fireEvent.click(button);
    expect(onClick).toHaveBeenCalledTimes(1);
  });

  it("restarts the count when `seconds` changes", () => {
    const { rerender } = render(<CountdownButton seconds={3} onClick={() => {}} />);
    for (let i = 0; i < 2; i++) {
      act(() => {
        vi.advanceTimersByTime(1000);
      });
    }
    expect(screen.getByRole("button").textContent).toBe("Retry in 1 s");

    rerender(<CountdownButton seconds={5} onClick={() => {}} />);
    expect(screen.getByRole("button").textContent).toBe("Retry in 5 s");
  });

  it("does not retry by itself when the count ends", () => {
    const onClick = vi.fn();
    render(<CountdownButton seconds={1} onClick={onClick} />);
    act(() => {
      vi.advanceTimersByTime(5000);
    });
    expect(onClick).not.toHaveBeenCalled();
  });
});
