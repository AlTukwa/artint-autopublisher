import os
from telegram import Update
from telegram.ext import Application, CommandHandler


TOKEN = os.environ["BOT_TOKEN"]


async def start(update: Update, context):
    await update.message.reply_text(
        "🤖 أهلاً بك في Artint AutoPublisher!\n\n"
        "اختر المجال الذي تريد متابعته لاحقًا:\n\n"
        "💻 تقنية\n"
        "📰 أخبار\n"
        "⚽ رياضة\n"
        "🎮 ألعاب"
    )


application = Application.builder().token(TOKEN).build()
application.add_handler(CommandHandler("start", start))


async def handler(request):
    if request.method != "POST":
        return {"status": "Artint AutoPublisher is running"}

    data = await request.json()

    update = Update.de_json(data, application.bot)

    await application.initialize()
    await application.process_update(update)
    await application.shutdown()

    return {"ok": True}
