"""
bot/sources.py
جلب المقالات من مصادر RSS/Atom.
"""

import time
from datetime import datetime, timezone

import feedparser

from bot.database import compute_hash


def fetch_source_entries(url: str, limit: int = 5):
    """
    يجلب أحدث عناصر من رابط RSS/Atom ويعيدها كقائمة قواميس موحّدة الشكل.
    يرفع استثناء إذا تعذّر الوصول للمصدر أو كان الرد غير صالح، ليتم
    التقاطه في المستدعي (لكي لا يوقف فشل مصدر واحد بقية المصادر).
    """
    parsed = feedparser.parse(url)

    if parsed.bozo and not getattr(parsed, "entries", None):
        raise ValueError(f"تعذّر تحليل المصدر: {getattr(parsed, 'bozo_exception', 'unknown error')}")

    entries = []
    for entry in parsed.entries[:limit]:
        title = getattr(entry, "title", "").strip()
        link = getattr(entry, "link", "").strip()
        if not title or not link:
            continue

        description = ""
        if hasattr(entry, "summary"):
            description = entry.summary
        elif hasattr(entry, "description"):
            description = entry.description

        guid = getattr(entry, "id", None) or getattr(entry, "guid", None) or link

        published_at = None
        if getattr(entry, "published_parsed", None):
            try:
                published_at = datetime.fromtimestamp(
                    time.mktime(entry.published_parsed), tz=timezone.utc
                )
            except Exception:
                published_at = None

        image_url = _extract_image(entry)

        entries.append({
            "title": title,
            "link": link,
            "description": _strip_html(description)[:2000],
            "guid": guid,
            "published_at": published_at,
            "image_url": image_url,
            "hash": compute_hash(link, title),
        })

    return entries


def _extract_image(entry) -> str:
    # media_content (Media RSS)
    media = getattr(entry, "media_content", None)
    if media:
        for m in media:
            if m.get("url"):
                return m["url"]

    # media_thumbnail
    thumb = getattr(entry, "media_thumbnail", None)
    if thumb:
        for t in thumb:
            if t.get("url"):
                return t["url"]

    # enclosures (صور مرفقة كـ Podcast/Enclosure)
    for enc in getattr(entry, "enclosures", []) or []:
        enc_type = enc.get("type", "")
        if enc_type.startswith("image/") and enc.get("href"):
            return enc["href"]

    return ""


def _strip_html(raw: str) -> str:
    """إزالة وسوم HTML البسيطة من ملخص RSS بدون الاعتماد على مكتبة خارجية إضافية."""
    if not raw:
        return ""
    import re
    text = re.sub(r"<[^>]+>", " ", raw)
    text = re.sub(r"\s+", " ", text)
    return text.strip()
