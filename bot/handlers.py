"""
bot/handlers.py

نقطة التوجيه الرئيسية لتحديثات Telegram القادمة عبر Webhook.
لا يوجد هنا Application دائم من python-telegram-bot (غير ممكن على
Serverless) — بدل ذلك نحلل التحديث يدويًا (أوامر / رسائل نصية / أزرار)
ونستخدم جدول pending_actions في قاعدة البيانات لتذكّر "أين نحن" في أي
محادثة متعددة الخطوات (مثل إضافة مصدر أو قناة) بين استدعاء وآخر.
"""

from telegram import Bot, Update

from bot import ai, database as db, filters, publisher
from bot.config import ADMIN_IDS, CATEGORIES, is_admin
from bot.telegram_api import (
    answer_callback, edit_message, escape_html, kb_ai_settings_menu, kb_approval,
    kb_back, kb_categories_for_add, kb_channels_menu, kb_list_with_delete,
    kb_main_menu, kb_sources_menu, send_message,
)

NO_PERMISSION_MSG = "ليس لديك صلاحية استخدام لوحة التحكم."

WELCOME_TEXT = (
    "🤖 <b>Artint AutoPublisher</b>\n\n"
    "مرحبًا بك في نظام النشر التلقائي.\n\n"
    "اختر العملية:"
)


async def process_update(update_data: dict, bot: Bot):
    update = Update.de_json(update_data, bot)

    if update.callback_query:
        await handle_callback(update.callback_query, bot)
        return

    if update.message:
        await handle_message(update.message, bot)
        return


# ------------------------------------------------------------------
# الرسائل النصية والأوامر
# ------------------------------------------------------------------
async def handle_message(message, bot: Bot):
    user_id = message.from_user.id if message.from_user else None
    text = (message.text or "").strip()

    if not text:
        return

    if text.startswith("/"):
        await handle_command(message, bot, user_id, text)
        return

    if not is_admin(user_id):
        # لا نرد على رسائل عامة من غير المشرفين لتفادي الإزعاج
        return

    pending = db.get_pending_action(user_id)
    if pending:
        await handle_conversation_step(message, bot, user_id, text, pending)
        return

    # لا يوجد حوار مفتوح ولا أمر معروف
    await send_message(bot, message.chat_id,
                        "أرسل /start لعرض لوحة التحكم.")


async def handle_command(message, bot: Bot, user_id, text):
    command = text.split()[0].split("@")[0].lower()

    if not is_admin(user_id):
        await send_message(bot, message.chat_id, NO_PERMISSION_MSG)
        return

    if command == "/start":
        db.clear_pending_action(user_id)
        await send_message(bot, message.chat_id, WELCOME_TEXT, kb_main_menu())

    elif command == "/setup":
        await cmd_setup(message, bot)

    elif command == "/test":
        await cmd_test(message, bot)

    else:
        await send_message(bot, message.chat_id,
                            "أمر غير معروف. استخدم /start لعرض لوحة التحكم.")


async def cmd_setup(message, bot: Bot):
    channels = db.list_channels()
    sources = db.list_sources()
    settings = db.get_all_settings()

    lines = ["🛠 <b>إعداد أول مرة</b>", ""]
    lines.append(f"1️⃣ القنوات المضافة: {len(channels)}")
    lines.append(f"2️⃣ المصادر المضافة: {len(sources)}")
    lines.append(f"3️⃣ التصنيفات المتاحة: {len(CATEGORIES)} (جاهزة مسبقًا)")
    lines.append(f"4️⃣ وضع النشر الحالي: "
                 f"{'تلقائي 🤖' if settings.get('publish_mode') == 'auto' else 'موافقة يدوية 👤'}")
    lines.append(f"5️⃣ الذكاء الاصطناعي: "
                 f"{'✅ مُهيأ' if _openai_configured() else '⚠️ لم يُضبط OPENAI_API_KEY بعد'}")
    lines.append(f"6️⃣ الحد الأدنى للتقييم: {settings.get('min_score')}")
    lines.append("")
    lines.append("استخدم الأزرار أدناه لإكمال الإعداد الناقص:")

    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ إضافة قناة", callback_data="chan:add")],
        [InlineKeyboardButton("➕ إضافة مصدر", callback_data="src:add")],
        [InlineKeyboardButton("🤖 إعدادات الذكاء الاصطناعي", callback_data="menu:ai_settings")],
        [InlineKeyboardButton("🔙 القائمة الرئيسية", callback_data="menu:main")],
    ])
    await send_message(bot, message.chat_id, "\n".join(lines), kb)


