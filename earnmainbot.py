import os
import threading
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
PORT = int(os.environ.get("PORT", 10000))

TASK_REWARD = 0.10
REF_REWARD = 0.50
TASK_RESET_TIME = timedelta(hours=24)

# ================= TASK DEFINITIONS =================
TASKS = {
    "watch": {
        "name": "🎥 Watch Video",
        "url": "https://example.com/video",
        "secret": "VIDEO123",  # 🔐 CHANGE DAILY IF YOU WANT
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

# ================= FLASK (PORT FIX FOR RENDER) =================
app_flask = Flask(__name__)

@app_flask.route("/")
def home():
    return "Bot running"

threading.Thread(
    target=lambda: app_flask.run(host="0.0.0.0", port=PORT),
    daemon=True,
).start()

# ================= DATABASE =================
conn = psycopg.connect(DATABASE_URL, autocommit=True)  # autocommit mode
cur = conn.cursor()

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
    try:
        cur.execute("""
            INSERT INTO users (user_id, ref_code, referred_by)
            VALUES (%s, %s, %s)
            ON CONFLICT (user_id) DO NOTHING
        """, (uid, ref_code(uid), referred_by))
    except Exception as e:
        print("DB Error in add_user:", e)

def add_balance(uid, amount):
    try:
        cur.execute(
            "UPDATE users SET balance = balance + %s WHERE user_id=%s",
            (amount, uid),
        )
    except Exception as e:
        print("DB Error in add_balance:", e)

def balance(uid):
    try:
        cur.execute("SELECT balance FROM users WHERE user_id=%s", (uid,))
        row = cur.fetchone()
        return float(row[0]) if row else 0.0
    except Exception as e:
        print("DB Error in balance:", e)
        return 0.0

def can_do_task(uid, task):
    try:
        cur.execute(
            "SELECT completed_at FROM tasks WHERE user_id=%s AND task=%s",
            (uid, task),
        )
        row = cur.fetchone()
        if not row or not row[0]:
            return True
        return datetime.utcnow() - row[0] >= TASK_RESET_TIME
    except Exception as e:
        print("DB Error in can_do_task:", e)
        return False

def complete_task(uid, task):
    try:
        cur.execute("""
            INSERT INTO tasks (user_id, task, completed_at)
            VALUES (%s, %s, %s)
            ON CONFLICT (user_id, task)
            DO UPDATE SET completed_at=%s
        """, (uid, task, datetime.utcnow(), datetime.utcnow()))
        add_balance(uid, TASK_REWARD)
    except Exception as e:
        print("DB Error in complete_task:", e)

def referral_info(uid):
    try:
        cur.execute(
            "SELECT referred_by, referral_paid FROM users WHERE user_id=%s",
            (uid,),
        )
        return cur.fetchone()
    except Exception as e:
        print("DB Error in referral_info:", e)
        return None

def mark_ref_paid(uid):
    try:
        cur.execute(
            "UPDATE users SET referral_paid=TRUE WHERE user_id=%s",
            (uid,),
        )
    except Exception as e:
        print("DB Error in mark_ref_paid:", e)

# ================= MENUS =================
menu = ReplyKeyboardMarkup(
    [
        ["💰 Earn Crypto", "📋 Tasks"],
        ["👥 Refer & Earn", "📊 My Balance"],
        ["🧾 Proof Payment", "❓ Help"],
    ],
    resize_keyboard=True,
)

def task_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(TASKS["watch"]["name"], callback_data="task_watch")],
        [InlineKeyboardButton(TASKS["visit"]["name"], callback_data="task_visit")],
        [InlineKeyboardButton(TASKS["airdrop"]["name"], callback_data="task_airdrop")],
    ])

# ================= START =================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    referred_by = context.args[0] if context.args else None
    add_user(uid, referred_by)

    await update.message.reply_text(
        "👋 Welcome!\n\nComplete tasks, submit secret codes & earn crypto.",
        reply_markup=menu,
    )

# ================= MESSAGE HANDLER =================
async def messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    text = update.message.text.strip()

    if text in ["💰 Earn Crypto", "📋 Tasks"]:
        await update.message.reply_text("Choose a task:", reply_markup=task_keyboard())
        return

    if text == "📊 My Balance":
        await update.message.reply_text(f"💰 Balance: {balance(uid):.2f} USD")
        return

    if text == "👥 Refer & Earn":
        await update.message.reply_text(
            f"Earn {REF_REWARD} USD per referral\n\n"
            f"https://t.me/YOUR_BOT_USERNAME?start={ref_code(uid)}"
        )
        return

    if text == "🧾 Proof Payment":
        await update.message.reply_text("https://t.me/your_proof_channel")
        return

    if text == "❓ Help":
        await update.message.reply_text("Admin: @YourAdminUsername")
        return

    # ===== SECRET CODE VALIDATION =====
    for task, data in TASKS.items():
        if text == data["secret"]:
            if not can_do_task(uid, task):
                await update.message.reply_text(
                    "⏳ You already completed this task.\nTry again after 24 hours."
                )
                return

            complete_task(uid, task)

            # Referral reward (one time)
            ref = referral_info(uid)
            if ref:
                referred_by, paid = ref
                if referred_by and not paid:
                    cur.execute(
                        "SELECT user_id FROM users WHERE ref_code=%s",
                        (referred_by,),
                    )
                    r = cur.fetchone()
                    if r:
                        add_balance(r[0], REF_REWARD)
                        mark_ref_paid(uid)

            await update.message.reply_text(
                f"🎉 **Task Completed Successfully!**\n\n"
                f"✅ +{TASK_REWARD} USD added\n"
                "🔒 Task resets after 24 hours"
            )
            return

    if len(text) <= 20:
        await update.message.reply_text("❌ Invalid secret code.")

# ================= CALLBACK TASK START =================
async def task_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()

    task = q.data.replace("task_", "")
    data = TASKS[task]

    await q.edit_message_text(
        f"{data['name']} 👇\n\n"
        f"🔗 {data['url']}\n\n"
        "📌 Watch / visit carefully.\n"
        "✍️ Send the **secret code** from this task to claim reward."
    )

# ================= RUN =================
if __name__ == "__main__":
    # ✅ AUTO RESET WEBHOOK ON STARTUP
    import requests
    requests.get(f"https://api.telegram.org/bot{BOT_TOKEN}/deleteWebhook?drop_pending_updates=true")

    # ================= TELEGRAM BOT =================
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(task_callback, pattern="^task_"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, messages))

    # ✅ Polling with drop_pending_updates
    app.run_polling(drop_pending_updates=True)
