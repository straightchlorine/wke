import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, fireEvent, render, screen } from "@testing-library/react";
import { EndpointRow, endpointRecordRow, type EndpointProps } from "./EndpointRow";
import { Record } from "./Record";

const writeText = vi.fn<(text: string) => Promise<void>>();

const endpoint: EndpointProps = {
  label: "llms.txt",
  line: "GET https://wke.example/llms.txt",
  copyText: "https://wke.example/llms.txt",
  message: "Copied URL",
};

const shapes = [
  ["EndpointRow", (props: EndpointProps) => <EndpointRow {...props} sentence="A plain index." />],
  ["endpointRecordRow", (props: EndpointProps) => <Record rows={[endpointRecordRow(props)]} />],
] as const;

async function clickCopy() {
  await act(async () => {
    fireEvent.click(screen.getByRole("button"));
  });
}

it("gives the clipped line of EndpointRow as its title, so the whole line can be read", () => {
  render(<EndpointRow {...endpoint} sentence="A plain index." />);
  expect(screen.getByText(endpoint.line).getAttribute("title")).toBe(endpoint.line);
});

describe.each(shapes)("%s", (_name, view) => {
  beforeEach(() => {
    writeText.mockReset();
    writeText.mockResolvedValue(undefined);
    Object.defineProperty(navigator, "clipboard", { value: { writeText }, configurable: true });
  });

  afterEach(() => {
    document.getElementById("copy-fallback")?.remove();
  });

  it("shows the label and the line", () => {
    render(view(endpoint));
    expect(screen.getByText("llms.txt")).toBeTruthy();
    expect(screen.getByText(endpoint.line)).toBeTruthy();
  });

  it("copies the copy text, not the line, and reports the message", async () => {
    const onCopy = vi.fn();
    render(view({ ...endpoint, onCopy }));
    await clickCopy();
    expect(writeText).toHaveBeenCalledWith("https://wke.example/llms.txt");
    expect(onCopy).toHaveBeenCalledWith("Copied URL");
    expect(screen.getByRole("button").textContent).toBe("Copied");
  });

  it("names the button by `copyLabel` and `ariaLabel`", () => {
    render(view({ ...endpoint, copyLabel: "Copy config", ariaLabel: "Copy MCP config" }));
    expect(screen.getByRole("button", { name: "Copy MCP config" }).textContent).toBe("Copy config");
  });

  it("ignores a click while there is nothing to copy", async () => {
    render(view({ ...endpoint, copyText: null }));
    await clickCopy();
    expect(writeText).not.toHaveBeenCalled();
    expect(screen.getByRole("button").getAttribute("aria-disabled")).toBe("true");
  });
});
