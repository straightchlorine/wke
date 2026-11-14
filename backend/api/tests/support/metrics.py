"""Reading Prometheus samples in tests."""

from __future__ import annotations


def metric_sample(name: str, labels: dict[str, str]) -> float:
    """Read one Prometheus sample from the process-wide registry, 0.0 when absent."""
    from prometheus_client import REGISTRY

    return REGISTRY.get_sample_value(name, labels) or 0.0
