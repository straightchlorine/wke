import { useCallback } from "react";
import { useNavigate } from "@tanstack/react-router";
import type { Budget } from "../budget";

/** Returns a function that opens the dossier route for a slug at the given budget. */
export function useOpenDossier(budget: Budget): (slug: string) => void {
  const navigate = useNavigate();
  return useCallback(
    (slug) => void navigate({ to: "/t/$slug", params: { slug }, search: { budget } }),
    [navigate, budget],
  );
}
