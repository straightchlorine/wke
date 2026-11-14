"""Short-lived in-process cache for the assembled list and trending views.

A cache entry lives for `VIEW_CACHE_TTL_SECONDS` or until `invalidate_views`
bumps the process-wide generation, whichever comes first.

The generation is shared only by code running in the same process,
as when the API runs the worker itself.
Where the worker runs as a separate process, a build finishing there cannot
invalidate the API's cache, and the TTL is the real staleness bound.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Hashable

VIEW_CACHE_TTL_SECONDS = 10.0

_generation = 0


def invalidate_views() -> None:
    """Drop every cached view in this process (a build finished or a refresh began)."""
    global _generation
    _generation += 1


class ViewCache[T]:
    """Tiny TTL cache keyed by hashable params, dropped on `invalidate_views`."""

    def __init__(
        self,
        ttl: float = VIEW_CACHE_TTL_SECONDS,
        clock: Callable[[], float] = time.monotonic,
        max_entries: int = 64,
    ) -> None:
        self._ttl = ttl
        self._clock = clock
        self._max_entries = max_entries
        self._entries: dict[Hashable, tuple[float, int, T]] = {}

    def get(self, key: Hashable) -> T | None:
        """Return the live value for key, or None if missing, expired or invalidated.

        Args:
            key: cache key.

        Returns:
            T | None: the cached value, or None on a miss.
        """
        entry = self._entries.get(key)
        if entry is None:
            return None
        expires, generation, value = entry
        if generation != _generation or self._clock() >= expires:
            del self._entries[key]
            return None
        return value

    def put(self, key: Hashable, value: T, generation: int | None = None) -> None:
        """Store value under key for one TTL.

        Args:
            key: cache key.
            value: the value to keep.
            generation: the generation read before the value was computed;
                a build finishing mid-computation makes the entry dead on
                arrival. Defaults to the current generation.
        """
        # full: drop the oldest entry, unless this put only replaces a key.
        if key not in self._entries and len(self._entries) >= self._max_entries:
            self._entries.pop(next(iter(self._entries)))
        self._entries[key] = (
            self._clock() + self._ttl,
            _generation if generation is None else generation,
            value,
        )


def current_generation() -> int:
    """Return the process-wide invalidation generation.

    Returns:
        int: bumped by every `invalidate_views` call.
    """
    return _generation
