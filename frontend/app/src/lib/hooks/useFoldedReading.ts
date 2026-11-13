import { useState } from "react";
import { getDossierView } from "../../api/dossier";
import type { Chunk, Section } from "../../api/generated";

/** The passages of a section the budget left out: `"loading"` while they are fetched, then the passages. */
export type FoldedText = Chunk[] | "loading";

/** The largest budget the API takes, in tokens. */
const FULL_BUDGET = 32000;

/**
 * Lets the reader read a left-out section in place. It fetches the dossier at the largest budget and
 * keeps that section's passages, and a second call for the same section closes it again.
 */
export function useFoldedReading(
  pageId: number | null,
  onToast: (message: string) => void,
): { texts: Record<string, FoldedText>; toggle: (section: Section) => Promise<void> } {
  const [state, setState] = useState<{ pageId: number | null; texts: Record<string, FoldedText> }>({
    pageId,
    texts: {},
  });
  if (state.pageId !== pageId) setState({ pageId, texts: {} });
  const texts = state.pageId === pageId ? state.texts : {};

  /** Applies a change to the texts unless the dossier has changed since the request began. */
  function update(
    forPageId: number | null,
    change: (prev: Record<string, FoldedText>) => Record<string, FoldedText>,
  ) {
    setState((prev) =>
      prev.pageId === forPageId ? { pageId: prev.pageId, texts: change(prev.texts) } : prev,
    );
  }

  function drop(sectionId: string) {
    update(pageId, (prev) => {
      const next = { ...prev };
      delete next[sectionId];
      return next;
    });
  }

  async function toggle(section: Section) {
    if (texts[section.id]) {
      drop(section.id);
      return;
    }
    if (!pageId) return;
    update(pageId, (prev) => ({ ...prev, [section.id]: "loading" }));
    const result = await getDossierView({
      path: { page_id: pageId },
      query: { budget: FULL_BUDGET },
    });
    if (result.error || result.data == null) {
      drop(section.id);
      onToast("Could not load the full section");
      return;
    }
    const byId = new Map(result.data.chunks.map((chunk) => [chunk.id, chunk]));
    const chunks = section.chunk_ids
      .map((id) => byId.get(id))
      .filter((chunk): chunk is Chunk => chunk != null);
    update(pageId, (prev) =>
      prev[section.id] === "loading" ? { ...prev, [section.id]: chunks } : prev,
    );
  }

  return { texts, toggle };
}
