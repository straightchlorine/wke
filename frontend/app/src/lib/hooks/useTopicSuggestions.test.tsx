import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, renderHook } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import type { TopicCandidate } from "../../api/generated";

const searchTopics = vi.fn();
const listDossiers = vi.fn();
vi.mock("../../api/generated", () => ({
  searchTopics: (...args: unknown[]) => searchTopics(...args),
  listDossiers: (...args: unknown[]) => listDossiers(...args),
}));

const { useTopicSuggestions } = await import("./useTopicSuggestions");

function candidate(title: string, pageId: number): TopicCandidate {
  return { page_id: pageId, title, dossier_state: "none" };
}

function renderSuggestions(initial: string) {
  const client = new QueryClient();
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );
  return renderHook(({ text }: { text: string }) => useTopicSuggestions(text), {
    wrapper,
    initialProps: { text: initial },
  });
}

/** Lets the input rest, then lets the answer arrive. */
async function answered() {
  await rest(300);
  await rest(10);
}

async function rest(ms: number) {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(ms);
  });
}

beforeEach(() => {
  vi.useFakeTimers();
  searchTopics.mockResolvedValue({
    data: { query: "alan", results: [candidate("Alan Turing", 1)] },
  });
  listDossiers.mockResolvedValue({ data: { items: [] } });
});

afterEach(() => {
  vi.useRealTimers();
  vi.clearAllMocks();
});

describe("useTopicSuggestions", () => {
  it("lists nothing and asks nothing for fewer than three characters", async () => {
    const { result } = renderSuggestions("al");
    await rest(1000);
    expect(result.current).toEqual({ term: "", suggestions: [] });
    expect(searchTopics).not.toHaveBeenCalled();
    expect(listDossiers).not.toHaveBeenCalled();
  });

  it("waits for the input to rest, then asks both sources for the trimmed text", async () => {
    const { result } = renderSuggestions("  ala ");
    await rest(299);
    expect(searchTopics).not.toHaveBeenCalled();
    await rest(1);
    expect(searchTopics).toHaveBeenCalledWith({ query: { q: "ala", limit: 5 } });
    expect(listDossiers).toHaveBeenCalledWith({ query: { q: "ala", limit: 20 } });
    expect(result.current.term).toBe("ala");
  });

  it("puts stored dossiers first and caps the list at five", async () => {
    searchTopics.mockResolvedValue({
      data: {
        query: "ala",
        results: [1, 2, 3, 4, 5, 6].map((id) => candidate(`Alan ${id}`, id)),
      },
    });
    listDossiers.mockResolvedValue({ data: { items: [{ page_id: 9, title: "Alan Stored" }] } });
    const { result } = renderSuggestions("ala");
    await answered();
    expect(result.current.suggestions).toHaveLength(5);
    expect(result.current.suggestions[0]).toMatchObject({
      title: "Alan Stored",
      dossier_state: "ready",
    });
  });

  it("lists no titles while the input has moved past the answer", async () => {
    const { result, rerender } = renderSuggestions("alan");
    await answered();
    expect(result.current.suggestions).toHaveLength(1);
    rerender({ text: "alan t" });
    expect(result.current.term).toBe("alan");
    expect(result.current.suggestions).toEqual([]);
    await answered();
    expect(result.current.term).toBe("alan t");
  });

  it.each([
    ["Wikipedia search", searchTopics, "Alan Stored"],
    ["the stored list", listDossiers, "Alan Turing"],
  ])("keeps the other source's titles when %s fails", async (_name, failing, title) => {
    listDossiers.mockResolvedValue({ data: { items: [{ page_id: 9, title: "Alan Stored" }] } });
    searchTopics.mockResolvedValue({ data: { results: [candidate("Alan Turing", 1)] } });
    failing.mockRejectedValue(new Error("offline"));
    const { result } = renderSuggestions("ala");
    await answered();
    expect(result.current.suggestions.map((row) => row.title)).toEqual([title]);
  });

  it("restarts the wait on every keystroke", async () => {
    const { rerender } = renderSuggestions("ala");
    await rest(100);
    rerender({ text: "alan" });
    await rest(250);
    expect(searchTopics).not.toHaveBeenCalled();
    await rest(100);
    expect(searchTopics).toHaveBeenCalledTimes(1);
    expect(searchTopics).toHaveBeenCalledWith({ query: { q: "alan", limit: 5 } });
  });

  it("lists nothing when both sources fail", async () => {
    searchTopics.mockResolvedValue({ error: { status: 500 } });
    listDossiers.mockRejectedValue(new Error("offline"));
    const { result } = renderSuggestions("ala");
    await answered();
    expect(result.current.suggestions).toEqual([]);
    expect(searchTopics).toHaveBeenCalledTimes(1);
  });

  it("asks again for a text whose last answer was a failure", async () => {
    searchTopics.mockResolvedValue({ error: { status: 500 } });
    listDossiers.mockResolvedValue({ error: { status: 500 } });
    const { rerender } = renderSuggestions("ala");
    await answered();
    expect(searchTopics).toHaveBeenCalledTimes(1);
    rerender({ text: "alb" });
    await answered();
    rerender({ text: "ala" });
    await answered();
    expect(searchTopics).toHaveBeenCalledTimes(3);
  });
});
