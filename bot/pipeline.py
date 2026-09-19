"""
bot/pipeline.py

المسار الكامل المطلوب في المواصفات:
RSS -> جلب المقال -> منع التكرار -> AI -> فلترة -> إعادة صياغة عربية ->
موافقة المشرف أو نشر تلقائي -> Telegram Channel

يُستدعى هذا الملف من api/cron.py فقط (وليس من webhook.py) لأن معالجة
RSS + الذكاء الاصطناعي قد تستغرق وقتًا أطول من محادثة تليجرام العادية.
"""

from telegram import Bot

from bot import ai, database as db, filters, publisher
from bot.sources import fetch_source_entries
from bot.telegram_api import kb_approval, send_message


async def run_cycle(bot: Bot):
    """
    ينفذ دورة واحدة كاملة: جلب من كل المصادر النشطة، ثم معالجة الطابور
    بالذكاء الاصطناعي، ثم محاولة نشر ما يستحق النشر مع احترام الجدولة.
    يعيد ملخصًا نصيًا للعملية (يُستخدم في استجابة GET /api/cron).
    """
    if filters.publishing_enabled() is False:
        return {"status": "skipped", "reason": "publishing_enabled=0"}

    summary = {"fetched": 0, "duplicates": 0, "ai_processed": 0,
               "ai_errors": 0, "published": 0, "queued_for_approval": 0,
               "source_errors": []}

    _fetch_new_articles(summary)
    _process_new_articles_with_ai(summary)
    await _try_publish_pending(bot, summary)

    db.set_setting("last_scan_at", _now_str())
    return {"status": "ok", **summary}


def _now_str():
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def _fetch_new_articles(summary: dict):
    sources = db.list_sources(active_only=True)
    per_source_limit = int(db.get_setting("articles_per_source_per_run", "5"))

    for source in sources:
        try:
            entries = fetch_source_entries(source["url"], limit=per_source_limit)
            db.mark_source_checked(source["id"])
        except Exception as e:
            db.mark_source_checked(source["id"], error=str(e))
            db.bump_counter("error_count")
            db.log("error", "sources", f"فشل جلب المصدر '{source['name']}': {e}")
            summary["source_errors"].append(source["name"])
            continue

        for entry in entries:
            summary["fetched"] += 1
            if filters.is_duplicate(entry["hash"]):
                summary["duplicates"] += 1
                continue
            db.insert_article(
                source_id=source["id"],
                guid=entry["guid"],
                link=entry["link"],
                hash_value=entry["hash"],
                category=source["category"],
                raw_title=entry["title"],
                raw_description=entry["description"],
                image_url=entry["image_url"],
            )


def _process_new_articles_with_ai(summary: dict):
    new_articles = db.list_articles_by_status("new", limit=20)
    min_score = int(db.get_setting("min_score", "60"))

    for article in new_articles:
        db.bump_counter("checked_count")
        summary["ai_processed"] += 1

        source = db.get_source(article["source_id"]) if article["source_id"] else None
        source_name = source["name"] if source else "غير معروف"

        try:
            result = ai.process_article(
                title=article["raw_title"],
                description=article["raw_description"],
                source_name=source_name,
                category_hint=article["category"],
            )
        except ai.AIError as e:
            summary["ai_errors"] += 1
            db.bump_counter("error_count")
            db.log("error", "ai", f"فشل تحليل المقال {article['id']}: {e}")
            db.update_article_status(article["id"], "ai_failed")
            continue

        if not result["publish"] or result["score"] < min_score:
            db.update_article_ai(article["id"], result["title_ar"], result["summary_ar"],
                                  result["score"], "rejected", result["category"])
            db.bump_counter("rejected_count")
            continue

        db.bump_counter("approved_count")
        publish_mode = db.get_setting("publish_mode", "manual")
        next_status = "approved" if publish_mode == "auto" else "pending_approval"
        db.update_article_ai(article["id"], result["title_ar"], result["summary_ar"],
                              result["score"], next_status, result["category"])


async def _try_publish_pending(bot: Bot, summary: dict):
    publish_mode = db.get_setting("publish_mode", "manual")

    # وضع الموافقة اليدوية: أرسل كل خبر "pending_approval" جديد إلى المشرفين
    if publish_mode == "manual":
        pending = db.list_articles_by_status("pending_approval", limit=10)
        for article in pending:
            await _send_for_approval(bot, article)
            summary["queued_for_approval"] += 1
        return

    # وضع النشر التلقائي: انشر أقدم خبر "approved" واحد فقط إن سمحت الجدولة
    approved = db.list_articles_by_status("approved", limit=5)
    if not approved:
        return

    channel = db.get_default_channel()
    if not channel:
        db.log("warning", "publisher", "لا توجد قناة افتراضية، تعذّر النشر التلقائي.")
        return

    for article in approved:
        can_publish, reason = filters.can_publish_now()
        if not can_publish:
            break
        try:
            enriched = _enrich(article)
            await publisher.publish_article(bot, enriched, channel["chat_id"])
            db.update_article_status(article["id"], "published")
            db.bump_counter("published_count")
            summary["published"] += 1
        except Exception as e:
            db.bump_counter("error_count")
            db.log("error", "publisher", f"فشل النشر التلقائي للمقال {article['id']}: {e}")
            db.update_article_status(article["id"], "publish_failed")


async def _send_for_approval(bot: Bot, article: dict):
    from bot.config import ADMIN_IDS
    enriched = _enrich(article)
    text = "📰 <b>خبر جديد بانتظار الموافقة</b>\n\n" + publisher.format_post(enriched)
    # نغيّر الحالة فورًا حتى لا يُعاد إرسال نفس الخبر في الدورة التالية
    db.update_article_status(article["id"], "awaiting_approval")
    for admin_id in ADMIN_IDS:
        try:
            await send_message(bot, admin_id, text, kb_approval(article["id"]))
        except Exception as e:
            db.log("error", "handlers", f"تعذّر إرسال الخبر {article['id']} للمشرف {admin_id}: {e}")


def _enrich(article: dict) -> dict:
    enriched = dict(article)
    source = db.get_source(article["source_id"]) if article.get("source_id") else None
    enriched["source_name"] = source["name"] if source else ""
    return enriched
