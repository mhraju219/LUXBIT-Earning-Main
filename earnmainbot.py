import os
import sqlite3
from flask import Flask, request
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup
)
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
    MessageHandler,
    filters
)

# ================== CONFIG ==================
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))
PROOF_CHANNEL_ID = int(os.getenv("PROOF_CHANNEL_ID"))

PORT = int(os.environ.get("PORT", 10000))

# ================== DATABASE ==================
conn = sqlite3.connect("bot.db", check_same_thread=False)
cur = conn.cursor()

cur.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    balance INTEGER DEFAULT 0
)
""")

cur.execute("""
CREATE TABLE IF NOT EXISTS withdraws (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    amount INTEGER,
    wallet TEXT,
    status TEXT
)
""")

conn.commit()

# ================== BOT ==================
app_bot = Application.builder().token(BOT_TOKEN).build()

# ================== HANDLERS ==================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    cur.execute("INSERT OR IGNORE INTO users(user_id) VALUES(?)", (uid,))
    conn.commit()

    kb = [
        [InlineKeyboardButton("💰 Earn", callback_data="earn")],
        [InlineKeyboardButton("📊 Balance", callback_data="balance")],
        [InlineKeyboardButton("💸 Withdraw", callback_data="withdraw")]
    ]
    if uid == ADMIN_ID:
        kb.append([InlineKeyboardButton("👑 Admin", callback_data="admin")])

    await update.message.reply_text(
        "🚀 Welcome to Earning Bot",
        reply_markup=InlineKeyboardMarkup(kb)
    )

async def buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    uid = q.from_user.id
    await q.answer()

    if q.data == "earn":
        cur.execute("UPDATE users SET balance = balance + 1 WHERE user_id=?", (uid,))
        conn.commit()
        await q.edit_message_text("✅ You earned 1 point")

    elif q.data == "balance":
        bal = cur.execute(
            "SELECT balance FROM users WHERE user_id=?", (uid,)
        ).fetchone()[0]
        await q.edit_message_text(f"💰 Balance: {bal}")

    elif q.data == "withdraw":
        bal = cur.execute(
            "SELECT balance FROM users WHERE user_id=?", (uid,)
        ).fetchone()[0]
        if bal < 50:
            await q.edit_message_text("❌ Minimum withdraw is 50 points")
        else:
            context.user_data["withdraw"] = True
            await q.edit_message_text("✍️ Send your Binance UID")

    elif q.data == "admin" and uid == ADMIN_ID:
        req = cur.execute(
            "SELECT id,user_id,amount,wallet FROM withdraws WHERE status='pending'"
        ).fetchone()

        if not req:
            await q.edit_message_text("✅ No pending withdraws")
        else:
            wid, user, amt, wallet = req
            kb = [
                [
                    InlineKeyboardButton("✅ Approve", callback_data=f"approve_{wid}"),
                    InlineKeyboardButton("❌ Reject", callback_data=f"reject_{wid}")
                ]
            ]
            await q.edit_message_text(
                f"💸 Withdraw Request\n\n"
                f"User: {user}\n"
                f"Amount: {amt}\n"
                f"Binance UID: {wallet}",
                reply_markup=InlineKeyboardMarkup(kb)
            )

    elif q.data.startswith("approve_"):
        wid = q.data.split("_")[1]
        cur.execute("UPDATE withdraws SET status='approved' WHERE id=?", (wid,))
        conn.commit()

        user_id, amount, wallet = cur.execute(
            "SELECT user_id,amount,wallet FROM withdraws WHERE id=?", (wid,)
        ).fetchone()

        proof = f"""
✅ *Withdraw Paid*

👤 User: `{user_id}`
💰 Amount: `{amount}`
🏦 Method: Binance UID
📬 UID: `{wallet}`

🔥 Trusted Bot
"""
        await context.bot.send_message(
            PROOF_CHANNEL_ID,
            proof,
            parse_mode="Markdown"
        )
        await context.bot.send_message(
            user_id,
            "✅ Your withdraw has been paid!\n📢 Proof posted."
        )
        await q.edit_message_text("✅ Approved & Proof Posted")

    elif q.data.startswith("reject_"):
        wid = q.data.split("_")[1]
        cur.execute("UPDATE withdraws SET status='rejected' WHERE id=?", (wid,))
        conn.commit()
        await q.edit_message_text("❌ Withdraw Rejected")

async def wallet_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get("withdraw"):
        uid = update.effective_user.id
        wallet = update.message.text

        bal = cur.execute(
            "SELECT balance FROM users WHERE user_id=?", (uid,)
        ).fetchone()[0]

        cur.execute("UPDATE users SET balance=0 WHERE user_id=?", (uid,))
        cur.execute(
            "INSERT INTO withdraws(user_id,amount,wallet,status) VALUES(?,?,?,?)",
            (uid, bal, wallet, "pending")
        )
        conn.commit()

        context.user_data["withdraw"] = False
        await update.message.reply_text("✅ Withdraw request submitted")

# ================== ADD HANDLERS ==================
app_bot.add_handler(CommandHandler("start", start))
app_bot.add_handler(CallbackQueryHandler(buttons))
app_bot.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, wallet_input))

# ================== FLASK WEBHOOK ==================
flask_app = Flask(__name__)

@flask_app.route("/", methods=["GET"])
def index():
    return "Bot is running"

@flask_app.route(f"/{BOT_TOKEN}", methods=["POST"])
def webhook():
    update = Update.de_json(request.get_json(force=True), app_bot.bot)
    app_bot.update_queue.put_nowait(update)
    return "ok"

# ================== RUN ==================
if __name__ == "__main__":
    app_bot.initialize()
    app_bot.start()
    flask_app.run(host="0.0.0.0", port=PORT)