def _openai_configured() -> bool:
    from bot.config import OPENAI_API_KEY
    return bool(OPENAI_API_KEY)


async def cmd_test(message, bot: Bot):
    lines = ["🔍 <b>تقرير الاختبار</b>", ""]

    # Telegram
    try:
        me = await bot.get_me()
        lines.append(f"✅ Telegram: متصل كـ @{me.username}")
    except Exception as e:
        lines.append(f"❌ Telegram: {e}")

    # Database
    try:
        db.get_all_settings()
        lines.append("✅ Database: الاتصال يعمل")
    except Exception as e:
        lines.append(f"❌ Database: {e}")

    # RSS
    sources = db.list_sources(active_only=True)
    if not sources:
        lines.append("⚠️ RSS: لا توجد مصادر مضافة بعد")
    else:
        from bot.sources import fetch_source_entries
        src = sources[0]
        try:
            entries = fetch_source_entries(src["url"], limit=1)
            lines.append(f"✅ RSS: تم جلب {len(entries)} عنصر من '{src['name']}'")
        except Exception as e:
            lines.append(f"❌ RSS ({src['name']}): {e}")

    # AI
    try:
        result = ai.process_article(
            title="اختبار الاتصال بالذكاء الاصطناعي",
            description="هذه رسالة اختبار داخلية للتأكد من عمل واجهة الذكاء الاصطناعي.",
            source_name="Artint Test",
        )
        lines.append(f"✅ AI: يعمل (تقييم تجريبي: {result['score']})")
    except Exception as e:
        lines.append(f"❌ AI: {e}")

    await send_message(bot, message.chat_id, "\n".join(lines), kb_back())


# ------------------------------------------------------------------
# خطوات المحادثة (إضافة مصدر / قناة / تعديل قيمة إعداد)
# ------------------------------------------------------------------
async def handle_conversation_step(message, bot: Bot, user_id, text, pending):
    action = pending["action"]
    data = pending["data"] or {}
    chat_id = message.chat_id

    if action == "add_source_name":
        db.set_pending_action(user_id, "add_source_url", {"name": text})
        await send_message(bot, chat_id, "الرابط:\nأرسل رابط RSS الآن.")

    elif action == "add_source_url":
        data["url"] = text
        db.set_pending_action(user_id, "add_source_category", data)
        await send_message(bot, chat_id, "اختر تصنيف المصدر:",
                            kb_categories_for_add("srccat"))

    elif action == "add_channel_id":
        channel_id = text.strip()
        title = channel_id
        try:
            chat = await bot.get_chat(channel_id)
            title = chat.title or channel_id
            try:
                member = await bot.get_chat_member(channel_id, bot.id)
                if member.status not in ("administrator", "creator"):
                    await send_message(
                        bot, chat_id,
                        "⚠️ تنبيه: البوت ليس مشرفًا في هذه القناة بعد، لن "
                        "يتمكن من النشر فيها حتى تضيفه كمشرف (Admin).")
            except Exception:
                pass
        except Exception as e:
            await send_message(bot, chat_id,
                                f"⚠️ تعذّر التحقق من القناة ({e})، سيتم حفظها كما هي.")

        db.add_channel(channel_id, title)
        db.clear_pending_action(user_id)
        await send_message(bot, chat_id, f"✅ تمت إضافة القناة: {escape_html(title)}",
                            kb_channels_menu())

    elif action == "edit_article_text":
        article_id = data.get("article_id")
        db.update_article_summary(article_id, text)
        db.clear_pending_action(user_id)
        await send_message(bot, chat_id, "✅ تم تحديث نص الخبر. أرسل /start للعودة للقائمة.")

    elif action == "set_min_score":
        await _save_numeric_setting(bot, chat_id, user_id, text, "min_score", 0, 100)

    elif action == "set_daily_limit":
        await _save_numeric_setting(bot, chat_id, user_id, text, "daily_limit", 1, 500)

    elif action == "set_interval":
        await _save_numeric_setting(bot, chat_id, user_id, text, "interval_minutes", 1, 1440)

    elif action == "set_signature":
        db.set_setting("signature", text)
        db.clear_pending_action(user_id)
        await send_message(bot, chat_id, "✅ تم حفظ التوقيع.", kb_back())

    else:
        db.clear_pending_action(user_id)


