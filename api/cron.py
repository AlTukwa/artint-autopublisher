"""
api/cron.py

نقطة تشغيل دورة النشر (RSS -> AI -> فلترة -> نشر/موافقة).
تُستدعى دوريًا عبر:
- Vercel Cron (مرة واحدة يوميًا فقط على خطة Hobby — راجع README)
- أو GitHub Actions / أي خدمة Cron خارجية مجانية لتشغيلها كل بضع دقائق

يجب حماية هذا المسار بمفتاح CRON_SECRET حتى لا يستطيع أي شخص خارجي
استدعاءه وإجراء نشر غير مرغوب.
"""

import asyncio
import json
import sys
import os
import traceback
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bot import database as db  # noqa: E402
from bot.config import CRON_SECRET  # noqa: E402
from bot.pipeline import run_cycle  # noqa: E402
from bot.telegram_api import get_bot  # noqa: E402

_DB_READY = False


def _ensure_db():
    global _DB_READY
    if not _DB_READY:
        db.init_db()
        _DB_READY = True


class handler(BaseHTTPRequestHandler):

    def do_GET(self):
        if not self._is_authorized():
            self._respond(401, {"ok": False, "error": "unauthorized"})
            return

        try:
            _ensure_db()
            bot = get_bot()
            result = asyncio.run(self._run(bot))
            self._respond(200, {"ok": True, "result": result})
        except Exception as e:
            traceback.print_exc()
            try:
                db.log("error", "cron", f"فشل تشغيل الدورة: {e}")
            except Exception:
                pass
            self._respond(500, {"ok": False, "error": str(e)})

    async def _run(self, bot):
        await bot.initialize()
        try:
            return await run_cycle(bot)
        finally:
            await bot.shutdown()

    def _is_authorized(self) -> bool:
        if not CRON_SECRET:
            # بدون CRON_SECRET مضبوط، لا نسمح بتشغيل الدورة حماية من الاستخدام العشوائي
            return False

        auth_header = self.headers.get("Authorization", "")
        if auth_header == f"Bearer {CRON_SECRET}":
            return True

        query = parse_qs(urlparse(self.path).query)
        if query.get("secret", [""])[0] == CRON_SECRET:
            return True

        return False

    def _respond(self, status, payload):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.end_headers()
        self.wfile.write(body)
