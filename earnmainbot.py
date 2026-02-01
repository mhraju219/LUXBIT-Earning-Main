import os
import psycopg2
from datetime import datetime, timedelta
from flask import Flask, request
from telegram import (
    Update,
    ReplyKeyboardMarkup,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

# ================= ENV =================
BOT_TOKEN = os.environ["BOT_TOKEN"]
DATABASE_URL = os.environ["DATABASE_URL"]
RENDER_URL = os.environ["RENDER_URL"]  # https://your-app.onrender.com
ADMIN_CHANNEL = os.environ["ADMIN_CHANNEL"]  # @adminchannel
PROOF_CHANNEL = os.environ["PROOF_CHANNEL"]  # @proofchannel
HOT_TOKEN_URL = os.environ["HOT_TOKEN_URL"]
PORT = int(os.environ.get("PORT", 10000))

TASK_REWARD = 0.10
REF_REWARD = 0.50
RESET_TIME = timedelta(hours=24)

# ================= DATABASE =================
conn = psycopg2.connect(DATABASE_URL, sslmode="require")
conn.autocommit = True
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
    task_key TEXT,
    completed_at TIMESTAMP,
    PRIMARY KEY (user_id, task_key)
)
""")

cur.execute("""
CREATE TABLE IF NOT EXISTS withdrawals (
    user_id BIGINT,
    method TEXT,
    info TEXT,
    amount NUMERIC,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
""")

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
        "url": "https://example.com",
        "secret": "AIRDROP123",
    },
}

# ================= KEYBOARDS =================
MAIN_MENU = ReplyKeyboardMarkup(
    [
        ["🔥 Hot Token", "📋 Task"],
        ["📊 My Stats", "💸 Withdraw"],
        ["👥 Refer & Earn"],
        ["🧾 Proof Payment", "❓ Help"],
    ],
    resize_keyboard=True,
)

TASK_KEYBOARD = InlineKeyboardMarkup(
    [[InlineKeyboardButton(v["name"], callback_data=f"task_{k}")]
     for k, v in TASKS.items()]
)

WITHDRAW_KEYBOARD = InlineKeyboardMarkup(
    [
        [InlineKeyboardButton("💎 Crypto Wallet", callback_data="wd_crypto")],
        [InlineKeyboardButton("💳 Digital Wallet", callback_data="wd_digital")],
    ]
)

# ================= HELPERS =================
def ref_code(uid):
    return f"REF{uid}"

def add_user(uid, referred_by=None):
    cur.execute(
        "INSERT INTO users (user_id, ref_code, referred_by) VALUES (%s,%s,%s) ON CONFLICT DO NOTHING",
        (uid, ref_code(uid), referred_by),
    )

def get_balance(uid):
    cur.execute("SELECT balance FROM users WHERE user_id=%s", (uid,))
    r = cur.fetchone()
    return float(r[0]) if r else 0.0

def add_balance(uid, amount):
    cur.execute("UPDATE users SET balance = balance + %s WHERE user_id=%s", (amount, uid))

def can_do_task(uid, key):
    cur.execute(
        "SELECT completed_at FROM tasks WHERE user_id=%s AND task_key=%s",
        (uid, key),
    )
    r = cur.fetchone()
    return not r or datetime.utcnow() - r[0] >= RESET_TIME

def complete_task(uid, key):
    cur.execute(
        """
        INSERT INTO tasks (user_id, task_key, completed_at)
        VALUES (%s,%s,%s)
        ON CONFLICT (user_id, task_key)
        DO UPDATE SET completed_at=%s
        """,
        (uid, key, datetime.utcnow(), datetime.utcnow()),
    )
    add_balance(uid, TASK_REWARD)

# ================= BOT HANDLERS =================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    referred_by = context.args[0] if context.args else None
    add_user(uid, referred_by)
    await update.message.reply_text(
        "👋 Welcome!\nComplete tasks & earn crypto 💰",
        reply_markup=MAIN_MENU,
    )

async def messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    text = update.message.text.strip()

    if text == "🔥 Hot Token":
        await update.message.reply_text(
            "🔥 Hot Token",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("🚀 Open", url=HOT_TOKEN_URL)]]
            ),
        )
        return

    if text == "📋 Task":
        await update.message.reply_text("📋 Choose a task:", reply_markup=TASK_KEYBOARD)
        return

    if text == "📊 My Stats":
        cur.execute("SELECT COUNT(*) FROM tasks WHERE user_id=%s", (uid,))
        task_count = cur.fetchone()[0]
        await update.message.reply_text(
            f"📊 My Stats\n\n"
            f"💰 Balance: {get_balance(uid):.2f} USD\n"
            f"✅ Tasks Completed: {task_count}\n"
            f"👥 Referral ID: {ref_code(uid)}"
        )
        return

    if text == "💸 Withdraw":
        await update.message.reply_text(
            "💸 Choose withdraw method:",
            reply_markup=WITHDRAW_KEYBOARD,
        )
        return

    if text == "👥 Refer & Earn":
        await update.message.reply_text(
            f"👥 Invite & Earn\n\n"
            f"https://t.me/YOUR_BOT_USERNAME?start={ref_code(uid)}"
        )
        return

    if text == "🧾 Proof Payment":
        await update.message.reply_text(
            "🧾 Payment Proof",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("📢 Channel", url=f"https://t.me/{PROOF_CHANNEL.lstrip('@')}")]]
            ),
        )
        return

    if text == "❓ Help":
        await update.message.reply_text(
            "❓ Support",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("👮 Admin", url=f"https://t.me/{ADMIN_CHANNEL.lstrip('@')}")]]
            ),
        )
        return

    # Secret code
    for key, task in TASKS.items():
        if text == task["secret"]:
            if not can_do_task(uid, key):
                await update.message.reply_text("⏳ Task already completed.")
                return
            complete_task(uid, key)
            await update.message.reply_text(
                f"🎉 Task Completed!\n+{TASK_REWARD} USD added"
            )
            return

    await update.message.reply_text("❌ Invalid input.")

async def callbacks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    key = q.data.replace("task_", "")
    task = TASKS[key]
    await q.edit_message_text(
        f"{task['name']}\n\n🔗 {task['url']}\nSend secret code to complete."
    )

async def error_handler(update, context):
    print("ERROR:", context.error)

# ================= FLASK + WEBHOOK =================
flask_app = Flask(__name__)
application = Application.builder().token(BOT_TOKEN).build()

application.add_handler(CommandHandler("start", start))
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, messages))
application.add_handler(CallbackQueryHandler(callbacks))
application.add_error_handler(error_handler)

@flask_app.route("/", methods=["GET"])
def home():
    return "Bot running"

@flask_app.route("/webhook", methods=["POST"])
async def webhook():
    update = Update.de_json(request.get_json(force=True), application.bot)
    await application.process_update(update)
    return "OK"

# Webhook set once on start
application.bot.set_webhook(f"{RENDER_URL}/webhook")
