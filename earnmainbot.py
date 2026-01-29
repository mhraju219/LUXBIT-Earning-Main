import os import logging import sqlite3 from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup from telegram.ext import ( ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes, )

---------------- CONFIG ----------------

BOT_TOKEN = os.getenv("BOT_TOKEN") CHANNEL_ID = os.getenv("CHANNEL_ID")  # withdrawal proof channel WEBHOOK_URL = os.getenv("WEBHOOK_URL")  # https://your-app.onrender.com PORT = int(os.getenv("PORT", "10000"))

Optional Binance (safe if empty)

BINANCE_API_KEY = os.getenv("BINANCE_API_KEY", "") BINANCE_API_SECRET = os.getenv("BINANCE_API_SECRET", "")

try: from binance.client import Client except Exception: Client = None

binance_client = None if BINANCE_API_KEY and BINANCE_API_SECRET and Client: binance_client = Client(BINANCE_API_KEY, BINANCE_API_SECRET)

---------------- LOGGING ----------------

logging.basicConfig( format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO, ) logger = logging.getLogger(name)

---------------- DATABASE ----------------

DB_FILE = "earnbot.db"

def init_db(): conn = sqlite3.connect(DB_FILE) c = conn.cursor() c.execute( """ CREATE TABLE IF NOT EXISTS users ( user_id INTEGER PRIMARY KEY, balance REAL DEFAULT 0, ref_by INTEGER ) """ ) conn.commit() conn.close()

def get_user(user_id: int): conn = sqlite3.connect(DB_FILE) c = conn.cursor() c.execute("SELECT user_id, balance FROM users WHERE user_id=?", (user_id,)) row = c.fetchone() if not row: c.execute("INSERT INTO users (user_id, balance) VALUES (?, 0)", (user_id,)) conn.commit() row = (user_id, 0) conn.close() return row

def add_balance(user_id: int, amount: float): conn = sqlite3.connect(DB_FILE) c = conn.cursor() c.execute( "UPDATE users SET balance = balance + ? WHERE user_id=?", (amount, user_id), ) conn.commit() conn.close()

---------------- MENUS ----------------

def main_menu(): keyboard = [ [InlineKeyboardButton("💰 Tasks", callback_data="tasks")], [InlineKeyboardButton("👥 Referral", callback_data="referral")], [InlineKeyboardButton("💸 Withdraw", callback_data="withdraw")], [InlineKeyboardButton("🧾 Withdrawal Proof", callback_data="proof")], [InlineKeyboardButton("❓ Help", callback_data="help")], ] return InlineKeyboardMarkup(keyboard)

---------------- HANDLERS ----------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE): user = update.effective_user get_user(user.id) await update.message.reply_text( f"👋 Welcome {user.first_name}!\n\nEarn crypto by completing tasks.", reply_markup=main_menu(), )

async def menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE): query = update.callback_query await query.answer() user_id = query.from_user.id

if query.data == "tasks":
    await query.edit_message_text(
        "📋 Available Tasks:\n\n"
        "• Join channels\n"
        "• Daily bonus\n\n"
        "(Demo task: +0.5 balance added)",
        reply_markup=main_menu(),
    )
    add_balance(user_id, 0.5)

elif query.data == "referral":
    ref_link = f"https://t.me/{context.bot.username}?start={user_id}"
    await query.edit_message_text(
        f"👥 Referral System\n\n"
        f"Invite friends and earn!\n\n"
        f"Your link:\n{ref_link}",
        reply_markup=main_menu(),
    )

elif query.data == "withdraw":
    _, balance = get_user(user_id)
    await query.edit_message_text(
        f"💸 Withdraw\n\nYour balance: {balance:.2f}\n\n"
        "Minimum withdraw: 10",
        reply_markup=main_menu(),
    )

elif query.data == "proof":
    if CHANNEL_ID:
        await query.edit_message_text(
            f"🧾 Withdrawal Proofs:\n\nSee: {CHANNEL_ID}",
            reply_markup=main_menu(),
        )
    else:
        await query.edit_message_text(
            "❌ Proof channel not configured.", reply_markup=main_menu()
        )

elif query.data == "help":
    await query.edit_message_text(
        "❓ Help\n\n"
        "• Complete tasks to earn\n"
        "• Invite friends\n"
        "• Withdraw when minimum reached",
        reply_markup=main_menu(),
    )

---------------- MAIN ----------------

def main(): init_db()

app = ApplicationBuilder().token(BOT_TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(CallbackQueryHandler(menu_handler))

if WEBHOOK_URL:
    logger.info("Starting in WEBHOOK mode")
    app.run_webhook(
        listen="0.0.0.0",
        port=PORT,
        url_path=BOT_TOKEN,
        webhook_url=f"{WEBHOOK_URL}/{BOT_TOKEN}",
    )
else:
    logger.info("Starting in POLLING mode")
    app.run_polling()

if name == "main": main()
