import os
import threading
import asyncio
from datetime import datetime, timedelta

import psycopg
from flask import Flask
from telegram import (
    Update,
    ReplyKeyboardMarkup,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

# ================= CONFIG =================
BOT_TOKEN = os.environ["BOT_TOKEN"]
DATABASE_URL = os.environ["DATABASE_URL"]
ADMIN_ID = int(os.environ["ADMIN_ID"])
PORT = int(os.environ.get("PORT", 10000))

TASK_REWARD = 0.10
REF_REWARD = 0.50
TASK_RESET_TIME = timedelta(hours=24)

# ================= TASKS =================
TASKS = {
    "watch": {
        "name": "🎥 Watch Video",
        "url": "https://example.com/video",
        "secret": "VIDEO123",
    },
    "visit": {
        "name": "🌐 Visit Website",
        "url": "https://example.com",
        "secret": "VISIT123",
    },
    "airdrop": {
        "name": "🪂 Claim Airdrop",
        "url": "https://example.com/airdrop",
        "secret": "AIRDROP123",
    },
}

# ================= FLASK (KEEP ALIVE) =================
app_flask = Flask(__name__)

@app_flask.route("/")
def home():
    return "Bot running"

threading.Thread(
    target=lambda: app_flask.run(host="0.0.0.0", port=PORT),
    daemon=True,
).start()

# ================= DATABASE =================
conn = psycopg.connect(DATABASE_URL)
conn.autocommit = True

with conn.cursor() as cur:
    cur.execute("""
    CREATE TABLE IF NOT EXISTS users (
        user_id BIGINT PRIMARY KEY,
        balance NUMERIC DEFAULT 0,
        ref_code TEXT UNIQUE,
        referred_by TEXT,
        referral_paid BOOLEAN DEFAULT FALSE
    )
    """)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS tasks (
        user_id BIGINT,
        task TEXT,
        completed_at TIMESTAMP,
        UNIQUE(user_id, task)
    )
    """)

# ================= HELPERS =================
def ref_code(uid):
    return f"REF{uid}"

def add_user(uid, referred_by=None):
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO users (user_id, ref_code, referred_by)
            VALUES (%s, %s, %s)
            ON CONFLICT (user_id) DO NOTHING
        """, (uid, ref_code(uid), referred_by))

def add_balance(uid, amount):
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE users SET balance = balance + %s WHERE user_id=%s",
            (amount, uid),
        )

def get_balance(uid):
    with conn.cursor() as cur:
        cur.execute("SELECT balance FROM users WHERE user_id=%s", (uid,))
        row = cur.fetchone()
        return float(row[0]) if row else 0.0

def can_do_task(uid, task):
    with conn.cursor() as cur:
        cur.execute(
            "SELECT completed_at FROM tasks WHERE user_id=%s AND task=%s",
            (uid, task),
        )
        row = cur.fetchone()

    if not row:
        return True
    return datetime.utcnow() - row[0] >= TASK_RESET_TIME

def complete_task(uid, task):
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO tasks (user_id, task, completed_at)
            VALUES (%s, %s, %s)
            ON CONFLICT (user_id, task)
            DO UPDATE SET completed_at=%s
        """, (uid, task, datetime.utcnow(), datetime.utcnow()))
    add_balance(uid, TASK_REWARD)

# ================= MENUS =================
menu = ReplyKeyboardMarkup(
    [
        ["💰 Earn Crypto", "📋 Tasks"],
        ["👥 Refer & Earn", "📊 My Stats"],
    ],
    resize_keyboard=True,
)

def task_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(t["name"], callback_data=f"task_{k}")]
        for k, t in TASKS.items()
    ])

# ================= HANDLERS =================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    referred_by = context.args[0] if context.args else None
    add_user(uid, referred_by)
    await update.message.reply_text(
        "👋 Welcome!\n\nComplete tasks and send secret codes to earn.",
        reply_markup=menu,
    )

async def messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    text = update.message.text.strip()

    if text in ["💰 Earn Crypto", "📋 Tasks"]:
        await update.message.reply_text("Choose a task:", reply_markup=task_keyboard())
        return

    if text == "📊 My Stats":
        stats = []
        for key, t in TASKS.items():
            status = "❌" if can_do_task(uid, key) else "✅"
            stats.append(f"{t['name']}: {status}")

        await update.message.reply_text(
            f"📊 Your Stats\n\n"
            f"💰 Balance: {get_balance(uid):.2f} USD\n\n"
            + "\n".join(stats)
        )
        return

    if text == "👥 Refer & Earn":
        await update.message.reply_text(
            f"Invite link:\nhttps://t.me/YOUR_BOT_USERNAME?start={ref_code(uid)}"
        )
        return

    # ===== SECRET CODE =====
    for task, data in TASKS.items():
        if text.upper() == data["secret"]:
            if not can_do_task(uid, task):
                await update.message.reply_text("⏳ Already completed. Try after 24h.")
                return

            complete_task(uid, task)
            await update.message.reply_text(
                f"🎉 Task Completed!\n"
                f"✅ +{TASK_REWARD} USD added"
            )
            return

    if len(text) <= 20:
        await update.message.reply_text("❌ Invalid secret code.")

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()

    if q.data.startswith("task_"):
        task = q.data.replace("task_", "")
        t = TASKS[task]
        await q.edit_message_text(
            f"{t['name']}\n\n🔗 {t['url']}\n\nSend secret code to claim."
        )

# ================= RUN =================
async def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(callback_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, messages))

    await asyncio.sleep(2)
    await app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    asyncio.run(main())
