"""
bot/telegram_api.py

طبقة رقيقة فوق مكتبة python-telegram-bot.

ملاحظة معمارية مهمة:
---------------------
إصدارات python-telegram-bot الحديثة (v20+) هي مكتبة async بالكامل، ولا تدعم
Polling أصلاً بدون Application دائم — وهذا غير ممكن على Vercel Serverless لأن
كل استدعاء (Invocation) قصير العمر ومنفصل. لذلك لا نستخدم Application/Dispatcher
هنا (فهو مصمم لعملية طويلة العمر تدير event loop خاص بها)، بل نستخدم كائن
telegram.Bot مباشرة: نُنشئه، نستدعي initialize()، ننفذ العملية، ثم shutdown().
هذا هو الأسلوب الموصى به من نفس المكتبة عند تشغيلها داخل بيئة Serverless/Webhook
بدون Application، ويحقق طلبك باستخدام python-telegram-bot و Webhook بدل Polling.
"""

import html

from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode

from bot.config import BOT_TOKEN


def escape_html(text: str) -> str:
    """تهريب آمن للنصوص القادمة من مصادر خارجية قبل إرسالها بصيغة HTML."""
    if not text:
        return ""
    return html.escape(text, quote=False)


def get_bot() -> Bot:
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN غير مضبوط في متغيرات البيئة.")
    return Bot(token=BOT_TOKEN)


async def send_message(bot: Bot, chat_id, text, reply_markup=None,
                        parse_mode=ParseMode.HTML, disable_preview=True):
    return await bot.send_message(
        chat_id=chat_id,
        text=text,
        reply_markup=reply_markup,
        parse_mode=parse_mode,
        disable_web_page_preview=disable_preview,
    )


async def send_photo(bot: Bot, chat_id, photo_url, caption, reply_markup=None,
                      parse_mode=ParseMode.HTML):
    return await bot.send_photo(
        chat_id=chat_id,
        photo=photo_url,
        caption=caption,
        reply_markup=reply_markup,
        parse_mode=parse_mode,
    )


async def edit_message(bot: Bot, chat_id, message_id, text, reply_markup=None,
                        parse_mode=ParseMode.HTML):
    return await bot.edit_message_text(
        chat_id=chat_id,
        message_id=message_id,
        text=text,
        reply_markup=reply_markup,
        parse_mode=parse_mode,
        disable_web_page_preview=True,
    )


async def answer_callback(bot: Bot, callback_query_id, text=None, show_alert=False):
    await bot.answer_callback_query(
        callback_query_id=callback_query_id, text=text, show_alert=show_alert
    )


# ------------------------------------------------------------------
# لوحات المفاتيح (Inline Keyboards)
# ------------------------------------------------------------------
def kb_main_menu():
    from bot.config import MAIN_MENU_CATEGORIES
    rows = []
    cat_row = []
    for key, label in MAIN_MENU_CATEGORIES:
        cat_row.append(InlineKeyboardButton(label, callback_data=f"cat:{key}"))
        if len(cat_row) == 2:
            rows.append(cat_row)
            cat_row = []
    if cat_row:
        rows.append(cat_row)

    rows.append([
        InlineKeyboardButton("⚙️ المصادر", callback_data="menu:sources"),
        InlineKeyboardButton("🤖 إعدادات الذكاء الاصطناعي", callback_data="menu:ai_settings"),
    ])
    rows.append([
        InlineKeyboardButton("📢 القنوات", callback_data="menu:channels"),
        InlineKeyboardButton("📊 الإحصائيات", callback_data="menu:stats"),
    ])
    rows.append([
        InlineKeyboardButton("▶️ تشغيل النشر", callback_data="pub:on"),
        InlineKeyboardButton("⏸ إيقاف النشر", callback_data="pub:off"),
    ])
    return InlineKeyboardMarkup(rows)


def kb_back(target="menu:main"):
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("🔙 رجوع", callback_data=target)]]
    )


def kb_sources_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ إضافة مصدر", callback_data="src:add")],
        [InlineKeyboardButton("📋 عرض المصادر", callback_data="src:list")],
        [InlineKeyboardButton("🗑 حذف مصدر", callback_data="src:delete_menu")],
        [InlineKeyboardButton("🔄 اختبار مصدر", callback_data="src:test_menu")],
        [InlineKeyboardButton("🔙 رجوع", callback_data="menu:main")],
    ])


def kb_channels_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ إضافة قناة", callback_data="chan:add")],
        [InlineKeyboardButton("📋 عرض القنوات", callback_data="chan:list")],
        [InlineKeyboardButton("🗑 حذف قناة", callback_data="chan:delete_menu")],
        [InlineKeyboardButton("⭐ اختيار القناة الافتراضية", callback_data="chan:default_menu")],
        [InlineKeyboardButton("🔙 رجوع", callback_data="menu:main")],
    ])


def kb_categories_for_add(prefix: str):
    from bot.config import CATEGORIES
    rows = []
    row = []
    for key, label in CATEGORIES.items():
        row.append(InlineKeyboardButton(label, callback_data=f"{prefix}:{key}"))
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append([InlineKeyboardButton("🔙 رجوع", callback_data="menu:sources")])
    return InlineKeyboardMarkup(rows)


def kb_list_with_delete(items, prefix, back_target):
    """items: list of (id_or_key, label)"""
    rows = [[InlineKeyboardButton(label, callback_data=f"{prefix}:{key}")]
            for key, label in items]
    rows.append([InlineKeyboardButton("🔙 رجوع", callback_data=back_target)])
    return InlineKeyboardMarkup(rows)


def kb_approval(article_id: int):
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ نشر", callback_data=f"art:approve:{article_id}"),
            InlineKeyboardButton("❌ رفض", callback_data=f"art:reject:{article_id}"),
        ],
        [
            InlineKeyboardButton("✏️ تعديل", callback_data=f"art:edit:{article_id}"),
            InlineKeyboardButton("🔄 إعادة صياغة", callback_data=f"art:regen:{article_id}"),
        ],
    ])


def kb_ai_settings_menu(current):
    mode_label = "🤖 تلقائي" if current.get("publish_mode") == "auto" else "👤 موافقة يدوية"
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(f"وضع النشر الحالي: {mode_label} (اضغط للتبديل)",
                               callback_data="aiset:toggle_mode")],
        [InlineKeyboardButton(
            f"الحد الأدنى للتقييم: {current.get('min_score')} (تعديل)",
            callback_data="aiset:set_min_score")],
        [InlineKeyboardButton(
            f"عدد الأخبار اليومية: {current.get('daily_limit')} (تعديل)",
            callback_data="aiset:set_daily_limit")],
        [InlineKeyboardButton(
            f"الفاصل بين المنشورات (دقيقة): {current.get('interval_minutes')} (تعديل)",
            callback_data="aiset:set_interval")],
        [InlineKeyboardButton(
            f"إظهار المصدر: {'✅' if current.get('show_source')=='1' else '❌'}",
            callback_data="aiset:toggle_show_source")],
        [InlineKeyboardButton(
            f"إظهار الرابط: {'✅' if current.get('show_link')=='1' else '❌'}",
            callback_data="aiset:toggle_show_link")],
        [InlineKeyboardButton(
            f"تفعيل الصور: {'✅' if current.get('images_enabled')=='1' else '❌'}",
            callback_data="aiset:toggle_images")],
        [InlineKeyboardButton("✍️ تعديل توقيع القناة", callback_data="aiset:set_signature")],
        [InlineKeyboardButton("🔙 رجوع", callback_data="menu:main")],
    ])
