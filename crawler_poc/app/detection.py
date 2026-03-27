import hashlib
from bs4 import BeautifulSoup


BLOCKED_STATUS_CODES = {403, 429}
CHALLENGE_MARKERS = [
    "access denied",
    "just a moment",
    "enable javascript",
    "captcha",
    "verify you are human",
    "cf-chl",
    "errors.edgesuite.net",
    "request unsuccessful",
]


def detect_blocking_response(status_code: int, html: str, headers: dict | None = None) -> dict | None:
    content = (html or "").lower()
    header_str = str(headers or {}).lower()

    if status_code == 429:
        return {
            "reason_code": "HTTP_429",
            "reason_message": "Rate limited by target site.",
        }

    if status_code == 403:
        if _contains_challenge_marker(content):
            return {
                "reason_code": "BLOCKED_CHALLENGE_PAGE",
                "reason_message": "Blocked by anti-bot challenge page.",
            }
        return {
            "reason_code": "HTTP_403",
            "reason_message": "Access denied by target site.",
        }

    if status_code == 503 and _contains_challenge_marker(content):
        return {
            "reason_code": "BLOCKED_CHALLENGE_PAGE",
            "reason_message": "Challenge or temporary block page detected.",
        }

    waf_hint = any(hint in header_str for hint in ["cloudflare", "akamai", "datadome"])
    if waf_hint and _contains_challenge_marker(content):
        return {
            "reason_code": "BLOCKED_CHALLENGE_PAGE",
            "reason_message": "WAF challenge page detected.",
        }

    return None


def extract_blocked_snapshot(html: str) -> dict:
    soup = BeautifulSoup(html or "", "lxml")
    title = _safe_text(soup.title.string if soup.title else None)
    h1 = _safe_text(soup.h1.get_text(" ", strip=True) if soup.h1 else None)
    body_text = _safe_text(soup.get_text(" ", strip=True)) or ""
    return {
        "title": title,
        "meta_description": None,
        "canonical_url": None,
        "h1": h1,
        "body_text": body_text[:30000],
        "topics": [],
        "content_hash": hashlib.sha256(body_text.encode("utf-8")).hexdigest(),
    }


def _contains_challenge_marker(content: str) -> bool:
    return any(marker in content for marker in CHALLENGE_MARKERS)


def _safe_text(value: str | None) -> str | None:
    if not value:
        return None
    normalized = " ".join(value.split())
    return normalized if normalized else None
