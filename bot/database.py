"""
bot/database.py

طبقة قاعدة البيانات.

ملاحظة معمارية مهمة (اقرأها في README أيضًا):
--------------------------------------------
طلبت المواصفات استخدام SQLite في المرحلة الأولى. لكن على Vercel Serverless
لا يوجد قرص دائم يمكن الكتابة عليه بشكل موثوق بين الاستدعاءات المختلفة:
كل استدعاء قد يعمل على حاوية جديدة تمامًا، ومجلد /tmp نفسه غير مضمون البقاء،
كما يمكن تشغيل عدة نسخ من الدالة في نفس الوقت بدون أي ملف مشترك بينها.
معنى ذلك: أي بيانات تُكتب في ملف SQLite قد تختفي فورًا أو لا تُرى من نسخة
أخرى من نفس الدالة تعمل بالتوازي.

لذلك تم استبدال SQLite بقاعدة بيانات PostgreSQL مُستضافة مجانًا (مثل Supabase
أو Neon)، والتي يمكن الاتصال بها عبر الشبكة من أي دالة Serverless. هذا يحافظ
تمامًا على فكرة "قابلية النقل لاحقًا إلى PostgreSQL" التي طلبتها في البند 24،
فقط بدأنا بها مباشرة بدل SQLite لأن SQLite غير صالح على Vercel من الأساس.
كل الدوال هنا معزولة في هذا الملف، فإذا رغبت لاحقًا بتغيير مزوّد قاعدة
البيانات، التعديل يكون في هذا الملف فقط.
"""

import hashlib
import json
import time
from contextlib import contextmanager

import psycopg2
import psycopg2.extras

from bot.config import DATABASE_URL, DEFAULT_SETTINGS, MAX_LOG_ROWS

_SCHEMA = """
CREATE TABLE IF NOT EXISTS channels (
    id SERIAL PRIMARY KEY,
    chat_id TEXT UNIQUE NOT NULL,
    title TEXT,
    is_default BOOLEAN NOT NULL DEFAULT FALSE,
    added_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS sources (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    url TEXT UNIQUE NOT NULL,
    category TEXT NOT NULL DEFAULT 'news',
    active BOOLEAN NOT NULL DEFAULT TRUE,
    added_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_checked_at TIMESTAMPTZ,
    error_count INTEGER NOT NULL DEFAULT 0,
    last_error TEXT
);

CREATE TABLE IF NOT EXISTS articles (
    id SERIAL PRIMARY KEY,
    source_id INTEGER REFERENCES sources(id) ON DELETE SET NULL,
    guid TEXT,
    link TEXT,
    hash TEXT UNIQUE NOT NULL,
    category TEXT,
    raw_title TEXT,
    raw_description TEXT,
    image_url TEXT,
    ai_title TEXT,
    ai_summary TEXT,
    score INTEGER,
    status TEXT NOT NULL DEFAULT 'new',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    published_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT
);

CREATE TABLE IF NOT EXISTS counters (
    key TEXT PRIMARY KEY,
    value BIGINT NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS pending_actions (
    admin_id BIGINT PRIMARY KEY,
    action TEXT NOT NULL,
    data JSONB,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS logs (
    id SERIAL PRIMARY KEY,
    level TEXT NOT NULL,
    category TEXT NOT NULL,
    message TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
"""


@contextmanager
def get_conn():
    if not DATABASE_URL:
        raise RuntimeError(
            "DATABASE_URL غير مضبوط. أضف متغير البيئة DATABASE_URL "
            "(رابط اتصال PostgreSQL) في إعدادات Vercel."
        )
    conn = psycopg2.connect(DATABASE_URL, sslmode="require")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    """ينشئ الجداول إذا لم تكن موجودة، ويضبط الإعدادات الافتراضية. مأمون التكرار."""
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(_SCHEMA)
        for key, value in DEFAULT_SETTINGS.items():
            cur.execute(
                "INSERT INTO settings (key, value) VALUES (%s, %s) "
                "ON CONFLICT (key) DO NOTHING",
                (key, value),
            )
        for key in ("checked_count", "approved_count", "rejected_count",
                    "published_count", "error_count"):
            cur.execute(
                "INSERT INTO counters (key, value) VALUES (%s, 0) "
                "ON CONFLICT (key) DO NOTHING",
                (key,),
            )


