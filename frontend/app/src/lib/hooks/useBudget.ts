import { useCallback, useState } from "react";
import { parseBudget, type Budget } from "../budget";

const STORAGE_KEY = "wke-budget";

/** Returns the stored raw value, or null when nothing is stored or storage cannot be read. */
function readRaw(): string | null {
  try {
    return window.localStorage.getItem(STORAGE_KEY);
  } catch {
    return null;
  }
}

function writeRaw(budget: Budget) {
  try {
    window.localStorage.setItem(STORAGE_KEY, String(budget));
  } catch {
    // Storage is unavailable or full: the choice is simply not remembered.
  }
}

/** Returns the stored token budget, or the default one, without subscribing a component to it. */
export function readStoredBudget(): Budget {
  return parseBudget(readRaw());
}

/**
 * Resolves the token budget from the `?budget=` search param, else localStorage, else the default,
 * and stores every change. Changes go to the route's `setSearchBudget` when given, otherwise straight to the URL with
 * `history.replaceState`.
 */
export function useBudget(
  searchBudget?: unknown,
  setSearchBudget?: (next: Budget) => void,
): [Budget, (next: Budget) => void] {
  const [budget, setBudgetState] = useState<Budget>(() =>
    searchBudget !== undefined ? parseBudget(searchBudget) : readStoredBudget(),
  );

  const setBudget = useCallback(
    (next: Budget) => {
      writeRaw(next);
      if (setSearchBudget) {
        setSearchBudget(next);
        return;
      }
      setBudgetState(next);
      const url = new URL(window.location.href);
      url.searchParams.set("budget", String(next));
      window.history.replaceState(window.history.state, "", url);
    },
    [setSearchBudget],
  );

  // With a route setter and a `?budget=` value, the route's value wins over local state.
  // Local state would go stale when the URL changes under a mounted component, for example on back navigation.
  const resolved =
    setSearchBudget && searchBudget !== undefined ? parseBudget(searchBudget) : budget;

  return [resolved, setBudget];
}
