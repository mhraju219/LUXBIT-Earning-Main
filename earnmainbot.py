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
REF_REWARD = 0.50
TASK_RESET_TIME = timedelta(hours=24)
MIN_WITHDRAW = 1.0

# ================= TASK DEFINITIONS =================
TASKS = {
    "watch": {"name": "🎥 Watch Video", "url": "https://example.com/video", "secret": "VIDEO123"},
    "visit": {"name": "🌐 Visit Website", "url": "https://example.com", "secret": "VISIT123"},
    "airdrop": {"name": "🪂 Claim Airdrop", "url": "https://example.com/airdrop", "secret": "AIRDROP123"},
}

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
    details TEXT,
    amount NUMERIC,
    status TEXT,
    created_at TIMESTAMP
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

def balance(uid):
    cur.execute("SELECT balance FROM users WHERE user_id=%s", (uid,))
    row = cur.fetchone()
    return float(row[0]) if row else 0.0

def add_balance(uid, amount):
    cur.execute("UPDATE users SET balance = balance + %s WHERE user_id=%s", (amount, uid))
    conn.commit()

def can_do_task(uid, task):
    cur.execute("SELECT completed_at FROM tasks WHERE user_id=%s AND task=%s", (uid, task))
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
    cur.execute("SELECT referred_by, referral_paid FROM users WHERE user_id=%s", (uid,))
    return cur.fetchone()

def mark_ref_paid(uid):
    cur.execute("UPDATE users SET referral_paid=TRUE WHERE user_id=%s", (uid,))
    conn.commit()