def compute_hash(link: str, title: str) -> str:
    raw = f"{(link or '').strip()}|{(title or '').strip()}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


# ------------------------------------------------------------------
# القنوات
# ------------------------------------------------------------------
def add_channel(chat_id: str, title: str = ""):
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO channels (chat_id, title) VALUES (%s, %s) "
            "ON CONFLICT (chat_id) DO UPDATE SET title = EXCLUDED.title",
            (chat_id, title),
        )
        cur.execute("SELECT COUNT(*) FROM channels")
        count = cur.fetchone()[0]
        if count == 1:
            cur.execute("UPDATE channels SET is_default = TRUE WHERE chat_id = %s", (chat_id,))


def remove_channel(chat_id: str):
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("DELETE FROM channels WHERE chat_id = %s", (chat_id,))


def list_channels():
    with get_conn() as conn:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("SELECT * FROM channels ORDER BY added_at ASC")
        return cur.fetchall()


def set_default_channel(chat_id: str):
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("UPDATE channels SET is_default = FALSE")
        cur.execute("UPDATE channels SET is_default = TRUE WHERE chat_id = %s", (chat_id,))


def get_default_channel():
    with get_conn() as conn:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("SELECT * FROM channels WHERE is_default = TRUE LIMIT 1")
        row = cur.fetchone()
        if row:
            return row
        cur.execute("SELECT * FROM channels ORDER BY added_at ASC LIMIT 1")
        return cur.fetchone()


# ------------------------------------------------------------------
# المصادر
# ------------------------------------------------------------------
def add_source(name: str, url: str, category: str):
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO sources (name, url, category) VALUES (%s, %s, %s) "
            "ON CONFLICT (url) DO UPDATE SET name = EXCLUDED.name, category = EXCLUDED.category",
            (name, url, category),
        )


def remove_source(source_id: int):
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("DELETE FROM sources WHERE id = %s", (source_id,))


def list_sources(active_only: bool = False):
    with get_conn() as conn:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        if active_only:
            cur.execute("SELECT * FROM sources WHERE active = TRUE ORDER BY added_at ASC")
        else:
            cur.execute("SELECT * FROM sources ORDER BY added_at ASC")
        return cur.fetchall()


def get_source(source_id: int):
    with get_conn() as conn:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("SELECT * FROM sources WHERE id = %s", (source_id,))
        return cur.fetchone()


def mark_source_checked(source_id: int, error: str = None):
    with get_conn() as conn:
        cur = conn.cursor()
        if error:
            cur.execute(
                "UPDATE sources SET last_checked_at = NOW(), "
                "error_count = error_count + 1, last_error = %s WHERE id = %s",
                (error[:500], source_id),
            )
        else:
            cur.execute(
                "UPDATE sources SET last_checked_at = NOW(), error_count = 0, "
                "last_error = NULL WHERE id = %s",
                (source_id,),
            )


# ------------------------------------------------------------------
# المقالات
# ------------------------------------------------------------------
def article_exists(hash_value: str) -> bool:
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT 1 FROM articles WHERE hash = %s", (hash_value,))
        return cur.fetchone() is not None


