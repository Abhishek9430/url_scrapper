import os
import threading
import time
from urllib.parse import urlparse

import redis


_cooldown_lock = threading.Lock()
_blocked_domain_until_epoch: dict[str, float] = {}


def _domain(url: str) -> str:
    return urlparse(url).netloc.lower()


def _as_set(value: str) -> set[str]:
    print("hey guyz this is th value of my env var",value)
    if not value.strip():
        return set()
    return {item.strip().lower() for item in value.split(",") if item.strip()}


def render_allowlist_domains() -> set[str]:
    return _as_set(os.getenv("RENDER_ALLOWLIST_DOMAINS", ""))


def render_denylist_domains() -> set[str]:
    return _as_set(os.getenv("RENDER_DENYLIST_DOMAINS", ""))


def domain_cooldown_seconds() -> int:
    return int(os.getenv("DOMAIN_COOLDOWN_SECONDS", "300"))


def _redis_client() -> redis.Redis:
    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    return redis.Redis.from_url(redis_url, decode_responses=True)


def is_render_allowed(url: str) -> bool:
    domain = _domain(url)
    if domain in render_denylist_domains():
        return False
    allowlist = render_allowlist_domains()
    print("this is my domain",domain,allowlist)
    return domain in allowlist


def in_domain_cooldown(url: str) -> bool:
    domain = _domain(url)
    key = f"crawler_cooldown:{domain}"
    try:
        ttl = _redis_client().ttl(key)
        if ttl and ttl > 0:
            return True
    except Exception:
        pass

    now = time.time()
    with _cooldown_lock:
        expiry = _blocked_domain_until_epoch.get(domain)
        if not expiry:
            return False
        if expiry <= now:
            _blocked_domain_until_epoch.pop(domain, None)
            return False
        return True


def mark_domain_blocked(url: str) -> None:
    domain = _domain(url)
    key = f"crawler_cooldown:{domain}"
    seconds = domain_cooldown_seconds()
    try:
        _redis_client().setex(key, seconds, "1")
        return
    except Exception:
        pass

    with _cooldown_lock:
        _blocked_domain_until_epoch[domain] = time.time() + seconds


def decide_initial_tier(url: str, force_render: bool = False) -> tuple[str, str | None]:
    if in_domain_cooldown(url):
        return "blocked", "DOMAIN_COOLDOWN_ACTIVE"
    if force_render:
        if is_render_allowed(url):
            return "render", None
        return "blocked", "RENDER_NOT_ALLOWED"
    return "http", None


def should_escalate_to_render(
    url: str,
    *,
    status_code: int,
    content_type: str | None,
    html: str,
    extracted_body_text: str | None,
) -> tuple[bool, str | None]:
    if not is_render_allowed(url):
        return False, None
    if status_code != 200:
        return False, None
    if content_type and "text/html" not in content_type.lower():
        return False, None

    body_text = (extracted_body_text or "").strip()
    html_lower = (html or "").lower()
    js_markers = [
        "enable javascript",
        "javascript is required",
        "you need to enable javascript",
        "please turn javascript on",
        "noscript",
    ]
    if len(body_text) < 240 and any(marker in html_lower for marker in js_markers):
        return True, "JS_REQUIRED_LOW_CONTENT"
    return False, None
