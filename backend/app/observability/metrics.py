"""Minimal in-process metrics.

Deliberately dependency-free: the goal is enough signal to debug a demo
deployment (counters, error rates, latency percentiles) without pulling in a
Prometheus stack. ``/metrics`` renders this as JSON.
"""

import threading
from collections import defaultdict


class Metrics:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._counters: dict[str, int] = defaultdict(int)
        self._timings: dict[str, list[float]] = defaultdict(list)
        self._max_samples = 500

    def increment(self, name: str, value: int = 1, **labels: str) -> None:
        key = _key(name, labels)
        with self._lock:
            self._counters[key] += value

    def observe(self, name: str, milliseconds: float, **labels: str) -> None:
        key = _key(name, labels)
        with self._lock:
            samples = self._timings[key]
            samples.append(milliseconds)
            if len(samples) > self._max_samples:
                del samples[: len(samples) - self._max_samples]

    def snapshot(self) -> dict:
        with self._lock:
            counters = dict(self._counters)
            timings = {
                key: _summarize(samples)
                for key, samples in self._timings.items()
                if samples
            }
        return {"counters": counters, "latency_ms": timings}

    def reset(self) -> None:
        with self._lock:
            self._counters.clear()
            self._timings.clear()


def _key(name: str, labels: dict[str, str]) -> str:
    if not labels:
        return name
    rendered = ",".join(f"{k}={v}" for k, v in sorted(labels.items()))
    return f"{name}{{{rendered}}}"


def _summarize(samples: list[float]) -> dict:
    ordered = sorted(samples)
    count = len(ordered)
    return {
        "count": count,
        "avg": round(sum(ordered) / count, 2),
        "p50": round(ordered[int(count * 0.5) - 1 if count > 1 else 0], 2),
        "p95": round(ordered[min(count - 1, int(count * 0.95))], 2),
        "max": round(ordered[-1], 2),
    }


METRICS = Metrics()
