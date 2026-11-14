import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, fireEvent, render, screen } from "@testing-library/react";
import { CopyButton, type CopyButtonProps } from "./CopyButton";

const writeText = vi.fn<(text: string) => Promise<void>>();

function renderCopy(props: Partial<CopyButtonProps> = {}) {
  return render(
    <CopyButton getText={() => "payload"} message="Copied" durationMs={1000} {...props}>
      {(copied) => (copied ? "Copied" : "Copy")}
    </CopyButton>,
  );
}

async function click() {
  await act(async () => {
    fireEvent.click(screen.getByRole("button"));
  });
}

describe("CopyButton", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    writeText.mockReset();
    writeText.mockResolvedValue(undefined);
    Object.defineProperty(navigator, "clipboard", { value: { writeText }, configurable: true });
  });

  afterEach(() => {
    vi.useRealTimers();
    document.getElementById("copy-fallback")?.remove();
  });

  it("writes the text, reports the message and reverts after durationMs", async () => {
    const onCopy = vi.fn();
    renderCopy({ onCopy });

    await click();
    expect(writeText).toHaveBeenCalledWith("payload");
    expect(onCopy).toHaveBeenCalledWith("Copied");
    expect(screen.getByRole("button").textContent).toBe("Copied");

    act(() => {
      vi.advanceTimersByTime(999);
    });
    expect(screen.getByRole("button").textContent).toBe("Copied");
    act(() => {
      vi.advanceTimersByTime(1);
    });
    expect(screen.getByRole("button").textContent).toBe("Copy");
  });

  it("reports fetchFailedMessage and writes nothing when getText resolves null", async () => {
    const onCopy = vi.fn();
    renderCopy({
      getText: () => Promise.resolve(null),
      fetchFailedMessage: "Could not fetch",
      onCopy,
    });

    await click();
    expect(writeText).not.toHaveBeenCalled();
    expect(onCopy).toHaveBeenCalledWith("Could not fetch");
    expect(document.getElementById("copy-fallback")).toBeNull();
    expect(screen.getByRole("button").textContent).toBe("Copy");
  });

  it("selects the text in #copy-fallback and reports writeFailedMessage when the write rejects", async () => {
    writeText.mockRejectedValue(new Error("denied"));
    const onCopy = vi.fn();
    renderCopy({ writeFailedMessage: "Press Ctrl+C", onCopy });

    await click();
    const fallback = document.getElementById("copy-fallback");
    expect(fallback).toBeInstanceOf(HTMLTextAreaElement);
    if (!(fallback instanceof HTMLTextAreaElement)) {
      return;
    }
    expect(fallback.value).toBe("payload");
    expect(fallback.selectionStart).toBe(0);
    expect(fallback.selectionEnd).toBe("payload".length);
    expect(document.activeElement).toBe(fallback);
    expect(fallback.readOnly).toBe(true);
    expect(onCopy).toHaveBeenCalledWith("Press Ctrl+C");
    expect(screen.getByRole("button").textContent).toBe("Copy");
  });

  it("reuses one fallback textarea across failed writes", async () => {
    writeText.mockRejectedValue(new Error("denied"));
    renderCopy();

    await click();
    await click();
    expect(document.querySelectorAll("#copy-fallback")).toHaveLength(1);
  });

  it("restarts the revert timer on a second copy", async () => {
    renderCopy();
    await click();
    act(() => {
      vi.advanceTimersByTime(600);
    });
    await click();
    act(() => {
      vi.advanceTimersByTime(600);
    });
    expect(screen.getByRole("button").textContent).toBe("Copied");

    act(() => {
      vi.advanceTimersByTime(400);
    });
    expect(screen.getByRole("button").textContent).toBe("Copy");
  });

  it("passes id, label and title to the button", () => {
    renderCopy({ id: "copy-url", ariaLabel: "Copy the URL", title: "https://example.org/a" });
    const button = screen.getByRole("button", { name: "Copy the URL" });
    expect(button.getAttribute("data-copy")).toBe("copy-url");
    expect(button.title).toBe("https://example.org/a");
  });

  it("ignores clicks while disabled (waiting)", async () => {
    const onCopy = vi.fn();
    renderCopy({ disabled: true, onCopy });

    await click();
    expect(writeText).not.toHaveBeenCalled();
    expect(onCopy).not.toHaveBeenCalled();
  });

  it("clears the revert timer on unmount", async () => {
    const { unmount } = renderCopy();
    await click();
    expect(vi.getTimerCount()).toBe(1);

    unmount();
    expect(vi.getTimerCount()).toBe(0);
  });
});
