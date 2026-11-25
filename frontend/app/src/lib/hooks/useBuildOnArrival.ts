import { useState } from "react";
import { useRouterState } from "@tanstack/react-router";
import { rootNavState } from "../../routes/__root";

// Keys ("history position:slug") of the entries the app was opened on directly.
const openedDirectly = new Set<string>();

/**
 * Says whether the dossier page may request a build by itself, which it may not on the entry the app was opened on.
 * That stays so when the reader later comes back to that entry with Back or Forward.
 */
export function useBuildOnArrival(slug: string): boolean {
  const position = useRouterState({ select: (state) => state.location.state["__TSR_index"] });
  const entry = `${position}:${slug}`;
  // Runs once on mount. isInitialLoad stays true only until the app's first commit, so this
  // records the entry the app was opened on.
  useState(() => {
    if (rootNavState.isInitialLoad) {
      openedDirectly.add(entry);
    }
  });
  return !openedDirectly.has(entry);
}
