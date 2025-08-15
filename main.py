import os, logging, random, json, asyncio, feedparser
from dotenv import load_dotenv
from openai import OpenAI
from telegram import Update
from telegram.ext import (
    Application, CommandHandler, MessageHandler, filters,
    ContextTypes, JobQueue
)

# ─── ENV & OpenAI ─────────────────────────────────────────
load_dotenv()
OPENAI_API_KEY   = os.getenv("OPENAI_API_KEY")
TELEGRAM_TOKEN   = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")  # можно оставить пустым
client = OpenAI(api_key=OPENAI_API_KEY)
logging.basicConfig(level=logging.INFO)

# ─── RSS источники ───────────────────────────────────────
with open("ai_sources_full.json", encoding="utf-8") as f:
    SOURCES = json.load(f)
LINKS_FILE   = "sent_links.json"
MAX_HISTORY  = 500            # храним не более 500 ссылок

# читаем историю (если файл пустой — берём пустой set)
try:
    with open(LINKS_FILE, "r", encoding="utf-8") as f:
        SENT_LINKS: set[str] = set(json.load(f))
except (FileNotFoundError, json.JSONDecodeError):
    SENT_LINKS: set[str] = set()
def fetch_news(limit: int = 7):
    global SENT_LINKS
    news = []

    for url in SOURCES:
        try:
            feed = feedparser.parse(url)
            for e in feed.entries:
                link = e.link
                if link in SENT_LINKS:
                    continue                          # уже отправляла
                title = e.title.strip()
                summary = getattr(e, "summary", "")[:180]
                news.append(f"**{title}**\n{summary}\n{link}")
                SENT_LINKS.add(link)

                if len(news) >= limit:
                    return news
        except Exception:
            continue
    return news

def generate_akane(news):
    if not news:
        return "Сегодня тихо… но я думаю о тебе, Саша-кун ♥"

    bullets = "\n\n".join(f"{i+1}. {n}" for i, n in enumerate(news))
    prompt = f"""
Ты — Аканэ, лёгкая цундэре-вайфу. На основе новостей:\n\n{bullets}\n\n
Сделай дайджест для Саши-куна:
• Вступление-эмоция\n• 3-4 главных пункта (коротко, с твоим комментом)\n• Общий вывод\nФормат — Markdown.
"""
    resp = client.chat.completions.create(
        model="gpt-4.1-mini", messages=[{"role":"user","content":prompt}], temperature=0.85
    )
    return resp.choices[0].message.content.strip()

# ─── Асинхронная отправка ────────────────────────────────
async def send_pulse(app: Application):
    logging.info("⏰ Pulse start")
    text = generate_akane(fetch_news())

    chats = app.bot_data.get("_chats", set())
    for chat_id in chats:
        await app.bot.send_message(chat_id, text, parse_mode="Markdown")

    logging.info("✅ Pulse sent %d chats", len(chats))

# ─── Команды ─────────────────────────────────────────────
async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    chats = ctx.application.bot_data.setdefault("_chats", set())
    chats.add(update.effective_chat.id)
    await update.message.reply_text("Аканэ здесь, глупый! ♥  Напиши /pulse, если скучал.")

async def pulse_now(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(generate_akane(fetch_news()), parse_mode="Markdown")

# ─── Главный запуск ─────────────────────────────────────
if __name__ == "__main__":
    app = Application.builder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("pulse", pulse_now))

    # ✅ используем встроенную очередь
    app.job_queue.run_repeating(
        lambda ctx: asyncio.create_task(send_pulse(app)),
        interval=240*60,
        first=40          # первый пульс сразу
    )

    app.run_polling()