async def _save_numeric_setting(bot, chat_id, user_id, text, key, min_v, max_v):
    try:
        value = int(text.strip())
        if not (min_v <= value <= max_v):
            raise ValueError()
    except ValueError:
        await send_message(bot, chat_id,
                            f"⚠️ أرسل رقمًا صحيحًا بين {min_v} و {max_v}.")
        return
    db.set_setting(key, str(value))
    db.clear_pending_action(user_id)
    await send_message(bot, chat_id, "✅ تم الحفظ.", kb_back())


# ------------------------------------------------------------------
# الأزرار (Callback Queries)
# ------------------------------------------------------------------
async def handle_callback(cq, bot: Bot):
    user_id = cq.from_user.id
    chat_id = cq.message.chat_id
    message_id = cq.message.message_id
    data = cq.data or ""

    if not is_admin(user_id):
        await answer_callback(bot, cq.id, NO_PERMISSION_MSG, show_alert=True)
        return

    await answer_callback(bot, cq.id)

    try:
        if data == "menu:main":
            db.clear_pending_action(user_id)
            await edit_message(bot, chat_id, message_id, WELCOME_TEXT, kb_main_menu())

        elif data == "menu:sources":
            await edit_message(bot, chat_id, message_id, "⚙️ <b>إدارة المصادر</b>", kb_sources_menu())

        elif data == "menu:channels":
            await edit_message(bot, chat_id, message_id, "📢 <b>إدارة القنوات</b>", kb_channels_menu())

        elif data == "menu:ai_settings":
            settings = db.get_all_settings()
            await edit_message(bot, chat_id, message_id,
                                "🤖 <b>إعدادات الذكاء الاصطناعي والنشر</b>",
                                kb_ai_settings_menu(settings))

        elif data == "menu:stats":
            await show_stats(bot, chat_id, message_id)

        elif data.startswith("cat:"):
            await show_category_stats(bot, chat_id, message_id, data.split(":", 1)[1])

        elif data == "pub:on":
            db.set_setting("publishing_enabled", "1")
            await edit_message(bot, chat_id, message_id,
                                "▶️ تم تفعيل النشر التلقائي/الدوري.", kb_main_menu())

        elif data == "pub:off":
            db.set_setting("publishing_enabled", "0")
            await edit_message(bot, chat_id, message_id,
                                "⏸ تم إيقاف النشر مؤقتًا.", kb_main_menu())

        elif data == "src:add":
            db.set_pending_action(user_id, "add_source_name", {})
            await edit_message(bot, chat_id, message_id,
                                "اسم المصدر:\nأرسل اسم المصدر الآن.")

        elif data == "src:list":
            await list_sources_view(bot, chat_id, message_id)

        elif data == "src:delete_menu":
            await source_action_menu(bot, chat_id, message_id, "srcdel", "🗑 اختر مصدرًا لحذفه:")

        elif data == "src:test_menu":
            await source_action_menu(bot, chat_id, message_id, "srctest", "🔄 اختر مصدرًا لاختباره:")

        elif data.startswith("srccat:"):
            await finalize_add_source(bot, chat_id, message_id, user_id, data.split(":", 1)[1])

        elif data.startswith("srcdel:"):
            source_id = int(data.split(":", 1)[1])
            db.remove_source(source_id)
            await edit_message(bot, chat_id, message_id, "✅ تم حذف المصدر.", kb_sources_menu())

        elif data.startswith("srctest:"):
            await test_single_source(bot, cq, int(data.split(":", 1)[1]))

        elif data == "chan:add":
            db.set_pending_action(user_id, "add_channel_id", {})
            await edit_message(bot, chat_id, message_id,
                                "أرسل معرف القناة مثل:\n@ArtintDigital")

        elif data == "chan:list":
            await list_channels_view(bot, chat_id, message_id)

        elif data == "chan:delete_menu":
            await channel_action_menu(bot, chat_id, message_id, "chandel", "🗑 اختر قناة لحذفها:")

        elif data == "chan:default_menu":
            await channel_action_menu(bot, chat_id, message_id, "chandef", "⭐ اختر القناة الافتراضية:")

        elif data.startswith("chandel:"):
            await delete_channel_by_row_id(bot, chat_id, message_id, int(data.split(":", 1)[1]))

        elif data.startswith("chandef:"):
            await set_default_channel_by_row_id(bot, chat_id, message_id, int(data.split(":", 1)[1]))

        elif data.startswith("aiset:"):
            await handle_ai_setting_callback(bot, chat_id, message_id, user_id, data.split(":", 1)[1])

        elif data.startswith("art:"):
            await handle_article_callback(bot, cq, data)

    except Exception as e:
        db.log("error", "handlers", f"خطأ أثناء معالجة callback '{data}': {e}")
        try:
            await send_message(bot, chat_id, f"⚠️ حدث خطأ: {e}")
        except Exception:
            pass


