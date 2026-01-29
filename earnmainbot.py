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
AD_WAIT_TIME = timedelta(minutes=10)

# ================= FLASK (PORT FIX) =================
app_flask = Flask(__name__)

@app_flask.route("/")
def home():
    return "Bot running"

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
def ref_code(uid):
    return f"REF{uid}"

def add_user(uid, referred_by=None):
    cur.execute("""
        INSERT INTO users (user_id, ref_code, referred_by)
        VALUES (%s, %s, %s)
        ON CONFLICT (user_id) DO NOTHING
    """, (uid, ref_code(uid), referred_by))
    conn.commit()

def add_balance(uid, amount):
    cur.execute(
        "UPDATE users SET balance = balance + %s WHERE user_id=%s",
        (amount, uid)
    )
    conn.commit()

def balance(uid):
    cur.execute("SELECT balance FROM users WHERE user_id=%s", (uid,))
    return cur.fetchone()[0]

def can_do_task(uid, task):
    cur.execute(
        "SELECT completed_at FROM tasks WHERE user_id=%s AND task=%s",
        (uid, task)
    )
    row = cur.fetchone()
    if not row:
        return True
    return datetime.utcnow() - row[0] >= TASK_RESET_TIME

def start_ad(uid, task):
    cur.execute("""
        INSERT INTO tasks (user_id, task, ad_started_at)
        VALUES (%s, %s, %s)
        ON CONFLICT (user_id, task)
        DO UPDATE SET ad_started_at=%s
    """, (uid, task, datetime.utcnow(), datetime.utcnow()))
    conn.commit()

def can_claim_ad(uid, task):
    cur.execute(
        "SELECT ad_started_at FROM tasks WHERE user_id=%s AND task=%s",
        (uid, task)
    )
    row = cur.fetchone()
    if not row or not row[0]:
        return False
    return datetime.utcnow() - row[0] >= AD_WAIT_TIME

def complete_task(uid, task):
    cur.execute("""
        UPDATE tasks
        SET completed_at=%s
        WHERE user_id=%s AND task=%s
    """, (datetime.utcnow(), uid, task))
    add_balance(uid, TASK_REWARD)
    conn.commit()

def referral_info(uid):
    cur.execute(
        "SELECT referred_by, referral_paid FROM users WHERE user_id=%s",
        (uid,)
    )
    return cur.fetchone()

def mark_ref_paid(uid):
    cur.execute(
        "UPDATE users SET referral_paid=TRUE WHERE user_id=%s",
        (uid,)
    )
    conn.commit()

# ================= MENUS =================
menu = ReplyKeyboardMarkup(
    [
        ["💰 Earn Crypto", "📋 Tasks"],
        ["👥 Refer & Earn", "📊 My Balance"],
        ["🧾 Proof Payment", "❓ Help"],
    ],
    resize_keyboard=True
)

# ================= START =================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    referred_by = context.args[0] if context.args else None
    add_user(uid, referred_by)

    await update.message.reply_text(
        "Welcome 👋\nComplete tasks & earn rewards!",
        reply_markup=menu
    )

# ================= MESSAGES =================
async def messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    text = update.message.text

    if text == "📋 Tasks":
        await update.message.reply_text(
            "Choose task:",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🎥 Watch Video", callback_data="watch")],
            ])
        )
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

# ================= TASK CALLBACK =================
async def tasks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    uid = q.from_user.id
    task = q.data
    await q.answer()

    if not can_do_task(uid, task):
        await q.edit_message_text("⏳ Task available again after 1 hour.")
        return

    start_ad(uid, task)

    await q.edit_message_text(
        "📺 Ad is loading...\n\n"
        "Watch the video below 👇\n"
        "After 10 minutes, click **Claim Reward**",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("▶ Watch Ad", url="https://example.com/ad")],
            [InlineKeyboardButton("✅ Claim Reward", callback_data="claim_watch")]
        ])
    )

# ================= CLAIM =================
async def claim(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    uid = q.from_user.id
    await q.answer()

    if not can_claim_ad(uid, "watch"):
        await q.edit_message_text("⏳ Please wait 10 minutes.")
        return

    complete_task(uid, "watch")

    # Referral reward (first task only)
    ref = referral_info(uid)
    if ref:
        referred_by, paid = ref
        if referred_by and not paid:
            cur.execute(
                "SELECT user_id FROM users WHERE ref_code=%s",
                (referred_by,)
            )
            r = cur.fetchone()
            if r:
                add_balance(r[0], REF_REWARD)
                mark_ref_paid(uid)

    await q.edit_message_text(
        f"✅ Task completed!\n+{TASK_REWARD} USD added"
    )

# ================= RUN =================
if __name__ == "__main__":
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, messages))
    app.add_handler(CallbackQueryHandler(claim, pattern="claim_watch"))
    app.add_handler(CallbackQueryHandler(tasks))
    app.run_polling()
