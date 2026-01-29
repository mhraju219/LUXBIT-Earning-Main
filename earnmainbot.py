

import os from datetime import datetime, timedelta

import psycopg from flask import Flask from telegram import ( Update, ReplyKeyboardMarkup, InlineKeyboardButton, InlineKeyboardMarkup, ) from telegram.ext import ( ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters, )

================= CONFIG =================

BOT_TOKEN = os.environ["BOT_TOKEN"] DATABASE_URL = os.environ["DATABASE_URL"] WEBHOOK_URL = os.environ["WEBHOOK_URL"]  # https://your-app.onrender.com PORT = int(os.environ.get("PORT", 10000))

TASK_REWARD = 0.10 REF_REWARD = 0.50 TASK_RESET_TIME = timedelta(hours=24)

================= TASKS =================

TASKS = { "watch": { "name": "🎥 Watch Video", "url": "https://example.com/video", "secret": "VIDEO123", }, "visit": { "name": "🌐 Visit Website", "url": "https://example.com", "secret": "VISIT123", }, "airdrop": { "name": "🪂 Claim Airdrop", "url": "https://example.com/airdrop", "secret": "AIRDROP123", }, }

================= FLASK =================

app_flask = Flask(name)

@app_flask.route("/") def home(): return "Bot is running"

================= DATABASE =================

conn = psycopg.connect(DATABASE_URL) cur = conn.cursor()

cur.execute(""" CREATE TABLE IF NOT EXISTS users ( user_id BIGINT PRIMARY KEY, balance NUMERIC DEFAULT 0, ref_code TEXT UNIQUE, referred_by TEXT, referral_paid BOOLEAN DEFAULT FALSE, withdraw_status TEXT DEFAULT 'None' ) """)

cur.execute(""" CREATE TABLE IF NOT EXISTS tasks ( user_id BIGINT, task TEXT, completed_at TIMESTAMP, UNIQUE(user_id, task) ) """)

conn.commit()

================= HELPERS =================

def ref_code(uid): return f"REF{uid}"

def add_user(uid, referred_by=None): cur.execute( """ INSERT INTO users (user_id, ref_code, referred_by) VALUES (%s, %s, %s) ON CONFLICT (user_id) DO NOTHING """, (uid, ref_code(uid), referred_by), ) conn.commit()

def add_balance(uid, amount): cur.execute( "UPDATE users SET balance = balance + %s WHERE user_id=%s", (amount, uid), ) conn.commit()

def get_user(uid): cur.execute( "SELECT balance, withdraw_status, ref_code FROM users WHERE user_id=%s", (uid,), ) return cur.fetchone()

def can_do_task(uid, task): cur.execute( "SELECT completed_at FROM tasks WHERE user_id=%s AND task=%s", (uid, task), ) row = cur.fetchone() if not row or not row[0]: return True return datetime.utcnow() - row[0] >= TASK_RESET_TIME

def complete_task(uid, task): cur.execute( """ INSERT INTO tasks (user_id, task, completed_at) VALUES (%s, %s, %s) ON CONFLICT (user_id, task) DO UPDATE SET completed_at=%s """, (uid, task, datetime.utcnow(), datetime.utcnow()), ) add_balance(uid, TASK_REWARD) conn.commit()

================= MENUS =================

menu = ReplyKeyboardMarkup( [ ["💰 Earn Crypto", "📋 Tasks"], ["👥 Refer & Earn", "💸 Withdraw", "📊 My Stats"], ["🧾 Proof Payment", "❓ Help"], ], resize_keyboard=True, )

def task_keyboard(): return InlineKeyboardMarkup([ [InlineKeyboardButton(TASKS["watch"]["name"], callback_data="task_watch")], [InlineKeyboardButton(TASKS["visit"]["name"], callback_data="task_visit")], [InlineKeyboardButton(TASKS["airdrop"]["name"], callback_data="task_airdrop")], ])

================= HANDLERS =================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE): uid = update.effective_user.id referred_by = context.args[0] if context.args else None add_user(uid, referred_by)

await update.message.reply_text(
    "👋 Welcome!\nComplete tasks and earn crypto.",
    reply_markup=menu,
)

async def messages(update: Update, context: ContextTypes.DEFAULT_TYPE): uid = update.effective_user.id text = update.message.text.strip()

if text in ["💰 Earn Crypto", "📋 Tasks"]:
    await update.message.reply_text("Choose a task:", reply_markup=task_keyboard())
    return

if text == "📊 My Stats":
    bal, status, ref = get_user(uid)
    icon = {
        "None": "➖ No Request",
        "Pending": "⏳ Pending",
        "Approved": "✅ Approved",
        "Rejected": "❌ Rejected",
    }.get(status, "➖ No Request")

    await update.message.reply_text(
        "📊 *My Stats*\n\n"
        f"💰 Balance: `{float(bal):.2f} USD`\n"
        f"💸 Withdraw Status: {icon}\n"
        f"🔗 Referral Code: `{ref}`",
        parse_mode="Markdown",
    )
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

# ===== SECRET CODE CHECK =====
for task, data in TASKS.items():
    if text == data["secret"]:
        if not can_do_task(uid, task):
            await update.message.reply_text("⏳ Task already completed. Try after 24h.")
            return

        complete_task(uid, task)

        await update.message.reply_text(
            f"🎉 Task Completed!\n+{TASK_REWARD} USD added."
        )
        return

if len(text) <= 20:
    await update.message.reply_text("❌ Invalid secret code.")

async def task_callback(update: Update, context: ContextTypes.DEFAULT_TYPE): q = update.callback_query await q.answer()

task = q.data.replace("task_", "")
data = TASKS[task]

await q.edit_message_text(
    f"{data['name']}\n\n"
    f"🔗 {data['url']}\n\n"
    "Send the secret code here after completion."
)

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE): print("Error:", context.error)

================= RUN (WEBHOOK ONLY) =================

if name == "main": app = ApplicationBuilder().token(BOT_TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(CallbackQueryHandler(task_callback, pattern="^task_"))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, messages))
app.add_error_handler(error_handler)

app.run_webhook(
    listen="0.0.0.0",
    port=PORT,
    url_path=BOT_TOKEN,
    webhook_url=f"{WEBHOOK_URL}/{BOT_TOKEN}",
)