async def finalize_add_source(bot, chat_id, message_id, user_id, category_key):
    pending = db.get_pending_action(user_id)
    data = (pending or {}).get("data") or {}
    name = data.get("name", "مصدر بدون اسم")
    url = data.get("url", "")
    db.add_source(name, url, category_key)
    db.clear_pending_action(user_id)
    label = CATEGORIES.get(category_key, category_key)
    await edit_message(bot, chat_id, message_id,
                        f"✅ تمت إضافة المصدر '{escape_html(name)}' بتصنيف {label}.",
                        kb_sources_menu())


async def list_sources_view(bot, chat_id, message_id):
    sources = db.list_sources()
    if not sources:
        await edit_message(bot, chat_id, message_id, "لا توجد مصادر مضافة بعد.", kb_sources_menu())
        return
    lines = ["📋 <b>المصادر</b>", ""]
    for s in sources:
        status = "✅" if s["active"] else "⛔"
        label = CATEGORIES.get(s["category"], s["category"])
        lines.append(f"{status} <b>{escape_html(s['name'])}</b> — {label}\n{escape_html(s['url'])}")
    await edit_message(bot, chat_id, message_id, "\n\n".join(lines), kb_sources_menu())


async def source_action_menu(bot, chat_id, message_id, prefix, title):
    sources = db.list_sources()
    if not sources:
        await edit_message(bot, chat_id, message_id, "لا توجد مصادر مضافة بعد.", kb_sources_menu())
        return
    items = [(str(s["id"]), f"{s['name']}") for s in sources]
    await edit_message(bot, chat_id, message_id, title,
                        kb_list_with_delete(items, prefix, "menu:sources"))


async def test_single_source(bot, cq, source_id):
    from bot.sources import fetch_source_entries
    source = db.get_source(source_id)
    if not source:
        await answer_callback(bot, cq.id, "المصدر غير موجود.", show_alert=True)
        return
    try:
        entries = fetch_source_entries(source["url"], limit=3)
        db.mark_source_checked(source_id)
        await answer_callback(bot, cq.id,
                               f"✅ تم جلب {len(entries)} عنصر بنجاح من '{source['name']}'.",
                               show_alert=True)
    except Exception as e:
        db.mark_source_checked(source_id, error=str(e))
        await answer_callback(bot, cq.id, f"❌ فشل الاختبار: {e}", show_alert=True)


