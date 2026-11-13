import { ALWAYS_NAMED } from "./labelLayout";

/**
 * Returns the sentence that says which dots carry a name, then how to reach any other name by pointing or,
 * on a touch screen, tapping.
 * The "index" variant is for Home's graph and "related" is for the dossier page's graph.
 */
export function namesShownText(variant: "index" | "related", touch: boolean): string {
  const rule =
    variant === "index"
      ? `A name is shown for the ${ALWAYS_NAMED} most-read dots, every dot with no other close by, the most-read dot of each group, and as many more as fit.`
      : "Every dot is named, and a name crosses a line only where there is no clear space.";
  return `${rule} ${touch ? "Tap" : "Point at"} any dot for its name.`;
}
