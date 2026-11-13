import { describe, expect, it } from "vitest";
import { renderHook } from "@testing-library/react";
import type { DossierView } from "../api/dossier";
import { loadDossier } from "../test/fixtures";
import {
  clipDescription,
  dossierDescription,
  dossierJsonLd,
  homeJsonLd,
  useSeo,
  WEBSITE_JSON_LD,
  type SeoInput,
} from "./seo";

const base = loadDossier();

function dossier(description: string | undefined, lead: string, rev = 42): DossierView {
  const seed = base.citations.find((c) => c.role === "seed") ?? base.citations[0];
  const leadChunkId = base.sections[0]?.chunk_ids[0];
  if (!seed || leadChunkId == null) {
    throw new Error("fixture has no seed citation or lead chunk");
  }
  return {
    ...base,
    topic: { ...base.topic, description },
    citations: [{ ...seed, pin: { ...seed.pin, rev_id: rev } }],
    chunks: base.chunks.map((c) => (c.id === leadChunkId ? { ...c, text: lead } : c)),
  };
}

describe("clipDescription", () => {
  it("leaves a short text alone", () => {
    expect(clipDescription("A short one.")).toBe("A short one.");
  });

  it("cuts on a word boundary within the limit", () => {
    const clipped = clipDescription("word ".repeat(60));
    expect(clipped.length).toBeLessThanOrEqual(155);
    expect(clipped.endsWith("word...")).toBe(true);
  });
});

describe("dossierDescription", () => {
  it("prefers the Wikipedia short description", () => {
    expect(dossierDescription(dossier("English mathematician", "Lead sentence. More."))).toBe(
      "English mathematician",
    );
  });

  it("falls back to the first lead sentence", () => {
    expect(dossierDescription(dossier(undefined, "Lead sentence. More."))).toBe("Lead sentence.");
  });

  it("falls back to the pinned revision", () => {
    expect(dossierDescription(dossier(undefined, "no sentence end here"))).toBe(
      "Cited to Wikipedia revision 42.",
    );
  });
});

describe("dossierDescription revision fallback", () => {
  it("uses the first citation when none is the seed", () => {
    const d = dossier(undefined, "no sentence end here", 77);
    const first = d.citations[0];
    if (!first) throw new Error("fixture has no citation");
    d.citations = [{ ...first, role: "related" }];
    expect(dossierDescription(d)).toBe("Cited to Wikipedia revision 77.");
  });
});

describe("dossierJsonLd", () => {
  it("builds an Article on the pinned revision and a three-step breadcrumb", () => {
    const d = dossier("Short", "Lead.", 42);
    expect(dossierJsonLd(d, "/t/ada", "Ada", "Short")).toMatchObject({
      "@graph": [
        {
          "@type": "Article",
          url: "https://wke.piotrkrzysztof.dev/t/ada",
          isBasedOn: d.citations[0]?.pin.permalink,
        },
        {
          "@type": "BreadcrumbList",
          itemListElement: [{ name: "Home" }, { name: "Dossiers" }, { name: "Ada" }],
        },
      ],
    });
  });
});

const meta = (attr: string, key: string) =>
  document.head.querySelector(`meta[${attr}="${key}"]`)?.getAttribute("content") ?? null;
const canonical = () => document.head.querySelector('link[rel="canonical"]');

describe("useSeo", () => {
  it("drops the article-only tags when the next page does not set them", () => {
    const article: SeoInput = {
      title: "Ada",
      path: "/t/ada",
      type: "article",
      modified: "2026-01-01T00:00:00Z",
    };
    const { rerender } = renderHook((props) => useSeo(props), { initialProps: article });
    expect(meta("property", "article:modified_time")).toBe("2026-01-01T00:00:00Z");
    expect(meta("property", "og:url")).toBe("https://wke.piotrkrzysztof.dev/t/ada");
    rerender({ title: "Home", path: "/", type: "website", modified: undefined });
    expect(meta("property", "article:modified_time")).toBeNull();
    expect(meta("property", "og:url")).toBe("https://wke.piotrkrzysztof.dev/");
  });

  it("gives a noindex page no canonical and removes its tags on unmount", () => {
    const noindex = renderHook(() => useSeo({ title: "x", path: "/x", robots: "noindex" }));
    expect(canonical()).toBeNull();
    expect(meta("name", "robots")).toBe("noindex");
    noindex.unmount();
    const indexed = renderHook(() => useSeo({ title: "y", path: "/y" }));
    expect(canonical()?.getAttribute("href")).toBe("https://wke.piotrkrzysztof.dev/y");
    indexed.unmount();
    expect(canonical()).toBeNull();
    expect(meta("property", "og:url")).toBeNull();
  });

  it("writes the page JSON-LD and removes it on unmount", () => {
    const { unmount } = renderHook(() => useSeo({ title: "x", path: "/x", jsonLd: { a: 1 } }));
    expect(document.getElementById("ld-page")?.textContent).toBe('{"a":1}');
    unmount();
    expect(document.getElementById("ld-page")).toBeNull();
  });
});

describe("site JSON-LD", () => {
  it("describes the WebSite once, with the search action, and the home page only refers to it", () => {
    expect(homeJsonLd()).toMatchObject({
      "@type": "WebPage",
      isPartOf: { "@id": WEBSITE_JSON_LD["@id"] },
    });
    expect(WEBSITE_JSON_LD.potentialAction["@type"]).toBe("SearchAction");
  });
});
