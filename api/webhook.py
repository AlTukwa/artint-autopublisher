"""
api/webhook.py

نقطة استقبال Telegram Webhook على Vercel.
GET  -> فحص سريع يعيد "Artint AutoPublisher is running"
POST -> يستقبل تحديث Telegram (Update) ويمرره لمعالج البوت.

هذا الملف يتبع الشكل الرسمي المطلوب من Vercel Python Runtime لدوال /api:
تعريف صنف باسم `handler` يرث من BaseHTTPRequestHandler.
لا يوجد application.run_polling() هنا إطلاقًا — Webhook فقط.
"""

import asyncio
import json
import sys
import os
import traceback
from http.server import BaseHTTPRequestHandler

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bot import database as db  # noqa: E402
from bot.config import WEBHOOK_SECRET  # noqa: E402
from bot.handlers import process_update  # noqa: E402
from bot.telegram_api import get_bot  # noqa: E402

_DB_READY = False


def _ensure_db():
    global _DB_READY
    if not _DB_READY:
        db.init_db()
        _DB_READY = True


class handler(BaseHTTPRequestHandler):

    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write("Artint AutoPublisher is running".encode("utf-8"))

    def do_POST(self):
        try:
            if WEBHOOK_SECRET:
                incoming_secret = self.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
                if incoming_secret != WEBHOOK_SECRET:
                    self._respond(401, {"ok": False, "error": "invalid secret token"})
                    return

            content_length = int(self.headers.get("Content-Length", 0) or 0)
            raw_body = self.rfile.read(content_length) if content_length else b"{}"
            update_data = json.loads(raw_body.decode("utf-8") or "{}")

            _ensure_db()
            bot = get_bot()
            asyncio.run(self._process(bot, update_data))

            self._respond(200, {"ok": True})
        except Exception as e:
            traceback.print_exc()
            try:
                db.log("error", "webhook", f"خطأ غير متوقع في webhook: {e}")
            except Exception:
                pass
            # نعيد 200 دائمًا لتليجرام حتى لا يعيد إرسال نفس التحديث لانهائيًا
            self._respond(200, {"ok": False, "error": str(e)})

    async def _process(self, bot, update_data):
        await bot.initialize()
        try:
            await process_update(update_data, bot)
        finally:
            await bot.shutdown()

    def _respond(self, status, payload):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.end_headers()
        self.wfile.write(body)
