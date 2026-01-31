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
ADMIN_ID = int(os.environ.get("ADMIN_ID", "ADMIN_ID"))  # your Telegram ID
PORT = int(os.environ.get("PORT", 10000))

TASK_REWARD = 0.10
REF_REWARD = 0.50
TASK_RESET_TIME = timedelta(hours=24)

# ================= TASK DEFINITIONS =================
TASKS = {
    "watch": {"name": "🎥 Watch Video", "url": "https://example.com/video", "secret": "VIDEO123"},
    "visit": {"name": "🌐 Visit Website", "url": "https://example.com", "secret": "VISIT123"},
    "airdrop": {"name": "🪂 Claim Airdrop", "url": "https://example.com/airdrop", "secret": "AIRDROP123"},
}

# ================= FLASK (PORT FIX) =================
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

# Users table
cur.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id BIGINT PRIMARY KEY,
    balance NUMERIC DEFAULT 0,
    ref_code TEXT UNIQUE,
    referred_by TEXT,
    referral_paid BOOLEAN DEFAULT FALSE
)
""")

# Tasks table
cur.execute("""
CREATE TABLE IF NOT EXISTS tasks (
    user_id BIGINT,
    task TEXT,
    completed_at TIMESTAMP,
    UNIQUE(user_id, task)
)
""")

# Withdrawals table
cur.execute("""
CREATE TABLE IF NOT EXISTS withdrawals (
    user_id BIGINT,
    method TEXT,
    info TEXT,
    amount NUMERIC DEFAULT 0,
    status TEXT DEFAULT 'Pending',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
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
        (amount, uid),
    )
    conn.commit()

def balance(uid):
    cur.execute("SELECT balance FROM users WHERE user_id=%s", (uid,))
    row = cur.fetchone()
    return float(row[0]) if row else 0.0

def can_do_task(uid, task):
    cur.execute(
        "SELECT completed_at FROM tasks WHERE user_id=%s AND task=%s",
        (uid, task),
    )
    row = cur.fetchone()
    if not row or not row[0]:
        return True
    return datetime.utcnow() - row[0] >= TASK_RESET_TIME

def complete_task(uid, task):
    cur.execute("""
        INSERT INTO tasks (user_id, task, completed_at)
        VALUES (%s, %s, %s)
        ON CONFLICT (user_id, task)
        DO UPDATE SET completed_at=%s
    """, (uid, task, datetime.utcnow(), datetime.utcnow()))
    add_balance(uid, TASK_REWARD)
    conn.commit()

def referral_info(uid):
    cur.execute(
        "SELECT referred_by, referral_paid FROM users WHERE user_id=%s",
        (uid,),
    )
    return cur.fetchone()

def mark_ref_paid(uid):
    cur.execute(
        "UPDATE users SET referral_paid=TRUE WHERE user_id=%s",
        (uid,),
    )
    conn.commit()

def get_withdraw_status(uid):
    cur.execute(
        "SELECT method, amount, status, created_at FROM withdrawals WHERE user_id=%s ORDER BY created_at DESC",
        (uid,)
    )
    rows = cur.fetchall()
    if not rows:
        return "No withdrawals yet."
    lines = []
    for r in rows[:5]:  # show last 5 withdrawals
        lines.append(f"{r[0]} | {r[1]:.2f} USD | {r[2]} | {r[3].strftime('%Y-%m-%d %H:%M')}")
    return "\n".join(lines)

# ================= MENUS =================
menu = ReplyKeyboardMarkup(
    [
        ["💰 Earn Crypto", "📋 Tasks"],
        ["👥 Refer & Earn", "📊 My Stats"],
        ["💸 Withdraw"],
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

def withdraw_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("💎 Crypto Wallet", callback_data="withdraw_crypto")],
        [InlineKeyboardButton("💳 Digital Wallet", callback_data="withdraw_digital")],
        [InlineKeyboardButton("📈 Staking Wallet", callback_data="withdraw_staking")],
    ])

