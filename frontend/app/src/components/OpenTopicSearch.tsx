import { useState } from "react";
import { useNavigate } from "@tanstack/react-router";
import { slugify } from "../lib/slug";
import { readStoredBudget } from "../lib/hooks/useBudget";
import { SearchCombobox } from "./SearchCombobox";
import { Button } from "./Button";
import type { DossierState } from "../lib/dossierState";
import { searchButtonLabel } from "../lib/searchButton";

/**
 * The topic search of the not-found pages: a combobox and a submit button.
 * The button says Open when the highlighted suggestion has a dossier or one is being built, and Build otherwise.
 * A typed or picked title goes to its dossier route, which opens the stored dossier or builds one.
 */
export function OpenTopicSearch({ className = "" }: { className?: string }) {
  const navigate = useNavigate();
  const [search, setSearch] = useState("");
  const [activeState, setActiveState] = useState<DossierState | null>(null);

  function open(title: string) {
    const trimmed = title.trim();
    if (!trimmed) {
      return;
    }
    void navigate({
      to: "/t/$slug",
      params: { slug: slugify(trimmed) },
      search: { budget: readStoredBudget() },
    });
  }

  return (
    <form
      className={`flex h-11 gap-x-2 ${className}`}
      onSubmit={(event) => {
        event.preventDefault();
        open(search);
      }}
    >
      <SearchCombobox
        value={search}
        onChange={setSearch}
        onPick={(title) => {
          setSearch(title);
          open(title);
        }}
        placeholder="Search for a topic"
        ariaLabel="Search for a topic"
        onActiveStateChange={setActiveState}
      />
      <Button type="submit" variant="primary" className="h-11!">
        {searchButtonLabel(activeState)}
      </Button>
    </form>
  );
}
