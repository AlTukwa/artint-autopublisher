"""
bot/config.py
إعدادات المشروع الثابتة وقراءة متغيرات البيئة.
لا تضع أي مفتاح سري هنا مباشرة — كل شيء يُقرأ من Environment Variables.
"""

import os

# ------------------------------------------------------------------
# متغيرات البيئة الأساسية
# ------------------------------------------------------------------
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
OPENAI_API_BASE = os.environ.get("OPENAI_API_BASE", "https://api.openai.com/v1")
OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")

# رابط قاعدة البيانات (PostgreSQL — انظر README لشرح السبب بدل SQLite)
DATABASE_URL = os.environ.get("DATABASE_URL", "")

# سر بسيط يُستخدم للتحقق من أن استدعاء /api/cron قادم من جهة موثوقة
CRON_SECRET = os.environ.get("CRON_SECRET", "")

# سر اختياري يرسله Telegram في هيدر X-Telegram-Bot-Api-Secret-Token
# (يُضبط عند إعداد setWebhook بمعامل secret_token)
WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET", "")

# قائمة معرفات المشرفين المسموح لهم استخدام لوحة التحكم
_admin_ids_raw = os.environ.get("ADMIN_IDS", os.environ.get("ADMIN_ID", ""))
ADMIN_IDS = set()
for _part in _admin_ids_raw.replace(" ", "").split(","):
    if _part.isdigit():
        ADMIN_IDS.add(int(_part))


def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


# ------------------------------------------------------------------
# التصنيفات المدعومة
# ------------------------------------------------------------------
CATEGORIES = {
    "technology": "💻 Technology",
    "news": "📰 News",
    "sports": "⚽ Sports",
    "gaming": "🎮 Gaming",
    "ai": "🤖 AI",
    "android": "📱 Android",
    "apple": "🍎 Apple",
    "crypto": "💰 Crypto",
}

# التصنيفات الظاهرة كأزرار مختصرة في القائمة الرئيسية
MAIN_MENU_CATEGORIES = [
    ("news", "📰 الأخبار"),
    ("technology", "💻 التقنية"),
    ("sports", "⚽ الرياضة"),
    ("gaming", "🎮 الألعاب"),
]

PUBLISH_MODE_AUTO = "auto"
PUBLISH_MODE_MANUAL = "manual"

# ------------------------------------------------------------------
# القيم الافتراضية للإعدادات (تُحفظ في جدول settings عند أول تشغيل)
# ------------------------------------------------------------------
DEFAULT_SETTINGS = {
    "min_score": "60",           # الحد الأدنى للتقييم للنشر
    "daily_limit": "20",          # الحد الأقصى لعدد المنشورات يوميًا
    "interval_minutes": "30",     # الفاصل الزمني بين كل منشور والآخر
    "publish_mode": PUBLISH_MODE_MANUAL,
    "language": "ar",
    "signature": "",
    "show_source": "1",
    "show_link": "1",
    "images_enabled": "1",
    "publishing_enabled": "1",    # تشغيل/إيقاف النشر من القائمة الرئيسية
    "articles_per_source_per_run": "5",
}

MAX_LOG_ROWS = 500