async def list_channels_view(bot, chat_id, message_id):
    channels = db.list_channels()
    if not channels:
        await edit_message(bot, chat_id, message_id, "لا توجد قنوات مضافة بعد.", kb_channels_menu())
        return
    lines = ["📢 <b>القنوات</b>", ""]
    for c in channels:
        star = "⭐" if c["is_default"] else ""
        lines.append(f"{star} {escape_html(c['title'] or c['chat_id'])} ({escape_html(c['chat_id'])})")
    await edit_message(bot, chat_id, message_id, "\n".join(lines), kb_channels_menu())


async def channel_action_menu(bot, chat_id, message_id, prefix, title):
    channels = db.list_channels()
    if not channels:
        await edit_message(bot, chat_id, message_id, "لا توجد قنوات مضافة بعد.", kb_channels_menu())
        return
    items = [(str(c["id"]), c["title"] or c["chat_id"]) for c in channels]
    await edit_message(bot, chat_id, message_id, title,
                        kb_list_with_delete(items, prefix, "menu:channels"))


async def delete_channel_by_row_id(bot, chat_id, message_id, row_id):
    for c in db.list_channels():
        if c["id"] == row_id:
            db.remove_channel(c["chat_id"])
            break
    await edit_message(bot, chat_id, message_id, "✅ تم حذف القناة.", kb_channels_menu())


async def set_default_channel_by_row_id(bot, chat_id, message_id, row_id):
    for c in db.list_channels():
        if c["id"] == row_id:
            db.set_default_channel(c["chat_id"])
            break
    await edit_message(bot, chat_id, message_id, "✅ تم ضبط القناة الافتراضية.", kb_channels_menu())


async def handle_ai_setting_callback(bot, chat_id, message_id, user_id, action):
    settings = db.get_all_settings()

    if action == "toggle_mode":
        new_mode = "manual" if settings.get("publish_mode") == "auto" else "auto"
        db.set_setting("publish_mode", new_mode)

    elif action == "toggle_show_source":
        db.set_setting("show_source", "0" if settings.get("show_source") == "1" else "1")

    elif action == "toggle_show_link":
        db.set_setting("show_link", "0" if settings.get("show_link") == "1" else "1")

    elif action == "toggle_images":
        db.set_setting("images_enabled", "0" if settings.get("images_enabled") == "1" else "1")

    elif action == "set_min_score":
        db.set_pending_action(user_id, "set_min_score", {})
        await edit_message(bot, chat_id, message_id, "أرسل القيمة الجديدة للحد الأدنى للتقييم (0-100):")
        return

    elif action == "set_daily_limit":
        db.set_pending_action(user_id, "set_daily_limit", {})
        await edit_message(bot, chat_id, message_id, "أرسل الحد الأقصى الجديد لعدد المنشورات اليومية:")
        return

    elif action == "set_interval":
        db.set_pending_action(user_id, "set_interval", {})
        await edit_message(bot, chat_id, message_id, "أرسل الفاصل الزمني الجديد بين المنشورات (بالدقائق):")
        return

    elif action == "set_signature":
        db.set_pending_action(user_id, "set_signature", {})
        await edit_message(bot, chat_id, message_id, "أرسل نص التوقيع الجديد الذي يُضاف أسفل كل منشور:")
        return

    settings = db.get_all_settings()
    await edit_message(bot, chat_id, message_id, "🤖 <b>إعدادات الذكاء الاصطناعي والنشر</b>",
                        kb_ai_settings_menu(settings))


