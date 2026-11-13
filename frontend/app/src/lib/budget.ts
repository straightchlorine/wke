// The only place the budgets and their aliases are written out.
const ALIAS_BY_BUDGET = { 2000: "2k", 8000: "8k", 32000: "32k" } as const;

export type Budget = keyof typeof ALIAS_BY_BUDGET;
export type BudgetAlias = (typeof ALIAS_BY_BUDGET)[Budget];
export type BudgetSegmentValue = `${Budget}`;

const isBudget = (n: unknown): n is Budget => typeof n === "number" && n in ALIAS_BY_BUDGET;

const BUDGETS = Object.keys(ALIAS_BY_BUDGET).map(Number).filter(isBudget);

const DEFAULT_BUDGET: Budget = 8000;

/**
 * Returns the short alias, such as "8k", that labels a Budget in page text and download file names.
 */
export function budgetAlias(budget: Budget): BudgetAlias {
  return ALIAS_BY_BUDGET[budget];
}

/** Returns the string value the Segmented control uses for a Budget. */
export function budgetToSegmentValue(budget: Budget): BudgetSegmentValue {
  return `${budget}`;
}

/** The options of the budget Segmented control. */
export const BUDGET_OPTIONS: { value: BudgetSegmentValue; label: string }[] = BUDGETS.map(
  (budget) => ({ value: budgetToSegmentValue(budget), label: budgetAlias(budget) }),
);

const ALIASES = BUDGETS.map(budgetAlias);
const LARGEST_ALIAS = ALIASES.at(-1);
const ALIASES_WITH_OR = `${ALIASES.slice(0, -1).join(", ")} or ${LARGEST_ALIAS}`;

/** Tooltip text for the "Fits in" chip and column header. */
export const FITS_IN_HELP = `The smallest token budget that holds the whole dossier: ${ALIASES_WITH_OR}. ${LARGEST_ALIAS} also marks dossiers that do not fit even at ${LARGEST_ALIAS}.`;

/**
 * Tooltip text for the token budget control on the dossier page. The sentence about the number keys
 * is left out on a touch screen.
 */
export function dossierBudgetHelp(estimator: string, coarsePointer: boolean): string {
  const base = `Tokens the dossier may use. Estimated with ${estimator} (characters divided by 4). Real tokenizers usually count 12 to 20 percent fewer.`;
  return coarsePointer ? base : `${base} Keys 1, 2, 3 pick ${ALIASES.join(", ")}.`;
}

/**
 * Tooltip text for the token budget control on Home. The sentence about the number keys is left out
 * on a touch screen.
 */
export function homeBudgetHelp(coarsePointer: boolean): string {
  const choice = `${ALIASES_WITH_OR} tokens. A larger budget includes more sections.`;
  return coarsePointer ? `Pick ${choice}` : `Keys 1, 2, 3 pick ${choice}`;
}

/**
 * Parses a ?budget= search param into a Budget. It accepts a budget as a number, as a numeric
 * string or as an alias such as "8k", and anything else gives DEFAULT_BUDGET.
 */
export function parseBudget(raw: unknown): Budget {
  if (isBudget(raw)) {
    return raw;
  }
  if (typeof raw === "string") {
    const byAlias = BUDGETS.find((budget) => budgetAlias(budget) === raw.toLowerCase());
    if (byAlias !== undefined) {
      return byAlias;
    }
    const asNumber = Number(raw);
    if (isBudget(asNumber)) {
      return asNumber;
    }
  }
  return DEFAULT_BUDGET;
}
