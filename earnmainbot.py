import os
from datetime import datetime, timedelta

import psycopg
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
ADMIN_ID = int(os.environ.get("ADMIN_ID", "ADMIN_ID"))

TASK_REWARD = 0.10
MIN_WITHDRAW = 1.0
TASK_RESET = timedelta(hours=24)

VIDEO_LINK = "https://example.com/video"
SECRET_CODE = "ABC123"

# ================= DATABASE =================
conn = psycopg.connect(DATABASE_URL)
cur = conn.cursor()

cur.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id BIGINT PRIMARY KEY,
    balance NUMERIC DEFAULT 0
)
""")

cur.execute("""
CREATE TABLE IF NOT EXISTS tasks (
    user_id BIGINT,
    task TEXT,
    completed_at TIMESTAMP,
    PRIMARY KEY (user_id, task)
)
""")

cur.execute("""
CREATE TABLE IF NOT EXISTS withdrawals (
    user_id BIGINT,
    method TEXT,
    details TEXT,
    amount NUMERIC,
    status TEXT,
    created_at TIMESTAMP
)
""")

conn.commit()

# ================= HELPERS =================
def add_user(uid):
    cur.execute(
        "INSERT INTO users (user_id) VALUES (%s) ON CONFLICT DO NOTHING",
        (uid,)
    )
    conn.commit()

def get_balance(uid):
    cur.execute("SELECT balance FROM users WHERE user_id=%s", (uid,))
    return float(cur.fetchone()[0])

def add_balance(uid, amount):
    cur.execute(
        "UPDATE users SET balance = balance + %s WHERE user_id=%s",
        (amount, uid)
    )
    conn.commit()

def task_available(uid, task):
    cur.execute(
        "SELECT completed_at FROM tasks WHERE user_id=%s AND task=%s",
        (uid, task)
    )
    row = cur.fetchone()
    if not row:
        return True
    return datetime.utcnow() - row[0] >= TASK_RESET

def complete_task(uid, task):
    cur.execute("""
        INSERT INTO tasks (user_id, task, completed_at)
        VALUES (%s, %s, %s)
        ON CONFLICT (user_id, task)
        DO UPDATE SET completed_at=%s
    """, (uid, task, datetime.utcnow(), datetime.utcnow()))
    add_balance(uid, TASK_REWARD)
    conn.commit()

# ================= KEYBOARDS =================
menu = ReplyKeyboardMarkup(
    [
        ["💰 Earn Crypto", "📈 My Stats"],
        ["💸 Withdraw", "❓ Help"],
    ],
    resize_keyboard=True
)

withdraw_kb = InlineKeyboardMarkup([
    [InlineKeyboardButton("🪙 Crypto Wallet", callback_data="wd_crypto")],
    [InlineKeyboardButton("💳 Digital Wallet", callback_data="wd_digital")],
    [InlineKeyboardButton("📈 Staking Wallet", callback_data="wd_staking")],
])

# ================= START =================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    add_user(uid)

    await update.message.reply_text(
        "👋 Welcome!\nEarn crypto by completing tasks.",
        reply_markup=menu
    )

# ================= MESSAGES =================
async def messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    text = update.message.text

    # EARN
    if text == "💰 Earn Crypto":
        await update.message.reply_text(
            "🎥 Watch Video Task",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("▶ Watch Video", callback_data="watch_video")]
            ])
        )

    # STATS (TEXT ONLY – NO INLINE)
    elif text == "📈 My Stats":
        bal = get_balance(uid)
        await update.message.reply_text(
            f"📊 Your Account Stats\n\n"
            f"💰 Balance: {bal:.2f} USD\n"
            f"🎯 Tasks reset every 24 hours\n"
            f"💸 Minimum withdrawal: {MIN_WITHDRAW} USD\n\n"
            f"Keep earning 🚀"
        )

    # WITHDRAW
    elif text == "💸 Withdraw":
        bal = get_balance(uid)
        if bal < MIN_WITHDRAW:
            await update.message.reply_text(
                f"❌ Minimum withdrawal is {MIN_WITHDRAW} USD\n"
                f"Your balance: {bal:.2f} USD"
            )
        else:
            await update.message.reply_text(
                "Choose withdrawal method:",
                reply_markup=withdraw_kb
            )

    # HELP
    elif text == "❓ Help":
        await update.message.reply_text("Admin support available.")

# ================= CALLBACKS =================
async def callbacks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    uid = q.from_user.id
    data = q.data
    await q.answer()

    # WATCH VIDEO TASK
    if data == "watch_video":
        if not task_available(uid, "video"):
            await q.message.reply_text("⏳ Task resets after 24 hours.")
            return

        context.user_data["await_code"] = True

        await q.message.reply_text(
            f"▶ Watch video:\n{VIDEO_LINK}\n\n"
            "After watching, send the **SECRET CODE**."
        )

    # WITHDRAW OPTIONS
    elif data.startswith("wd_"):
        await q.message.reply_text(
            "📩 Withdrawal request received.\nAdmin will contact you."
        )

        cur.execute("""
            INSERT INTO withdrawals
            (user_id, method, details, amount, status, created_at)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (
            uid,
            data.replace("wd_", ""),
            "Pending user details",
            get_balance(uid),
            "PENDING",
            datetime.utcnow()
        ))
        conn.commit()

        await context.bot.send_message(
            ADMIN_ID,
            f"📤 Withdrawal Request\nUser: {uid}\nMethod: {data}"
        )

# ================= SECRET CODE =================
async def secret_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    text = update.message.text.strip()

    if context.user_data.get("await_code"):
        if text == SECRET_CODE:
            complete_task(uid, "video")
            context.user_data["await_code"] = False

            await update.message.reply_text(
                f"✅ Task completed!\n+{TASK_REWARD} USD added."
            )
        else:
            await update.message.reply_text("❌ Invalid code.")

# ================= RUN =================
if __name__ == "__main__":
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, messages))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, secret_code))
    app.add_handler(CallbackQueryHandler(callbacks))

    app.run_polling(drop_pending_updates=True)
