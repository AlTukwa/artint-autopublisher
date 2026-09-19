"""
bot/filters.py
منع التكرار وفلترة المحتوى حسب التقييم.
"""

from bot import database as db


def is_duplicate(hash_value: str) -> bool:
    return db.article_exists(hash_value)


def passes_score_threshold(score: int) -> bool:
    min_score = int(db.get_setting("min_score", "60"))
    return score >= min_score


def can_publish_now() -> tuple:
    """
    يتحقق من حدَّي: الفاصل الزمني بين المنشورات، والحد اليومي الأقصى.
    يعيد (True/False, سبب إن كان مرفوضًا).
    """
    interval_minutes = int(db.get_setting("interval_minutes", "30"))
    daily_limit = int(db.get_setting("daily_limit", "20"))

    if db.count_articles_published_since(interval_minutes * 60) > 0:
        return False, "لم يمر الفاصل الزمني المطلوب بين المنشورات بعد."

    if db.count_articles_published_today() >= daily_limit:
        return False, "تم بلوغ الحد الأقصى لعدد المنشورات اليوم."

    return True, ""


def publishing_enabled() -> bool:
    return db.get_setting("publishing_enabled", "1") == "1"
