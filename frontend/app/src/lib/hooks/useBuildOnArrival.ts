import { useState } from "react";
import { useRouterState } from "@tanstack/react-router";
import { rootNavState } from "../../routes/__root";

// History entries (position and slug) of dossier pages that were the app's first page.
const openedDirectly = new Set<string>();

/**
 * Says whether the dossier page may request the build of an unbuilt title by itself.
 * That is false for the history entry the app was opened on, and also when the reader comes back
 * to it later by Back or Forward, so a crawler or a pasted link never starts a build.
 */
export function useBuildOnArrival(slug: string): boolean {
  const position = useRouterState({ select: (state) => state.location.state["__TSR_index"] });
  const entry = `${position}:${slug}`;
  // Read once on the first render, because the app's first commit flips the flag.
  useState(() => {
    if (rootNavState.isInitialLoad) {
      openedDirectly.add(entry);
    }
  });
  return !openedDirectly.has(entry);
}
