import hashlib
import re
from bs4 import BeautifulSoup


TOPIC_KEYWORDS = {
    "ecommerce": ["buy", "price", "cart", "sale", "shipping", "product"],
    "technology": ["tech", "software", "ai", "computer", "internet", "cloud"],
    "news": ["breaking", "report", "latest", "news", "analysis", "update"],
    "outdoors": ["camp", "hiking", "trail", "outdoor", "tent", "backpack"],
    "kitchen": ["kitchen", "cook", "toaster", "appliance", "recipe", "food"],
}


def extract_page_data(html: str) -> dict:
    soup = BeautifulSoup(html, "lxml")

    title = _safe_text(soup.title.string if soup.title else None)
    meta_description = _safe_text(
        _meta_content(soup, "description")
        or _meta_property_content(soup, "og:description")
    )
    canonical_url = _safe_text(_canonical(soup))
    h1 = _safe_text(soup.h1.get_text(" ", strip=True) if soup.h1 else None)

    body_text = _normalize_text(soup.get_text(" ", strip=True))
    topics = classify_topics(f"{title} {meta_description} {body_text}")

    return {
        "title": title,
        "meta_description": meta_description,
        "canonical_url": canonical_url,
        "h1": h1,
        "body_text": body_text[:30000],  # Keep PoC payload lightweight.
        "topics": topics,
        "content_hash": hashlib.sha256(body_text.encode("utf-8")).hexdigest(),
    }


def classify_topics(text: str) -> list[str]:
    text_lower = text.lower()
    scores: dict[str, int] = {}

    for topic, keywords in TOPIC_KEYWORDS.items():
        score = 0
        for keyword in keywords:
            score += len(re.findall(rf"\b{re.escape(keyword)}\b", text_lower))
        if score > 0:
            scores[topic] = score

    if not scores:
        return ["general"]

    sorted_topics = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    return [topic for topic, _ in sorted_topics[:5]]


def _normalize_text(value: str | None) -> str:
    if not value:
        return ""
    return re.sub(r"\s+", " ", value).strip()


def _safe_text(value: str | None) -> str | None:
    if not value:
        return None
    normalized = _normalize_text(value)
    return normalized if normalized else None


def _meta_content(soup: BeautifulSoup, name: str) -> str | None:
    tag = soup.find("meta", attrs={"name": name})
    if not tag:
        return None
    return tag.get("content")


def _meta_property_content(soup: BeautifulSoup, prop: str) -> str | None:
    tag = soup.find("meta", attrs={"property": prop})
    if not tag:
        return None
    return tag.get("content")


def _canonical(soup: BeautifulSoup) -> str | None:
    tag = soup.find("link", attrs={"rel": "canonical"})
    if not tag:
        return None
    return tag.get("href")