async def show_stats(bot, chat_id, message_id):
    counters = db.get_counters()
    sources = db.list_sources()
    channels = db.list_channels()
    last_scan = db.get_setting("last_scan_at", "لم يتم بعد")

    lines = [
        "📊 <b>الإحصائيات</b>", "",
        f"عدد المصادر: {len(sources)}",
        f"عدد القنوات: {len(channels)}",
        f"عدد المقالات التي تم فحصها: {counters.get('checked_count', 0)}",
        f"عدد المقالات المقبولة: {counters.get('approved_count', 0)}",
        f"عدد المقالات المرفوضة: {counters.get('rejected_count', 0)}",
        f"عدد المنشورات: {counters.get('published_count', 0)}",
        f"عدد الأخطاء: {counters.get('error_count', 0)}",
        f"آخر عملية فحص: {last_scan}",
    ]
    await edit_message(bot, chat_id, message_id, "\n".join(lines), kb_back())


async def show_category_stats(bot, chat_id, message_id, category_key):
    rows = db.category_counts()
    label = CATEGORIES.get(category_key, category_key)
    counts = {}
    for r in rows:
        if r["category"] == category_key:
            counts[r["status"]] = r["n"]
    pending_total = (counts.get('pending_approval', 0) + counts.get('awaiting_approval', 0)
                     + counts.get('new', 0) + counts.get('approved', 0))
    lines = [f"{label}", "",
             f"قيد الانتظار: {pending_total}",
             f"منشور: {counts.get('published', 0)}",
             f"مرفوض: {counts.get('rejected', 0)}"]
    await edit_message(bot, chat_id, message_id, "\n".join(lines), kb_back())


async def handle_article_callback(bot: Bot, cq, data):
    _, action, article_id = data.split(":")
    article_id = int(article_id)
    chat_id = cq.message.chat_id
    message_id = cq.message.message_id

    article = db.get_article(article_id)
    if not article:
        await send_message(bot, chat_id, "⚠️ هذا الخبر لم يعد موجودًا.")
        return

    if action == "approve":
        channel = db.get_default_channel()
        if not channel:
            await send_message(bot, chat_id, "⚠️ لا توجد قناة افتراضية. أضف قناة أولًا.")
            return
        try:
            article_with_source = _enrich_article(article)
            await publisher.publish_article(bot, article_with_source, channel["chat_id"])
            db.update_article_status(article_id, "published")
            db.bump_counter("published_count")
            await edit_message(bot, chat_id, message_id, "✅ تم النشر بنجاح.")
        except Exception as e:
            db.bump_counter("error_count")
            db.log("error", "publisher", f"فشل نشر المقال {article_id}: {e}")
            await send_message(bot, chat_id, f"❌ فشل النشر: {e}")

    elif action == "reject":
        db.update_article_status(article_id, "rejected")
        db.bump_counter("rejected_count")
        await edit_message(bot, chat_id, message_id, "❌ تم رفض هذا الخبر.")

    elif action == "edit":
        db.set_pending_action(cq.from_user.id, "edit_article_text", {"article_id": article_id})
        await send_message(bot, chat_id,
                            "✏️ أرسل النص الجديد الذي سيحل محل ملخص هذا الخبر:")

    elif action == "regen":
        source_name = article.get("category", "")
        try:
            result = ai.process_article(
                title=article["raw_title"],
                description=article["raw_description"],
                source_name=source_name,
            )
            db.update_article_ai(article_id, result["title_ar"], result["summary_ar"],
                                  result["score"], "pending_approval", result["category"])
            updated = db.get_article(article_id)
            preview = publisher.format_post(_enrich_article(updated))
            await edit_message(bot, chat_id, message_id, preview, kb_approval(article_id))
        except Exception as e:
            await send_message(bot, chat_id, f"❌ فشلت إعادة الصياغة: {e}")


def _enrich_article(article: dict) -> dict:
    """يضيف اسم المصدر إلى قاموس المقال قبل تنسيقه للنشر."""
    enriched = dict(article)
    if article.get("source_id"):
        source = db.get_source(article["source_id"])
        enriched["source_name"] = source["name"] if source else ""
    else:
        enriched["source_name"] = ""
    enriched["link"] = article.get("link")
    return enriched
