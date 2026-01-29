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
ADMIN_ID = int(os.environ["ADMIN_ID"])
PORT = int(os.environ.get("PORT", 10000))

TASK_REWARD = 0.10
REF_REWARD = 0.50
TASK_RESET_TIME = timedelta(hours=24)
MIN_WITHDRAW = 1.0

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

# ================= FLASK =================
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

cur.execute("""
CREATE TABLE IF NOT EXISTS withdrawals (
    id SERIAL PRIMARY KEY,
    user_id BIGINT,
    type TEXT,
    details TEXT,
    amount NUMERIC,
    status TEXT,
    created_at TIMESTAMP
)
""")

conn.commit()

# ================= MEMORY STATE =================
user_states = {}

# ================= HELPERS =================
def ref_code(uid): return f"REF{uid}"

def add_user(uid, referred_by=None):
    cur.execute("""
        INSERT INTO users (user_id, ref_code, referred_by)
        VALUES (%s, %s, %s)
        ON CONFLICT (user_id) DO NOTHING
    """, (uid, ref_code(uid), referred_by))
    conn.commit()

def balance(uid):
    cur.execute("SELECT balance FROM users WHERE user_id=%s", (uid,))
    r = cur.fetchone()
    return float(r[0]) if r else 0.0

def add_balance(uid, amt):
    cur.execute("UPDATE users SET balance=balance+%s WHERE user_id=%s", (amt, uid))
    conn.commit()

def deduct_balance(uid, amt):
    cur.execute("UPDATE users SET balance=balance-%s WHERE user_id=%s", (amt, uid))
    conn.commit()

def can_do_task(uid, task):
    cur.execute("SELECT completed_at FROM tasks WHERE user_id=%s AND task=%s", (uid, task))
    r = cur.fetchone()
    if not r: return True
    return datetime.utcnow() - r[0] >= TASK_RESET_TIME

def complete_task(uid, task):
    cur.execute("""
        INSERT INTO tasks (user_id, task, completed_at)
        VALUES (%s,%s,%s)
        ON CONFLICT (user_id,task)
        DO UPDATE SET completed_at=%s
    """, (uid, task, datetime.utcnow(), datetime.utcnow()))
    add_balance(uid, TASK_REWARD)
    conn.commit()

# ================= MENUS =================
menu = ReplyKeyboardMarkup(
    [
        ["💰 Earn Crypto", "📋 Tasks"],
        ["📊 My Balance", "📈 My Stats"],
        ["👥 Refer & Earn"],
        ["💸 Withdraw"],
        ["🧾 Proof Payment", "❓ Help"],
    ],
    resize_keyboard=True,
)

def task_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(v["name"], callback_data=f"task_{k}")]
        for k, v in TASKS.items()
    ])

def withdraw_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("💰 Crypto Wallet", callback_data="wd_crypto")],
        [InlineKeyboardButton("📱 Digital Wallet", callback_data="wd_digital")],
        [InlineKeyboardButton("🔒 Staking Wallet", callback_data="wd_staking")],
    ])

def staking_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📆 Daily 1% APY", callback_data="stk_daily")],
        [InlineKeyboardButton("📅 Monthly 3% APY", callback_data="stk_monthly")],
        [InlineKeyboardButton("🗓 Yearly 5% APY", callback_data="stk_yearly")],
    ])

# ================= START =================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    add_user(uid, context.args[0] if context.args else None)
    await update.message.reply_text("Welcome 👋", reply_markup=menu)

# ================= MESSAGES =================
async def messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    text = update.message.text.strip()

    if text in ["💰 Earn Crypto", "📋 Tasks"]:
        await update.message.reply_text("Choose task:", reply_markup=task_keyboard())
        return

    if text == "📊 My Balance":
        await update.message.reply_text(f"💰 Balance: {balance(uid):.2f} USD")
        return

    if text == "💸 Withdraw":
        if balance(uid) < MIN_WITHDRAW:
            await update.message.reply_text("❌ Minimum withdrawal is 1 USD.")
            return
        await update.message.reply_text("Choose withdrawal method:", reply_markup=withdraw_keyboard())
        return

    # SECRET CODE TASKS
    for t, d in TASKS.items():
        if text == d["secret"]:
            if not can_do_task(uid, t):
                await update.message.reply_text("⏳ Task already completed today.")
                return
            complete_task(uid, t)
            await update.message.reply_text(f"✅ Task completed! +{TASK_REWARD} USD")
            return

    # WITHDRAW STATE
    state = user_states.get(uid)
    if state:
        state["data"].append(text)
        await finalize_withdraw(uid, context)
        user_states.pop(uid)
        await update.message.reply_text("✅ Withdrawal request submitted.")
        return

    await update.message.reply_text("❓ Invalid input.")

# ================= TASK CALLBACK =================
async def task_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    task = q.data.replace("task_", "")
    t = TASKS[task]
    await q.edit_message_text(
        f"{t['name']}\n\n{t['url']}\n\nSend secret code to claim reward."
    )

# ================= WITHDRAW CALLBACK =================
async def withdraw_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    uid = q.from_user.id
    await q.answer()

    user_states[uid] = {"type": q.data, "data": []}
    await q.edit_message_text("✍️ Enter required details:")

# ================= FINALIZE WITHDRAW =================
async def finalize_withdraw(uid, context):
    state = user_states[uid]
    details = ", ".join(state["data"])
    amt = balance(uid)

    deduct_balance(uid, amt)

    cur.execute("""
        INSERT INTO withdrawals (user_id, type, details, amount, status, created_at)
        VALUES (%s,%s,%s,%s,'Pending',%s)
    """, (uid, state["type"], details, amt, datetime.utcnow()))
    conn.commit()

    await context.bot.send_message(
        ADMIN_ID,
        f"💸 New Withdrawal\nUser: {uid}\nType: {state['type']}\nAmount: {amt}\nDetails: {details}"
    )

# ================= RUN =================
if __name__ == "__main__":
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(task_callback, pattern="^task_"))
    app.add_handler(CallbackQueryHandler(withdraw_callback, pattern="^wd_"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, messages))
    app.run_polling()
