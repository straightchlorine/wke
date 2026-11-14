import { describe, expect, it, vi } from "vitest";
import { act, fireEvent, render, screen } from "@testing-library/react";
import { CodeBlock } from "./CodeBlock";

const START = "**Machine summary (model output)**";

function tinted(container: HTMLElement) {
  return Array.from(container.querySelectorAll("pre span.bg-model")).map((el) => el.textContent);
}

function pre(container: HTMLElement) {
  return container.querySelector("pre");
}

describe("CodeBlock", () => {
  it("shows the text as given, line breaks included", () => {
    const { container } = render(<CodeBlock heading="Request" code={"GET /a\n\nPOST /b"} />);
    expect(pre(container)?.textContent).toBe("GET /a\n\nPOST /b");
  });

  it("dims # lines unless comments is false", () => {
    const code = "# note\nbody";
    const { container, rerender } = render(<CodeBlock heading="x" code={code} />);
    expect(
      Array.from(container.querySelectorAll("pre span.text-ink-3")).map((e) => e.textContent),
    ).toEqual(["# note"]);
    rerender(<CodeBlock heading="x" code={code} comments={false} />);
    expect(container.querySelectorAll("pre span.text-ink-3")).toHaveLength(0);
    expect(pre(container)?.textContent).toBe(code);
  });

  it("tints the model block from its start line through the Model line", () => {
    const code = `before\n${START}\nSome words.\nModel: distilbart\nafter`;
    const { container } = render(<CodeBlock heading="x" code={code} />);
    expect(tinted(container)).toEqual([`${START}\nSome words.\nModel: distilbart`]);
    expect(pre(container)?.textContent).toBe(code);
  });

  it("tints a model block that has no Model line to the end of the text", () => {
    const code = `before\n${START}\nSome words.\nMore words.`;
    const { container } = render(<CodeBlock heading="x" code={code} />);
    expect(tinted(container)).toEqual([`${START}\nSome words.\nMore words.`]);
    expect(pre(container)?.textContent).toBe(code);
  });

  it("does not dim a # line inside the model block", () => {
    const code = `${START}\n# heading\nModel: m`;
    const { container } = render(<CodeBlock heading="x" code={code} />);
    expect(container.querySelectorAll("pre span.text-ink-3")).toHaveLength(0);
  });

  it("has no Copy button without copy", () => {
    render(<CodeBlock heading="x" code="abc" />);
    expect(screen.queryByRole("button")).toBeNull();
  });

  it.each([
    ["the shown code by default", undefined, "abc"],
    ["the text option when set", "other", "other"],
  ])("copies %s and reports the message", async (_name, text, written) => {
    const writeText = vi.fn<(text: string) => Promise<void>>().mockResolvedValue(undefined);
    Object.defineProperty(navigator, "clipboard", { value: { writeText }, configurable: true });
    const onCopy = vi.fn();
    render(
      <CodeBlock
        heading="x"
        code="abc"
        onCopy={onCopy}
        copy={{ id: "c1", text, message: "Copied the request" }}
      />,
    );
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Copy" }));
    });
    expect(writeText).toHaveBeenCalledWith(written);
    expect(onCopy).toHaveBeenCalledWith("Copied the request");
  });

  it("names the button by label, and by ariaLabel when given", () => {
    const { rerender } = render(
      <CodeBlock heading="x" code="abc" copy={{ id: "c1", label: "Copy request" }} />,
    );
    expect(screen.getByRole("button", { name: "Copy request" }).textContent).toBe("Copy request");
    rerender(
      <CodeBlock
        heading="x"
        code="abc"
        copy={{ id: "c1", label: "Copy", ariaLabel: "Copy the request" }}
      />,
    );
    const button = screen.getByRole("button", { name: "Copy the request" });
    expect(button.textContent).toBe("Copy");
    expect(button.getAttribute("data-copy")).toBe("c1");
  });
});
