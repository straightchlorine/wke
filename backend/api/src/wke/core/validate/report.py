"""The result of validating a dossier view."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field


@dataclass
class ValidationReport:
    """Counts of what was checked and what failed, with one line per failure."""

    counts: Counter[str] = field(default_factory=Counter[str])
    problems: list[str] = field(default_factory=list[str])

    @property
    def ok(self) -> bool:
        """True when no check failed."""
        return not self.problems

    def fail(self, kind: str, detail: str) -> None:
        """Record one failure.

        Args:
            kind: counter name, e.g. "fragment_passages".
            detail: what failed, with enough to find it.
        """
        self.counts[kind] += 1
        self.problems.append(f"{kind}: {detail}")
