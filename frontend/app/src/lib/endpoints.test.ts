import { describe, expect, it } from "vitest";
import {
  dossierJsonUrl,
  dossierMarkdownUrl,
  llmsTxtUrl,
  mcpDossierCall,
  mcpUrl,
} from "./endpoints";

describe("endpoint URLs", () => {
  it("builds the llms.txt and MCP URLs on the base", () => {
    expect(llmsTxtUrl("https://wke.example")).toBe("https://wke.example/llms.txt");
    expect(mcpUrl("https://wke.example")).toBe("https://wke.example/mcp");
  });

  it.each([
    ["JSON", dossierJsonUrl, "/api/v1/dossiers/1095706?budget=8000"],
    ["Markdown", dossierMarkdownUrl, "/api/v1/dossiers/1095706.md?budget=8000"],
  ])("builds the %s URL, with parts only when asked", (_name, build, path) => {
    expect(build("https://wke.example", 1095706, 8000)).toBe(`https://wke.example${path}`);
    expect(build("https://wke.example", 1095706, 8000, "dossier,metadata")).toBe(
      `https://wke.example${path}&parts=dossier,metadata`,
    );
  });

  it("builds a bare path pattern from an empty base and the page_id placeholder", () => {
    expect(dossierJsonUrl("", "{page_id}", 2000)).toBe("/api/v1/dossiers/{page_id}?budget=2000");
    expect(dossierMarkdownUrl("", "{page_id}", 2000)).toBe(
      "/api/v1/dossiers/{page_id}.md?budget=2000",
    );
  });

  it("quotes the title in the MCP call", () => {
    expect(mcpDossierCall('The "Who"', 32000, "markdown")).toBe(
      'get_dossier({ "title": "The \\"Who\\"", "budget": 32000, "format": "markdown" })',
    );
  });
});
