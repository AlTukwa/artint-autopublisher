import os
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

TOKEN = os.getenv("BOT_TOKEN")


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 أهلاً بك في Artint AutoPublisher\n\n"
        "أنا بوت النشر الذكي.\n\n"
        "اختر المجال الذي تريد العمل عليه لاحقًا:\n"
        "💻 تقنية\n"
        "📰 أخبار\n"
        "⚽ رياضة\n"
        "🎮 ألعاب"
    )


def main():
    if not TOKEN:
        raise ValueError("BOT_TOKEN غير موجود")

    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))

    print("Bot is running...")
    app.run_polling()


if __name__ == "__main__":
    main()
