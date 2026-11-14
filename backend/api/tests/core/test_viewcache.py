"""ViewCache entry expiry, invalidation and size bound."""

from __future__ import annotations

from wke.core.viewcache import ViewCache, current_generation, invalidate_views


def test_view_cache_expires_after_ttl_and_on_invalidate() -> None:
    now = [100.0]
    cache: ViewCache[str] = ViewCache(ttl=10.0, clock=lambda: now[0])
    cache.put("k", "v")
    assert cache.get("k") == "v"
    now[0] = 109.9
    assert cache.get("k") == "v"
    now[0] = 110.0
    assert cache.get("k") is None

    cache.put("k", "v")
    invalidate_views()
    assert cache.get("k") is None


def test_view_cache_drops_entry_computed_across_an_invalidation() -> None:
    cache: ViewCache[str] = ViewCache()
    generation = current_generation()
    invalidate_views()
    cache.put("k", "stale", generation)
    assert cache.get("k") is None


def test_a_full_cache_drops_its_oldest_entry_but_not_on_a_replace() -> None:
    cache: ViewCache[int] = ViewCache(max_entries=2)
    cache.put("a", 1)
    cache.put("b", 2)
    cache.put("b", 3)
    assert (cache.get("a"), cache.get("b")) == (1, 3)

    cache.put("c", 4)
    assert (cache.get("a"), cache.get("b"), cache.get("c")) == (None, 3, 4)
