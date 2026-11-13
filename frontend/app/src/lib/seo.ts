import { useEffect } from "react";
import type { DossierView } from "../api/dossier";
import { leadSentence } from "./lede";

const SITE_NAME = "WKE";
const SITE_URL = "https://wke.piotrkrzysztof.dev";
const OG_IMAGE = `${SITE_URL}/og.png`;
const WEBSITE_ID = `${SITE_URL}/#website`;

/** The product pitch, used as the default meta description and in the WebSite JSON-LD. */
export const PITCH =
  "Cited context from Wikipedia for people and LLMs: pick a topic, get a dossier pinned to one revision, cut to your token budget, as Markdown, JSON or MCP.";

export interface SeoInput {
  /** Page title, before the site suffix is added. */
  title: string;
  /** Meta description; defaults to the pitch sentence. */
  description?: string;
  /** Path (with leading slash) used to build the canonical and OG URL. */
  path: string;
  /** Whether to append " - WKE" to the title. Defaults to true. */
  suffix?: boolean;
  /** Robots directive; defaults to "index,follow". A noindex page gets no canonical. */
  robots?: string;
  /** Open Graph type; defaults to "website". */
  type?: "website" | "article";
  /** ISO timestamp for article:modified_time; only meaningful for type "article". */
  modified?: string;
  /** Alt text for the share image. */
  imageAlt?: string;
  /** Structured data for this page, written to a script with id "ld-page". */
  jsonLd?: object;
}

const IMAGE_ALT = "WKE: a Wikipedia topic as a cited dossier pinned to one revision";
const LD_PAGE_ID = "ld-page";
const DESCRIPTION_MAX = 155;

function upsertMeta(attr: "name" | "property", key: string, content: string) {
  let tag = document.head.querySelector<HTMLMetaElement>(`meta[${attr}="${key}"]`);
  if (!tag) {
    tag = document.createElement("meta");
    tag.setAttribute(attr, key);
    document.head.appendChild(tag);
  }
  tag.setAttribute("content", content);
}

function removeMeta(attr: "name" | "property", key: string) {
  document.head.querySelector(`meta[${attr}="${key}"]`)?.remove();
}

function upsertLink(rel: string, href: string) {
  let tag = document.head.querySelector<HTMLLinkElement>(`link[rel="${rel}"]`);
  if (!tag) {
    tag = document.createElement("link");
    tag.setAttribute("rel", rel);
    document.head.appendChild(tag);
  }
  tag.setAttribute("href", href);
}

function removeLink(rel: string) {
  document.head.querySelector(`link[rel="${rel}"]`)?.remove();
}

/**
 * Shortens text to at most `max` characters, cutting at a word boundary and ending in "..." when it
 * was cut.
 */
export function clipDescription(text: string, max: number = DESCRIPTION_MAX): string {
  const flat = text.replace(/\s+/g, " ").trim();
  if (flat.length <= max) {
    return flat;
  }
  const room = flat.slice(0, max - 3);
  const cut = room.lastIndexOf(" ");
  return `${(cut > 0 ? room.slice(0, cut) : room).replace(/[\s,;:.-]+$/, "")}...`;
}

/**
 * Returns a meta description for a dossier: the Wikipedia short description, else the lead's first
 * sentence, else a fixed line that names the pinned revision when there is one.
 */
export function dossierDescription(dossier: DossierView): string {
  const short = dossier.topic.description?.trim();
  if (short) {
    return clipDescription(short);
  }
  const lead = leadSentence(dossier);
  if (lead) {
    return clipDescription(lead);
  }
  const rev =
    dossier.citations.find((c) => c.role === "seed")?.pin.rev_id ??
    dossier.citations[0]?.pin.rev_id;
  return rev == null
    ? "A Wikipedia topic as a dossier: cited, pinned to one revision."
    : `Cited to Wikipedia revision ${rev}.`;
}

/**
 * Sets the page's title, meta tags, canonical link and JSON-LD in effects, and removes the optional
 * ones when the page unmounts or stops setting them.
 */
