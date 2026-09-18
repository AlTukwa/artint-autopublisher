import os
import json
from http.server import BaseHTTPRequestHandler

from telegram import Update
from telegram.ext import Application, CommandHandler


TOKEN = os.environ["BOT_TOKEN"]

application = Application.builder().token(TOKEN).build()


async def start(update: Update, context):
    await update.message.reply_text(
        "🤖 أهلاً بك في Artint AutoPublisher!\n\n"
        "اختر المجال الذي تريد متابعته لاحقًا:\n\n"
        "💻 تقنية\n"
        "📰 أخبار\n"
        "⚽ رياضة\n"
        "🎮 ألعاب"
    )


application.add_handler(CommandHandler("start", start))


class handler(BaseHTTPRequestHandler):

    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write(b"Artint AutoPublisher is running")

    def do_POST(self):
        try:
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length)
            data = json.loads(body.decode("utf-8"))

            update = Update.de_json(data, application.bot)

            import asyncio
            asyncio.run(application.initialize())
            asyncio.run(application.process_update(update))
            asyncio.run(application.shutdown())

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"ok":true}')

        except Exception as e:
            self.send_response(500)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(
                json.dumps({"ok": False, "error": str(e)}).encode("utf-8")
            )
