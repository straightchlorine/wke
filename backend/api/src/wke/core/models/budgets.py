"""The token budgets a dossier is packed to."""

from __future__ import annotations

from typing import Literal, get_args

BudgetTokens = Literal[2000, 8000, 32000]
BUDGETS: tuple[BudgetTokens, ...] = get_args(BudgetTokens)
DEFAULT_BUDGET: BudgetTokens = 8000