# ================= MENUS =================
menu = ReplyKeyboardMarkup(
    [
        ["💰 Earn Crypto", "📋 Tasks"],
        ["👥 Refer & Earn", "💸 Withdraw", "📊 My Balance"],
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

withdraw_kb = InlineKeyboardMarkup([
    [InlineKeyboardButton("🪙 Crypto Wallet", callback_data="wd_crypto")],
    [InlineKeyboardButton("💳 Digital Wallet", callback_data="wd_digital")],
    [InlineKeyboardButton("📈 Staking Wallet", callback_data="wd_staking")],
])

staking_durations_kb = InlineKeyboardMarkup([
    [InlineKeyboardButton("Daily 1% APY", callback_data="staking_daily")],
    [InlineKeyboardButton("Monthly 3% APY", callback_data="staking_monthly")],
    [InlineKeyboardButton("Yearly 5% APY", callback_data="staking_yearly")],
])

# ================= START =================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    referred_by = context.args[0] if context.args else None
    add_user(uid, referred_by)
    await update.message.reply_text(
        "👋 Welcome!\nComplete tasks, submit secret codes & earn crypto.",
        reply_markup=menu,
    )

# ================= MESSAGE HANDLER =================
async def messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    text = update.message.text.strip()

    # TASKS MENU
    if text in ["💰 Earn Crypto", "📋 Tasks"]:
        await update.message.reply_text("Choose a task:", reply_markup=task_keyboard())
        return

    # BALANCE
    if text == "📊 My Balance":
        await update.message.reply_text(f"💰 Balance: {balance(uid):.2f} USD")
        return

    # REFERRAL
    if text == "👥 Refer & Earn":
        await update.message.reply_text(
            f"Earn {REF_REWARD} USD per referral\n\n"
            f"https://t.me/YOUR_BOT_USERNAME?start={ref_code(uid)}"
        )
        return

    # PROOF
    if text == "🧾 Proof Payment":
        await update.message.reply_text("https://t.me/your_proof_channel")
        return

    # WITHDRAW
    if text == "💸 Withdraw":
        bal = balance(uid)
        if bal < MIN_WITHDRAW:
            await update.message.reply_text(f"❌ Minimum withdrawal is {MIN_WITHDRAW} USD.\nYour balance: {bal:.2f} USD")
            return
        await update.message.reply_text("Choose withdrawal method:", reply_markup=withdraw_kb)
        return

    # HELP
    if text == "❓ Help":
        await update.message.reply_text("Admin: @YourAdminUsername")
        return

    # ===== SECRET CODE VALIDATION =====
    for task, data in TASKS.items():
        if text == data["secret"]:
            if not can_do_task(uid, task):
                await update.message.reply_text("⏳ You already completed this task.\nTry again after 24 hours.")
                return
            complete_task(uid, task)
            # Referral reward
            ref = referral_info(uid)
            if ref:
                referred_by, paid = ref
                if referred_by and not paid:
                    cur.execute("SELECT user_id FROM users WHERE ref_code=%s", (referred_by,))
                    r = cur.fetchone()
                    if r:
                        add_balance(r[0], REF_REWARD)
                        mark_ref_paid(uid)
            await update.message.reply_text(
                f"🎉 Task Completed Successfully!\n✅ +{TASK_REWARD} USD added\n🔒 Task resets after 24 hours"
            )
            return

    # COLLECT USER DATA FOR WITHDRAWAL / STAKING
    if context.user_data.get("await_withdraw_name"):
        context.user_data["withdraw_name"] = text
        await update.message.reply_text("Please enter wallet / account address / number:")
        context.user_data["await_withdraw_address"] = True
        context.user_data["await_withdraw_name"] = False
        return

    if context.user_data.get("await_withdraw_address"):
        method = context.user_data["withdraw_method"]
        amount = balance(uid)
        details = f"Name: {context.user_data['withdraw_name']}\nAddress/Number: {text}"
        cur.execute("""
            INSERT INTO withdrawals (user_id, method, details, amount, status, created_at)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (uid, method, details, amount, "PENDING", datetime.utcnow()))
        conn.commit()
        await update.message.reply_text(f"✅ Withdrawal request sent to admin.\nMethod: {method}\nAmount: {amount:.2f} USD")
        await context.bot.send_message(ADMIN_ID, f"📤 Withdrawal Request\nUser: {uid}\nMethod: {method}\n{details}\nAmount: {amount:.2f} USD")
        context.user_data.clear()
        return

    if context.user_data.get("await_stake_amount"):
        context.user_data["stake_amount"] = text
        await update.message.reply_text("Choose staking duration:", reply_markup=staking_durations_kb)
        context.user_data["await_stake_amount"] = False
        context.user_data["await_stake_duration"] = True
        return

# ================= CALLBACK HANDLER =================
async def callbacks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    uid = q.from_user.id
    await q.answer()
    data = q.data

    # TASK BUTTONS
    if data.startswith("task_"):
        task = data.replace("task_", "")
        t = TASKS[task]
        await q.edit_message_text(
            f"{t['name']} 👇\n\n🔗 {t['url']}\n📌 Watch / visit carefully.\n✍️ Send the secret code to claim reward."
        )
        return

    # WITHDRAW OPTIONS
    if data.startswith("wd_"):
        method = data.replace("wd_", "")
        context.user_data["withdraw_method"] = method
        if method in ["crypto", "digital"]:
            await q.message.reply_text("Enter your name for withdrawal:")
            context.user_data["await_withdraw_name"] = True
        elif method == "staking":
            await q.message.reply_text("How much amount do you want to stake?")
            context.user_data["await_stake_amount"] = True
        return

    # STAKING DURATIONS
    if data.startswith("staking_") and context.user_data.get("await_stake_duration"):
        duration = data.replace("staking_", "")
        amount = context.user_data.get("stake_amount")
        method = "staking"
        details = f"Stake Amount: {amount}\nDuration: {duration.upper()}"
        cur.execute("""
            INSERT INTO withdrawals (user_id, method, details, amount, status, created_at)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (uid, method, details, amount, "PENDING", datetime.utcnow()))
        conn.commit()
        await q.message.reply_text(f"✅ Staking request sent to admin.\nAmount: {amount}\nDuration: {duration.upper()}")
        await context.bot.send_message(ADMIN_ID, f"📤 Staking Request\nUser: {uid}\n{details}")
        context.user_data.clear()
        return

# ================= RUN =================
if __name__ == "__main__":
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, messages))
    app.add_handler(CallbackQueryHandler(callbacks))

    app.run_polling(drop_pending_updates=True)