def insert_article(source_id, guid, link, hash_value, category, raw_title,
                    raw_description, image_url):
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO articles
                (source_id, guid, link, hash, category, raw_title,
                 raw_description, image_url, status)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'new')
            ON CONFLICT (hash) DO NOTHING
            RETURNING id
            """,
            (source_id, guid, link, hash_value, category, raw_title,
             raw_description, image_url),
        )
        row = cur.fetchone()
        return row[0] if row else None


def list_articles_by_status(status: str, limit: int = 20):
    with get_conn() as conn:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(
            "SELECT * FROM articles WHERE status = %s ORDER BY created_at ASC LIMIT %s",
            (status, limit),
        )
        return cur.fetchall()


def get_article(article_id: int):
    with get_conn() as conn:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("SELECT * FROM articles WHERE id = %s", (article_id,))
        return cur.fetchone()


def update_article_ai(article_id: int, ai_title: str, ai_summary: str,
                       score: int, status: str, category: str = None):
    with get_conn() as conn:
        cur = conn.cursor()
        if category:
            cur.execute(
                "UPDATE articles SET ai_title=%s, ai_summary=%s, score=%s, "
                "status=%s, category=%s WHERE id=%s",
                (ai_title, ai_summary, score, status, category, article_id),
            )
        else:
            cur.execute(
                "UPDATE articles SET ai_title=%s, ai_summary=%s, score=%s, "
                "status=%s WHERE id=%s",
                (ai_title, ai_summary, score, status, article_id),
            )


def update_article_status(article_id: int, status: str):
    with get_conn() as conn:
        cur = conn.cursor()
        if status == "published":
            cur.execute(
                "UPDATE articles SET status=%s, published_at=NOW() WHERE id=%s",
                (status, article_id),
            )
        else:
            cur.execute("UPDATE articles SET status=%s WHERE id=%s", (status, article_id))


def update_article_summary(article_id: int, ai_summary: str):
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("UPDATE articles SET ai_summary=%s WHERE id=%s", (ai_summary, article_id))


def count_articles_published_since(seconds: int) -> int:
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT COUNT(*) FROM articles WHERE status='published' "
            "AND published_at > NOW() - (%s::text || ' seconds')::interval",
            (seconds,),
        )
        return cur.fetchone()[0]


def count_articles_published_today() -> int:
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT COUNT(*) FROM articles WHERE status='published' "
            "AND published_at::date = NOW()::date"
        )
        return cur.fetchone()[0]


def get_last_published_at():
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT MAX(published_at) FROM articles WHERE status='published'")
        row = cur.fetchone()
        return row[0] if row else None


def category_counts():
    with get_conn() as conn:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(
            "SELECT category, status, COUNT(*) AS n FROM articles "
            "GROUP BY category, status"
        )
        return cur.fetchall()


# ------------------------------------------------------------------
# الإعدادات
# ------------------------------------------------------------------
def get_setting(key: str, default=None):
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT value FROM settings WHERE key=%s", (key,))
        row = cur.fetchone()
        return row[0] if row else default


def set_setting(key: str, value: str):
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO settings (key, value) VALUES (%s, %s) "
            "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value",
            (key, str(value)),
        )


def get_all_settings():
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT key, value FROM settings")
        return dict(cur.fetchall())


# ------------------------------------------------------------------
# العدادات (للإحصائيات)
# ------------------------------------------------------------------
def bump_counter(key: str, by: int = 1):
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO counters (key, value) VALUES (%s, %s) "
            "ON CONFLICT (key) DO UPDATE SET value = counters.value + EXCLUDED.value",
            (key, by),
        )


def get_counters():
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT key, value FROM counters")
        return dict(cur.fetchall())


# ------------------------------------------------------------------
# حالة المحادثة (لخطوات إضافة مصدر/قناة متعددة الخطوات)
# ------------------------------------------------------------------
def set_pending_action(admin_id: int, action: str, data: dict = None):
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO pending_actions (admin_id, action, data, updated_at) "
            "VALUES (%s, %s, %s, NOW()) "
            "ON CONFLICT (admin_id) DO UPDATE SET action=EXCLUDED.action, "
            "data=EXCLUDED.data, updated_at=NOW()",
            (admin_id, action, json.dumps(data or {})),
        )


def get_pending_action(admin_id: int):
    with get_conn() as conn:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("SELECT * FROM pending_actions WHERE admin_id=%s", (admin_id,))
        return cur.fetchone()


def clear_pending_action(admin_id: int):
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("DELETE FROM pending_actions WHERE admin_id=%s", (admin_id,))


# ------------------------------------------------------------------
# السجلات (Logs) — بدون أي أسرار
# ------------------------------------------------------------------
def log(level: str, category: str, message: str):
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO logs (level, category, message) VALUES (%s, %s, %s)",
            (level, category, message[:2000]),
        )
        cur.execute(
            "DELETE FROM logs WHERE id IN ("
            "  SELECT id FROM logs ORDER BY created_at DESC OFFSET %s"
            ")",
            (MAX_LOG_ROWS,),
        )


def recent_logs(limit: int = 20, category: str = None):
    with get_conn() as conn:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        if category:
            cur.execute(
                "SELECT * FROM logs WHERE category=%s ORDER BY created_at DESC LIMIT %s",
                (category, limit),
            )
        else:
            cur.execute("SELECT * FROM logs ORDER BY created_at DESC LIMIT %s", (limit,))
        return cur.fetchall()
