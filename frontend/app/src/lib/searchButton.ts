import type { DossierState } from "./dossierState";

/** Returns "Open" when the highlighted suggestion has a dossier, and "Build" otherwise. */
export function searchButtonLabel(state: DossierState | null): "Open" | "Build" {
  return state != null && state !== "none" ? "Open" : "Build";
}

/**
 * Returns "not built yet, <key> builds it", where the key is "tap" on a touch screen and "Enter" on
 * a keyboard device.
 */
export function notBuiltHint(input: "keyboard" | "touch"): string {
  const verb = input === "touch" ? "tap" : "Enter";
  return `not built yet, ${verb} builds it`;
}

/**
 * Returns the build hint without the "not built yet" part, for rows whose chip already says the
 * title is not built.
 */
export function buildVerbHint(input: "keyboard" | "touch"): string {
  return `${input === "touch" ? "tap" : "Enter"} builds it`;
}
