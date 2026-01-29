import os
import threading
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
    filters,
    ContextTypes,
)

# ---------------- CONFIG ----------------
BOT_TOKEN = os.environ.get("BOT_TOKEN")
DATABASE_URL = os.environ.get("DATABASE_URL")
PORT = int(os.environ.get("PORT", 10000))

TASK_REWARD = 0.10
REF_REWARD = 0.50

# ---------------- Flask (Render Port Fix) ----------------
app_flask = Flask(__name__)

@app_flask.route("/")
def home():
    return "Bot is running!"

threading.Thread(
    target=lambda: app_flask.run(host="0.0.0.0", port=PORT),
    daemon=True
).start()

# ---------------- PostgreSQL ----------------
conn = psycopg.connect(DATABASE_URL)
cur = conn.cursor()

cur.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id BIGINT PRIMARY KEY,
    balance NUMERIC DEFAULT 0,
    ref_code TEXT UNIQUE,
    referred_by TEXT
)
""")

cur.execute("""
CREATE TABLE IF NOT EXISTS tasks (
    user_id BIGINT,
    task TEXT,
    UNIQUE(user_id, task)
)
""")

conn.commit()

# ---------------- Helpers ----------------
def generate_ref_code(user_id):
    return f"REF{user_id}"

def add_user(user_id, referred_by=None):
    cur.execute(
        """
        INSERT INTO users (user_id, ref_code, referred_by)
        VALUES (%s, %s, %s)
        ON CONFLICT (user_id) DO NOTHING
        """,
        (user_id, generate_ref_code(user_id), referred_by)
    )
    conn.commit()

def add_balance(user_id, amount):
    cur.execute(
        "UPDATE users SET balance = balance + %s WHERE user_id=%s",
        (amount, user_id)
    )
    conn.commit()

def get_balance(user_id):
    cur.execute("SELECT balance FROM users WHERE user_id=%s", (user_id,))
    return cur.fetchone()[0]

def task_done(user_id, task):
    cur.execute(
        "SELECT 1 FROM tasks WHERE user_id=%s AND task=%s",
        (user_id, task)
    )
    return cur.fetchone() is not None

def complete_task(user_id, task):
    cur.execute(
        "INSERT INTO tasks (user_id, task) VALUES (%s, %s)",
        (user_id, task)
    )
    add_balance(user_id, TASK_REWARD)
    conn.commit()

# ---------------- Keyboard Menu ----------------
menu = ReplyKeyboardMarkup([
    ["💰 Earn Crypto", "📋 Tasks"],
    ["👥 Refer & Earn", "💸 Withdraw"],
    ["📊 My Balance", "🧾 Proof Payment"],
    ["❓ Help"]
], resize_keyboard=True)

# ---------------- Commands ----------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    args = context.args

    referred_by = None
    if args:
        referred_by = args[0]
        cur.execute("SELECT user_id FROM users WHERE ref_code=%s", (referred_by,))
        ref_user = cur.fetchone()
        if ref_user:
            add_balance(ref_user[0], REF_REWARD)

    add_user(user_id, referred_by)

    await update.message.reply_text(
        "Welcome! Use the menu below 👇",
        reply_markup=menu
    )

# ---------------- Messages ----------------
async def messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text

    if text == "📋 Tasks":
        buttons = [
            [InlineKeyboardButton("🎥 Watch Video", callback_data="watch")],
            [InlineKeyboardButton("📝 Survey", callback_data="survey")],
            [InlineKeyboardButton("🌐 Visit Website", callback_data="visit")]
        ]
        await update.message.reply_text(
            "Choose a task:",
            reply_markup=InlineKeyboardMarkup(buttons)
        )
        return

    if text == "📊 My Balance":
        bal = get_balance(user_id)
        await update.message.reply_text(f"💰 Balance: {bal:.2f} USD")
        return

    if text == "👥 Refer & Earn":
        await update.message.reply_text(
            f"Invite friends & earn {REF_REWARD} USD\n\n"
            f"https://t.me/YOUR_BOT_USERNAME?start={generate_ref_code(user_id)}"
        )
        return

    if text == "🧾 Proof Payment":
        await update.message.reply_text(
            "Proof channel:\nhttps://t.me/your_payment_proof_channel"
        )
        return

    await update.message.reply_text("Use menu 👇", reply_markup=menu)

# ---------------- Task Buttons ----------------
async def task_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    task = query.data
    await query.answer()

    if task_done(user_id, task):
        await query.edit_message_text("❌ Task already completed.")
        return

    complete_task(user_id, task)

    links = {
        "watch": "🎥 Watch:\nhttps://example.com/video",
        "survey": "📝 Survey:\nhttps://example.com/survey",
        "visit": "🌐 Visit:\nhttps://example.com/site",
    }

    await query.edit_message_text(
        f"✅ Task completed!\n"
        f"+{TASK_REWARD} USD added\n\n{links[task]}"
    )

# ---------------- Run ----------------
if __name__ == "__main__":
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, messages))
    app.add_handler(CallbackQueryHandler(task_handler))
    print("Bot running with PostgreSQL")
    app.run_polling()
