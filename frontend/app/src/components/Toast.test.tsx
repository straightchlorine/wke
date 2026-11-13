import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, render, screen } from "@testing-library/react";
import { useState } from "react";
import { Toast } from "./Toast";

function Harness({ durationMs }: { durationMs?: number }) {
  const [message, setMessage] = useState<string | null>(null);
  return (
    <div>
      <button type="button" onClick={() => setMessage("Copied 7,842 tokens")}>
        copy a
      </button>
      <button type="button" onClick={() => setMessage("Copied curl request")}>
        copy b
      </button>
      <Toast message={message} onDismiss={() => setMessage(null)} durationMs={durationMs} />
    </div>
  );
}

describe("Toast", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("stays mounted but invisible when there is no message, so the live region exists before text arrives", () => {
    render(<Toast message={null} onDismiss={() => {}} />);
    const status = screen.getByTestId("toast");
    expect(status.textContent).toBe("");
    expect(status.className).toContain("invisible");
  });

  it("clears the HUD bar by its own height only when asked, without adding the safe-area inset again", () => {
    const { rerender } = render(<Toast message="Copied" onDismiss={() => {}} />);
    expect(screen.getByTestId("toast").className).not.toContain("--hud-h");

    rerender(<Toast message="Copied" onDismiss={() => {}} aboveHud />);
    expect(screen.getByTestId("toast").className).toContain("var(--hud-h)");
    expect(screen.getByTestId("toast").className).not.toContain("env(");
  });

  it("announces the message through the shared live region", () => {
    const region = document.createElement("div");
    region.id = "live-region";
    document.body.appendChild(region);
    try {
      render(<Toast message="Copied" onDismiss={() => {}} />);
      expect(region.textContent).toBe("Copied");
    } finally {
      region.remove();
    }
  });

  it("is hidden from assistive tech, since the live region announces it", () => {
    render(<Toast message="Copied" onDismiss={() => {}} />);
    expect(screen.getByTestId("toast").getAttribute("aria-hidden")).toBe("true");
  });

  it("starts no timer without a message", () => {
    const onDismiss = vi.fn();
    render(<Toast message={null} onDismiss={onDismiss} durationMs={500} />);
    act(() => {
      vi.advanceTimersByTime(5000);
    });
    expect(onDismiss).not.toHaveBeenCalled();
  });

  it("dismisses after 1.6 s by default", () => {
    const onDismiss = vi.fn();
    render(<Toast message="Copied" onDismiss={onDismiss} />);
    act(() => {
      vi.advanceTimersByTime(1599);
    });
    expect(onDismiss).not.toHaveBeenCalled();
    act(() => {
      vi.advanceTimersByTime(1);
    });
    expect(onDismiss).toHaveBeenCalledTimes(1);
  });

  it("calls the latest onDismiss without restarting the timer", () => {
    const first = vi.fn();
    const second = vi.fn();
    const { rerender } = render(<Toast message="Copied" onDismiss={first} durationMs={1000} />);
    act(() => {
      vi.advanceTimersByTime(600);
    });
    rerender(<Toast message="Copied" onDismiss={second} durationMs={1000} />);
    act(() => {
      vi.advanceTimersByTime(400);
    });
    expect(first).not.toHaveBeenCalled();
    expect(second).toHaveBeenCalledTimes(1);
  });

  it("restarts the timer when the nonce changes under the same message", () => {
    const onDismiss = vi.fn();
    const { rerender } = render(
      <Toast message="Copied" nonce={1} onDismiss={onDismiss} durationMs={1000} />,
    );
    act(() => {
      vi.advanceTimersByTime(600);
    });
    rerender(<Toast message="Copied" nonce={2} onDismiss={onDismiss} durationMs={1000} />);
    act(() => {
      vi.advanceTimersByTime(600);
    });
    expect(onDismiss).not.toHaveBeenCalled();
    act(() => {
      vi.advanceTimersByTime(400);
    });
    expect(onDismiss).toHaveBeenCalledTimes(1);
  });

  it("shows the message text", () => {
    render(<Toast message="Copied" onDismiss={() => {}} />);
    expect(screen.getByTestId("toast").textContent).toBe("Copied");
  });

  it("dismisses after the given duration", () => {
    const onDismiss = vi.fn();
    render(<Toast message="Copied" onDismiss={onDismiss} durationMs={2000} />);

    act(() => {
      vi.advanceTimersByTime(1999);
    });
    expect(onDismiss).not.toHaveBeenCalled();

    act(() => {
      vi.advanceTimersByTime(1);
    });
    expect(onDismiss).toHaveBeenCalledTimes(1);
  });

  it("restarts the timer when a new message replaces the current one", () => {
    const { getByText } = render(<Harness durationMs={1600} />);

    act(() => {
      getByText("copy a").click();
    });
    expect(screen.getByTestId("toast").textContent).toBe("Copied 7,842 tokens");

    act(() => {
      vi.advanceTimersByTime(1000);
    });
    act(() => {
      getByText("copy b").click();
    });
    expect(screen.getByTestId("toast").textContent).toBe("Copied curl request");

    // 2000 ms after the first copy: only the restarted timer keeps it up.
    act(() => {
      vi.advanceTimersByTime(1000);
    });
    expect(screen.getByTestId("toast").className).not.toContain("invisible");

    act(() => {
      vi.advanceTimersByTime(600);
    });
    expect(screen.getByTestId("toast").className).toContain("invisible");
  });
});
