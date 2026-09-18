import os
import json
from fastapi import FastAPI, Request, Response
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

TOKEN = os.environ.get("BOT_TOKEN")

# إنشاء التطبيق
telegram_app = Application.builder().token(TOKEN).build()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 أهلاً بك في Artint AutoPublisher!\n\n"
        "اختر المجال الذي تريد متابعته لاحقًا:\n\n"
        "💻 تقنية\n"
        "📰 أخبار\n"
        "⚽ رياضة\n"
        "🎮 ألعاب"
    )

telegram_app.add_handler(CommandHandler("start", start))

app = FastAPI()

@app.get("/")
async def root():
    return Response(content="Artint AutoPublisher is running", media_type="text/plain; charset=utf-8")

@app.post("/webhook")
async def webhook(request: Request):
    try:
        data = await request.json()
        
        # تهيئة البوت ومعالجة التحديث
        if not telegram_app._initialized:
            await telegram_app.initialize()
            
        update = Update.de_json(data, telegram_app.bot)
        await telegram_app.process_update(update)
            
        return {"ok": True}
    except Exception as e:
        return Response(
            content=json.dumps({"ok": False, "error": str(e)}), 
            status_code=500, 
            media_type="application/json"
        )
