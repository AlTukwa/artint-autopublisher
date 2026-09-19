"""
bot/publisher.py
تنسيق منشور Telegram وإرساله إلى القناة.
"""

from telegram import Bot

from bot import database as db
from bot.config import CATEGORIES
from bot.telegram_api import escape_html, send_message, send_photo

_CATEGORY_EMOJI = {
    "technology": "💻", "news": "📰", "sports": "⚽", "gaming": "🎮",
    "ai": "🤖", "android": "📱", "apple": "🍎", "crypto": "💰",
}


def format_post(article: dict) -> str:
    settings = db.get_all_settings()
    emoji = _CATEGORY_EMOJI.get(article.get("category"), "📰")

    title = escape_html(article.get("ai_title") or article.get("raw_title") or "")
    summary = escape_html(article.get("ai_summary") or "")

    lines = [f"{emoji} <b>{title}</b>", "", summary]

    if settings.get("show_source", "1") == "1" and article.get("source_name"):
        lines.append("")
        lines.append(f"📌 المصدر: {escape_html(article['source_name'])}")

    if settings.get("show_link", "1") == "1" and article.get("link"):
        lines.append(f'🔗 <a href="{article["link"]}">قراءة التفاصيل</a>')

    signature = settings.get("signature", "")
    if signature:
        lines.append("")
        lines.append(escape_html(signature))

    return "\n".join(lines)


async def publish_article(bot: Bot, article: dict, channel_chat_id: str) -> bool:
    """
    ينشر مقالًا واحدًا في قناة محددة. يعيد True عند النجاح.
    عند فشل الإرسال بالصورة (رابط صورة غير صالح مثلاً) يعيد المحاولة كنص فقط.
    """
    text = format_post(article)
    settings = db.get_all_settings()
    image_url = article.get("image_url")

    if settings.get("images_enabled", "1") == "1" and image_url:
        try:
            await send_photo(bot, channel_chat_id, image_url, text)
            return True
        except Exception as e:
            db.log("warning", "publisher",
                   f"فشل إرسال الصورة للمقال {article.get('id')}: {e}. سيتم الإرسال كنص.")

    await send_message(bot, channel_chat_id, text)
    return True
