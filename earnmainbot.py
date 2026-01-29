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
TASK_RESET_TIME = timedelta(hours=1)

# Task definitions
TASKS = {
    "watch": {"name": "🎥 Watch Video", "url": "https://example.com/video", "wait": timedelta(minutes=10)},
    "visit": {"name": "🌐 Visit Website", "url": "https://example.com/website", "wait": timedelta(minutes=3)},
    "airdrop": {"name": "🪂 Claim Airdrop", "url": "https://example.com/airdrop", "wait": timedelta(minutes=5)},
}

# ================= FLASK HEALTH CHECK =================
app_flask = Flask(__name__)

@app_flask.route("/")
def home():
    return "Bot is running"

threading.Thread(
    target=lambda: app_flask.run(host="0.0.0.0", port=PORT),
    daemon=True
).start()

# ================= DATABASE =================
conn = psycopg.connect(DATABASE_URL)
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
    ad_started_at TIMESTAMP,
    UNIQUE(user_id, task)
)
""")
conn.commit()

# ================= HELPERS =================
def ref_code(uid): return f"REF{uid}"

def add_user(uid, referred_by=None):
    cur.execute("""
        INSERT INTO users (user_id, ref_code, referred_by)
        VALUES (%s, %s, %s)
        ON CONFLICT (user_id) DO NOTHING
    """, (uid, ref_code(uid), referred_by))
    conn.commit()

def add_balance(uid, amount):
    cur.execute("UPDATE users SET balance = balance + %s WHERE user_id=%s", (amount, uid))
    conn.commit()

def balance(uid):
    cur.execute("SELECT balance FROM users WHERE user_id=%s", (uid,))
    row = cur.fetchone()
    return float(row[0]) if row and row[0] is not None else 0.0

def can_do_task(uid, task):
    cur.execute("SELECT completed_at FROM tasks WHERE user_id=%s AND task=%s", (uid, task))
    row = cur.fetchone()
    return True if not row or not row[0] else datetime.utcnow() - row[0] >= TASK_RESET_TIME

def start_ad(uid, task):
    cur.execute("""
        INSERT INTO tasks (user_id, task, ad_started_at)
        VALUES (%s, %s, %s)
        ON CONFLICT (user_id, task)
        DO UPDATE SET ad_started_at=%s
    """, (uid, task, datetime.utcnow(), datetime.utcnow()))
    conn.commit()

def can_claim_ad(uid, task):
    cur.execute("SELECT ad_started_at FROM tasks WHERE user_id=%s AND task=%s", (uid, task))
    row = cur.fetchone()
    if not row or not row[0]:
        return False
    return datetime.utcnow() - row[0] >= TASKS[task]["wait"]

def complete_task(uid, task):
    cur.execute("UPDATE tasks SET completed_at=%s WHERE user_id=%s AND task=%s", (datetime.utcnow(), uid, task))
    add_balance(uid, TASK_REWARD)
    conn.commit()

def referral_info(uid):
    cur.execute("SELECT referred_by, referral_paid FROM users WHERE user_id=%s", (uid,))
    return cur.fetchone()

def mark_ref_paid(uid):
    cur.execute("UPDATE users SET referral_paid=TRUE WHERE user_id=%s", (uid,))
    conn.commit()

# ================= MENU =================
menu = ReplyKeyboardMarkup(
    [["💰 Earn Crypto", "📋 Tasks"], ["👥 Refer & Earn", "📊 My Balance"], ["🧾 Proof Payment", "❓ Help"]],
    resize_keyboard=True
)

# ================= COMMANDS =================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    referred_by = context.args[0] if context.args else None
    add_user(uid, referred_by)
    await update.message.reply_text("Welcome 👋\nComplete tasks & earn rewards!", reply_markup=menu)

# ================= MESSAGES =================
async def messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    text = update.message.text

    if text in ["💰 Earn Crypto", "📋 Tasks"]:
        await update.message.reply_text(
            "Choose a task:",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton(TASKS["watch"]["name"], callback_data="task_watch")],
                [InlineKeyboardButton(TASKS["visit"]["name"], callback_data="task_visit")],
                [InlineKeyboardButton(TASKS["airdrop"]["name"], callback_data="task_airdrop")],
            ])
        )
        return

    if text == "📊 My Balance":
        await update.message.reply_text(f"💰 Balance: {balance(uid):.2f} USD")
        return

    if text == "👥 Refer & Earn":
        await update.message.reply_text(
            f"Earn {REF_REWARD} USD per referral\n\nhttps://t.me/YOUR_BOT_USERNAME?start={ref_code(uid)}"
        )
        return

    if text == "🧾 Proof Payment":
        await update.message.reply_text("https://t.me/your_proof_channel")
        return

    if text == "❓ Help":
        await update.message.reply_text("Admin: @YourAdminUsername")
        return

# ================= TASK CALLBACK =================
async def tasks_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    uid = q.from_user.id
    task = q.data.replace("task_", "")
    print(f"[DEBUG] Task clicked: {task}")
    await q.answer()

    if not can_do_task(uid, task):
        await q.edit_message_text("⏳ Task available again after 1 hour.")
        return

    start_ad(uid, task)

    await q.edit_message_text(
        f"{TASKS[task]['name']} started 👇\nComplete the task, then click Claim Reward",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton(f"🔗 Open {TASKS[task]['name']}", url=TASKS[task]["url"])],
            [InlineKeyboardButton("✅ Claim Reward", callback_data=f"claim_{task}")]
        ])
    )

# ================= CLAIM CALLBACK =================
async def claim_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    uid = q.from_user.id
    task = q.data.replace("claim_", "")
    print(f"[DEBUG] Claim clicked: {task}")
    await q.answer()

    if not can_claim_ad(uid, task):
        await q.edit_message_text("⏳ Please wait for the task ad to finish.")
        return

    complete_task(uid, task)

    ref = referral_info(uid)
    if ref:
        referred_by, paid = ref
        if referred_by and not paid:
            cur.execute("SELECT user_id FROM users WHERE ref_code=%s", (referred_by,))
            r = cur.fetchone()
            if r:
                add_balance(r[0], REF_REWARD)
                mark_ref_paid(uid)

    await q.edit_message_text(f"✅ {TASKS[task]['name']} completed!\n+{TASK_REWARD} USD added")

# ================= ERROR HANDLER =================
async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    print(f"[ERROR] Exception: {context.error}")

# ================= RUN BOT =================
if __name__ == "__main__":
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, messages))
    app.add_handler(CallbackQueryHandler(tasks_callback, pattern="^task_"))
    app.add_handler(CallbackQueryHandler(claim_callback, pattern="^claim_"))
    app.add_error_handler(error_handler)
    app.run_polling()
