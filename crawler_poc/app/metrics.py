import os
import threading

import redis


_lock = threading.Lock()
_counters: dict[str, int] = {
    "jobs_completed_total": 0,
    "jobs_blocked_total": 0,
    "jobs_escalated_to_render_total": 0,
    "render_success_total": 0,
}
_metric_names = tuple(_counters.keys())


def _client() -> redis.Redis:
    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    return redis.Redis.from_url(redis_url, decode_responses=True)


def increment(metric_name: str) -> None:
    try:
        _client().incr(f"crawler_metric:{metric_name}")
        return
    except Exception:
        with _lock:
            _counters[metric_name] = _counters.get(metric_name, 0) + 1


def snapshot() -> dict[str, int]:
    try:
        client = _client()
        values = client.mget([f"crawler_metric:{name}" for name in _metric_names])
        return {
            name: int(value) if value is not None else 0
            for name, value in zip(_metric_names, values)
        }
    except Exception:
        with _lock:
            return dict(_counters)
