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

ADMIN_ID = 7742465131  # 🔴 YOUR TELEGRAM ID
PROOF_CHANNEL = "https://t.me/your_proof_channel"

TASK_REWARD = 0.10
REF_REWARD = 0.50
TASK_RESET_TIME = timedelta(hours=24)
MIN_WITHDRAW = 1.0

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
    referral_paid BOOLEAN DEFAULT FALSE,
    withdraw_status TEXT DEFAULT 'None'
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

def get_user(uid):
    cur.execute(
        "SELECT balance, withdraw_status FROM users WHERE user_id=%s",
        (uid,)
    )
    return cur.fetchone()

def set_withdraw_status(uid, status):
    cur.execute(
        "UPDATE users SET withdraw_status=%s WHERE user_id=%s",
        (status, uid),
    )
    conn.commit()

# ================= MENUS =================
menu = ReplyKeyboardMarkup(
    [
        ["💰 Earn Crypto", "📋 Tasks"],
        ["👥 Refer & Earn", "📊 My Stats"],
        ["💸 Withdraw", "🧾 Proof Payment"],
        ["❓ Help"],
    ],
    resize_keyboard=True,
)

def withdraw_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("💰 Crypto Wallet", callback_data="wd_crypto")],
        [InlineKeyboardButton("💳 Digital Wallet", callback_data="wd_digital")],
        [InlineKeyboardButton("📈 Staking Wallet", callback_data="wd_stake")],
    ])

def staking_duration_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📅 Daily – 1% APY", callback_data="stake_daily")],
        [InlineKeyboardButton("🗓 Monthly – 3% APY", callback_data="stake_monthly")],
        [InlineKeyboardButton("📆 Yearly – 5% APY", callback_data="stake_yearly")],
    ])

# ================= START =================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    referred_by = context.args[0] if context.args else None
    add_user(uid, referred_by)

    await update.message.reply_text(
        "👋 Welcome!\n\nEarn crypto by completing tasks.",
        reply_markup=menu,
    )

# ================= MESSAGE HANDLER =================
async def messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    text = update.message.text.strip()

    user = get_user(uid)
    bal = float(user[0]) if user else 0.0

    if text == "💸 Withdraw":
        if bal < MIN_WITHDRAW:
            await update.message.reply_text(
                f"❌ Minimum withdrawal is {MIN_WITHDRAW} USD"
            )
            return
        await update.message.reply_text(
            "💸 Choose withdrawal method:",
            reply_markup=withdraw_keyboard()
        )
        return

    if text == "📊 My Stats":
        status = user[1] if user else "None"
        icon = {
            "None": "➖ No Request",
            "Pending": "⏳ Pending",
            "Approved": "✅ Approved",
            "Rejected": "❌ Rejected",
        }.get(status, "➖ No Request")

        await update.message.reply_text(
            "📊 *My Stats*\n\n"
            f"💰 Balance: `{bal:.2f} USD`\n"
            f"💸 Withdraw Status: {icon}",
            parse_mode="Markdown"
        )
        return

    if text == "🧾 Proof Payment":
        await update.message.reply_text(PROOF_CHANNEL)
        return

    if text == "❓ Help":
        await update.message.reply_text("Admin: @lxbRewards")
        return

    # ===== USER INPUT STATES =====
    state = context.user_data.get("state")

    if state == "crypto_name":
        context.user_data["wallet_name"] = text
        context.user_data["state"] = "crypto_address"
        await update.message.reply_text("📥 Enter wallet address:")
        return

    if state == "crypto_address":
        await send_admin(update, context, "Crypto Withdraw", context.user_data)
        return

    if state == "digital_name":
        context.user_data["wallet_name"] = text
        context.user_data["state"] = "digital_number"
        await update.message.reply_text("📥 Enter wallet number:")
        return

    if state == "digital_number":
        await send_admin(update, context, "Digital Withdraw", context.user_data)
        return

    if state == "stake_amount":
        context.user_data["amount"] = text
        await update.message.reply_text(
            "📈 Select staking duration:",
            reply_markup=staking_duration_keyboard()
        )
        return

# ================= CALLBACK HANDLER =================
async def callbacks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()

    if q.data == "wd_crypto":
        context.user_data.clear()
        context.user_data["state"] = "crypto_name"
        await q.edit_message_text("💰 Enter crypto wallet name:")
        return

    if q.data == "wd_digital":
        context.user_data.clear()
        context.user_data["state"] = "digital_name"
        await q.edit_message_text("💳 Enter digital wallet name:")
        return

    if q.data == "wd_stake":
        context.user_data.clear()
        context.user_data["state"] = "stake_amount"
        await q.edit_message_text("📈 How much amount do you want to stake?")
        return

    if q.data.startswith("stake_"):
        context.user_data["duration"] = q.data.replace("stake_", "")
        await send_admin(update, context, "Staking Request", context.user_data)

# ================= ADMIN SEND =================
async def send_admin(update, context, title, data):
    uid = update.effective_user.id
    set_withdraw_status(uid, "Pending")

    msg = (
        f"📥 *{title}*\n\n"
        f"👤 User ID: `{uid}`\n"
        f"💰 Balance: `{get_user(uid)[0]} USD`\n\n"
        "📄 Details:\n"
    )

    for k, v in data.items():
        msg += f"• {k}: {v}\n"

    await context.bot.send_message(
        chat_id=ADMIN_ID,
        text=msg,
        parse_mode="Markdown"
    )

    context.user_data.clear()
    await update.effective_message.reply_text(
        "✅ Request submitted!\n⏳ Status: Pending",
        reply_markup=menu
    )

# ================= RUN =================
if __name__ == "__main__":
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(callbacks))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, messages))

    app.run_polling(drop_pending_updates=True)