staking_keyboard = InlineKeyboardMarkup([
    [InlineKeyboardButton("📅 Daily 1% APY", callback_data="stake_daily")],
    [InlineKeyboardButton("📅 Monthly 3% APY", callback_data="stake_monthly")],
    [InlineKeyboardButton("📅 Yearly 5% APY", callback_data="stake_yearly")],
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
    if not update.message or not update.message.text:
    return

text = update.message.text.strip()

    # Tasks
    if text in ["💰 Earn Crypto", "📋 Tasks"]:
        await update.message.reply_text("Choose a task:", reply_markup=task_keyboard())
        return

    # My Stats
    if text == "📊 My Stats":
    try:
        stats_text = (
            f"📊 *Your Stats*\n\n"
            f"💰 Balance: {balance(uid):.2f} USD\n"
            f"🔹 Tasks completed:\n" +
            "\n".join(
                [
                    f"{t['name']}: ✅" if not can_do_task(uid, key)
                    else f"{t['name']}: ❌"
                    for key, t in TASKS.items()
                ]
            ) +
            "\n\n💸 Last Withdrawals:\n" +
            get_withdraw_status(uid)
        )

        await update.message.reply_text(stats_text, parse_mode="Markdown")

    except Exception as e:
        await update.message.reply_text("⚠️ Unable to load stats right now. Try again.")
        print("MY STATS ERROR:", e)

    return

    # Referral
    if text == "👥 Refer & Earn":
        await update.message.reply_text(
            f"Earn {REF_REWARD} USD per referral\n\n"
            f"https://t.me/YOUR_BOT_USERNAME?start={ref_code(uid)}"
        )
        return

    # Proof Payment
    if text == "🧾 Proof Payment":
        await update.message.reply_text("https://t.me/your_proof_channel")
        return

    # Help
    if text == "❓ Help":
        await update.message.reply_text("Admin: @YourAdminUsername")
        return

    # Withdraw
    if text == "💸 Withdraw":
        await update.message.reply_text("Select withdrawal method:", reply_markup=withdraw_keyboard())
        return

    # Withdraw data collection
    if context.user_data.get("withdraw_method") in ["crypto", "digital"]:
        info_type = "Crypto Wallet" if context.user_data.get("withdraw_method") == "crypto" else "Digital Wallet"
        context.user_data["withdraw_info"] = text
        # save withdrawal
        cur.execute(
            "INSERT INTO withdrawals (user_id, method, info, amount) VALUES (%s,%s,%s,%s)",
            (uid, info_type, text, balance(uid))
        )
        conn.commit()
        await update.message.reply_text(f"✅ {info_type} info received.\nAdmin will process it.")
        await context.bot.send_message(chat_id=ADMIN_ID, text=f"{info_type} Withdrawal Request:\nUser: {uid}\n{text}")
        context.user_data.pop("withdraw_method")
        return

    # Staking amount
    if context.user_data.get("withdraw_method") == "staking_amount":
        context.user_data["stake_amount"] = text
        await update.message.reply_text("Select staking duration:", reply_markup=staking_keyboard)
        return

    # Secret Code Validation
    for task, data in TASKS.items():
        if text == data["secret"]:
            if not can_do_task(uid, task):
                await update.message.reply_text("⏳ Task already done. Try again after 24h.")
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
            await update.message.reply_text(f"🎉 Task Completed!\n✅ +{TASK_REWARD} USD\n🔒 Reset after 24h")
            return

    if len(text) <= 20 and text not in [
    "💰 Earn Crypto",
    "📋 Tasks",
    "📊 My Stats",
    "👥 Refer & Earn",
    "💸 Withdraw",
    "🧾 Proof Payment",
    "❓ Help",
]:
    await update.message.reply_text("❌ Invalid secret code.")



# ================= CALLBACK HANDLER =================
async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id

    # Tasks
    if q.data.startswith("task_"):
        task = q.data.replace("task_", "")
        data = TASKS[task]
        await q.edit_message_text(
            f"{data['name']} 👇\n\n🔗 {data['url']}\n\nSend the secret code to claim reward."
        )
        return

    # Withdraw
    if q.data == "withdraw_crypto":
        context.user_data["withdraw_method"] = "crypto"
        await q.edit_message_text("Send your Crypto Wallet name and address:")
        return

    if q.data == "withdraw_digital":
        context.user_data["withdraw_method"] = "digital"
        await q.edit_message_text("Send your Digital Wallet name and number:")
        return

    if q.data == "withdraw_staking":
        context.user_data["withdraw_method"] = "staking_amount"
        await q.edit_message_text("Enter staking amount:")
        return

    # Staking duration
    if q.data in ["stake_daily", "stake_monthly", "stake_yearly"]:
        duration_map = {"stake_daily": "Daily 1% APY", "stake_monthly": "Monthly 3% APY", "stake_yearly": "Yearly 5% APY"}
        duration = duration_map[q.data]
        amount = context.user_data.get("stake_amount", "Not provided")
        await q.edit_message_text(f"📈 Staking request:\nUser: {uid}\nAmount: {amount}\nDuration: {duration}")
        await context.bot.send_message(chat_id=ADMIN_ID, text=f"Staking request:\nUser: {uid}\nAmount: {amount}\nDuration: {duration}")
        context.user_data.pop("withdraw_method", None)
        context.user_data.pop("stake_amount", None)
        return

# ================= RUN =================
if __name__ == "__main__":
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(callback_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, messages))

    # Render-safe polling
    app.run_polling(drop_pending_updates=True)