export function useSeo({
  title,
  description = PITCH,
  path,
  suffix = true,
  robots = "index,follow",
  type = "website",
  modified,
  imageAlt = IMAGE_ALT,
  jsonLd,
}: SeoInput) {
  useEffect(() => {
    const fullTitle = suffix ? `${title} - ${SITE_NAME}` : title;
    const url = `${SITE_URL}${path}`;
    const indexable = !robots.includes("noindex");

    document.title = fullTitle;
    upsertMeta("name", "description", description);
    upsertMeta("name", "robots", robots);
    upsertMeta("property", "og:type", type);
    upsertMeta("property", "og:site_name", SITE_NAME);
    upsertMeta("property", "og:locale", "en_US");
    upsertMeta("property", "og:title", fullTitle);
    upsertMeta("property", "og:description", description);
    upsertMeta("property", "og:image", OG_IMAGE);
    upsertMeta("property", "og:image:width", "1200");
    upsertMeta("property", "og:image:height", "630");
    upsertMeta("property", "og:image:alt", imageAlt);
    upsertMeta("name", "twitter:card", "summary_large_image");
    upsertMeta("name", "twitter:title", fullTitle);
    upsertMeta("name", "twitter:description", description);
    upsertMeta("name", "twitter:image", OG_IMAGE);
    upsertMeta("name", "twitter:image:alt", imageAlt);
    if (indexable) {
      upsertMeta("property", "og:url", url);
      upsertLink("canonical", url);
    }
    if (type === "article" && modified) {
      upsertMeta("property", "article:modified_time", modified);
    }
    return () => {
      removeMeta("property", "og:url");
      removeMeta("property", "article:modified_time");
      removeLink("canonical");
    };
  }, [title, description, path, suffix, robots, type, modified, imageAlt]);

  const ld = jsonLd === undefined ? null : JSON.stringify(jsonLd);
  useEffect(() => {
    if (ld === null) {
      return undefined;
    }
    const script = document.createElement("script");
    script.type = "application/ld+json";
    script.id = LD_PAGE_ID;
    script.textContent = ld;
    document.head.appendChild(script);
    return () => script.remove();
  }, [ld]);
}

/** Builds the home page's JSON-LD: a WebPage that belongs to the site-wide WebSite node. */
export function homeJsonLd(): object {
  return {
    "@context": "https://schema.org",
    "@type": "WebPage",
    "@id": `${SITE_URL}/#webpage`,
    url: `${SITE_URL}/`,
    isPartOf: { "@id": WEBSITE_ID },
  };
}

/**
 * Builds a dossier's JSON-LD: an Article based on the pinned revision, plus a breadcrumb of Home,
 * Dossiers and the title.
 */
export function dossierJsonLd(
  dossier: DossierView,
  path: string,
  headline: string,
  description: string,
): object {
  const url = `${SITE_URL}${path}`;
  const pin = dossier.citations.find((c) => c.role === "seed")?.pin ?? dossier.citations[0]?.pin;
  return {
    "@context": "https://schema.org",
    "@graph": [
      {
        "@type": "Article",
        "@id": `${url}#article`,
        headline,
        description,
        url,
        mainEntityOfPage: url,
        inLanguage: "en",
        image: OG_IMAGE,
        ...(pin
          ? {
              datePublished: pin.rev_timestamp,
              dateModified: pin.rev_timestamp,
              isBasedOn: pin.permalink,
            }
          : {}),
        license: "https://creativecommons.org/licenses/by-sa/4.0/",
        isAccessibleForFree: true,
        publisher: { "@type": "Organization", name: SITE_NAME, url: `${SITE_URL}/` },
        author: { "@type": "Organization", name: "Wikipedia contributors" },
      },
      {
        "@type": "BreadcrumbList",
        itemListElement: [
          { "@type": "ListItem", position: 1, name: "Home", item: `${SITE_URL}/` },
          { "@type": "ListItem", position: 2, name: "Dossiers", item: `${SITE_URL}/t/` },
          { "@type": "ListItem", position: 3, name: headline, item: url },
        ],
      },
    ],
  };
}

/** JSON-LD WebSite object with the search action, injected once by the root layout. */
export const WEBSITE_JSON_LD = {
  "@context": "https://schema.org",
  "@type": "WebSite",
  "@id": WEBSITE_ID,
  name: SITE_NAME,
  alternateName: "Wikipedia Knowledge Explorer",
  description: PITCH,
  url: `${SITE_URL}/`,
  potentialAction: {
    "@type": "SearchAction",
    target: { "@type": "EntryPoint", urlTemplate: `${SITE_URL}/?q={search_term_string}` },
    "query-input": "required name=search_term_string",
  },
};
