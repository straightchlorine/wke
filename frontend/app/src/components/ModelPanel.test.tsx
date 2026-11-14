import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { ModelPanel } from "./ModelPanel";
import type { MachineSummary } from "../api/generated";

function makeSummary(params: MachineSummary["params"], inferSeconds?: number): MachineSummary {
  return {
    kind: "machine_summary",
    text: "A short summary.",
    model: "distilbart",
    model_revision: "abc123",
    params,
    generated_at: "2026-11-13T09:05:00Z",
    ...(inferSeconds === undefined ? {} : { infer_seconds: inferSeconds }),
  };
}

const links = (...indexes: number[]) => indexes.map((index) => ({ id: `c${index}`, index }));

function textOf(startsWith: string): string {
  const el = screen.getByText((_, node) => node?.textContent?.startsWith(startsWith) ?? false, {
    selector: "p, span",
    ignore: "a",
  });
  return el.textContent ?? "";
}

describe("ModelPanel", () => {
  it("sorts passage numbers and groups consecutive ones into ranges", () => {
    render(<ModelPanel summary={makeSummary({})} chunkLinks={links(8, 5, 3, 4, 10)} />);
    expect(textOf("Summarised from")).toBe("Summarised from passages 3 to 5, 8, 10 below.");
  });

  it("uses the singular word for one passage", () => {
    render(<ModelPanel summary={makeSummary({})} chunkLinks={links(7)} />);
    expect(textOf("Summarised from")).toBe("Summarised from passage 7 below.");
  });

  it("prints the duration and source tokens when both are present", () => {
    render(<ModelPanel summary={makeSummary({ input_tokens: 512 }, 2.5)} />);
    expect(textOf("distilbart revision")).toMatch(
      /generated .+ in 2\.5 s, from 512 tokens of source$/,
    );
  });

  it("omits the duration and source tokens when both keys are absent", () => {
    render(<ModelPanel summary={makeSummary({})} />);
    expect(textOf("distilbart revision")).toBe(
      "distilbart revision abc123, generated 2026-11-13, 09:05 UTC",
    );
  });
});
