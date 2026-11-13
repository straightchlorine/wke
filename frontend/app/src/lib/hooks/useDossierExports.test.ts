import { beforeEach, describe, expect, it, vi } from "vitest";
import { act, renderHook } from "@testing-library/react";
import { fetchDossierMarkdownText } from "../../api/dossier";
import { loadDossier } from "../../test/fixtures";
import { useDossierExports } from "./useDossierExports";

vi.mock("../../api/dossier", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../../api/dossier")>()),
  fetchDossierMarkdownText: vi.fn(),
}));
const fetchMarkdown = vi.mocked(fetchDossierMarkdownText);

const dossier = loadDossier();

describe("useDossierExports", () => {
  const onToast = vi.fn();
  const click = vi.fn();
  let blobs: Blob[];

  beforeEach(() => {
    fetchMarkdown.mockReset();
    onToast.mockReset();
    click.mockReset();
    blobs = [];
    URL.createObjectURL = (blob) => {
      if (blob instanceof Blob) {
        blobs.push(blob);
      }
      return "blob:x";
    };
    URL.revokeObjectURL = () => {};
    vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(function (
      this: HTMLAnchorElement,
    ) {
      click(this.download);
    });
  });

  const mount = (full = dossier) =>
    renderHook(() => useDossierExports(dossier, full, "Jesus", 8000, onToast)).result;

  it("fetches the Markdown of the dossier's page at the page's budget", async () => {
    fetchMarkdown.mockResolvedValue("# Jesus");
    const result = mount();
    expect(await result.current.fetchAsContext()).toBe("# Jesus");
    expect(fetchMarkdown).toHaveBeenCalledWith(dossier.topic.page_id, 8000);
  });

  it("describes the copy with the token count and the pinned revision", () => {
    const message = mount().current.copyMessage;
    expect(message).toMatch(/^Copied as text\/markdown, [\d,]+ dossier tokens, revision \d+$/);
  });

  it("downloads the Markdown named for the slug and the budget", async () => {
    fetchMarkdown.mockResolvedValue("# Jesus");
    const result = mount();
    await act(() => result.current.downloadMarkdown());
    expect(click).toHaveBeenCalledWith("Jesus-8k.md");
    expect(blobs[0]?.type).toBe("text/markdown");
    expect(onToast).not.toHaveBeenCalled();
  });

  it("says so when the Markdown could not be fetched, and downloads nothing", async () => {
    fetchMarkdown.mockResolvedValue(null);
    const result = mount();
    await act(() => result.current.downloadMarkdown());
    expect(onToast).toHaveBeenCalledWith("Download failed");
    expect(click).not.toHaveBeenCalled();
  });

  it("downloads the full dossier as JSON named for the slug and the budget", async () => {
    const full = { ...dossier, sections: dossier.sections.slice(0, 3) };
    mount(full).current.downloadJson();
    expect(click).toHaveBeenCalledWith("Jesus-8k.json");
    expect(blobs[0]?.type).toBe("application/json");
    const body: unknown = JSON.parse(await blobs[0]!.text());
    expect(body).toMatchObject({
      dossier: { sections: full.sections },
      metadata: { topic: { title: dossier.topic.title } },
    });
  });
});
