import os import logging import sqlite3 from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, CallbackQueryHandler import requests

==============================

Environment Variables

==============================

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN") CHANNEL_ID = os.getenv("TELEGRAM_CHANNEL_ID") WEBHOOK_URL = os.getenv("WEBHOOK_URL") BINANCE_API_KEY = os.getenv("BINANCE_API_KEY") BINANCE_API_SECRET = os.getenv("BINANCE_API_SECRET") PORT = int(os.getenv("PORT", 8443))

for var_name in ['BOT_TOKEN', 'CHANNEL_ID', 'WEBHOOK_URL', 'BINANCE_API_KEY', 'BINANCE_API_SECRET']: if not globals()[var_name]: raise RuntimeError(f"Missing env var: {var_name}")

==============================

Logging

==============================

logging.basicConfig( format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO, ) logger = logging.getLogger(name)

==============================

Database Setup

==============================

DB_FILE = 'bot_users.db' conn = sqlite3.connect(DB_FILE, check_same_thread=False) cursor = conn.cursor()

Create tables if not exist

cursor.execute(''' CREATE TABLE IF NOT EXISTS users ( user_id INTEGER PRIMARY KEY, balance REAL DEFAULT 0 ) ''')

cursor.execute(''' CREATE TABLE IF NOT EXISTS withdrawals ( id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, amount REAL, status TEXT, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP ) ''') conn.commit()

==============================

Helper Functions

==============================

def get_user_balance(user_id): cursor.execute("SELECT balance FROM users WHERE user_id=?", (user_id,)) row = cursor.fetchone() if row: return row[0] else: cursor.execute("INSERT INTO users (user_id, balance) VALUES (?, 0)", (user_id,)) conn.commit() return 0

def update_user_balance(user_id, amount): balance = get_user_balance(user_id) + amount cursor.execute("UPDATE users SET balance=? WHERE user_id=?", (balance, user_id)) conn.commit() return balance

def add_withdrawal(user_id, amount, status="pending"): cursor.execute("INSERT INTO withdrawals (user_id, amount, status) VALUES (?, ?, ?)" , (user_id, amount, status)) conn.commit()

def fetch_withdrawal_proofs(): cursor.execute("SELECT user_id, amount, status, timestamp FROM withdrawals ORDER BY timestamp DESC LIMIT 5") rows = cursor.fetchall() if not rows: return "No withdrawal proofs yet." text = "📄 Recent withdrawal proofs:\n" for r in rows: text += f"- User {r[0]}: {r[1]} units ({r[2]})\n" return text

==============================

Handlers

==============================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE): keyboard = [ [InlineKeyboardButton("💰 Tasks", callback_data='tasks')], [InlineKeyboardButton("💸 Withdraw", callback_data='withdraw')], [InlineKeyboardButton("👥 Referral", callback_data='referral')], [InlineKeyboardButton("📄 Withdrawal Proof", callback_data='proof')], [InlineKeyboardButton("❓ Help", callback_data='help')] ] reply_markup = InlineKeyboardMarkup(keyboard) await update.message.reply_text("Welcome! Choose an option:", reply_markup=reply_markup)

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE): query = update.callback_query await query.answer()

if query.data == 'tasks':
    await query.edit_message_text("💰 Available tasks:\n- Task 1: Watch a video\n- Task 2: Visit website\n- Task 3: Share referral")
elif query.data == 'withdraw':
    balance = get_user_balance(query.from_user.id)
    await query.edit_message_text(f"💸 Your balance: {balance} units\nUse /withdraw <amount> to withdraw.")
elif query.data == 'referral':
    user_id = query.from_user.id
    await query.edit_message_text(f"👥 Your referral link:\nhttps://t.me/YourBotUsername?start={user_id}")
elif query.data == 'proof':
    await query.edit_message_text(fetch_withdrawal_proofs())
elif query.data == 'help':
    await query.edit_message_text("❓ Help:\nUse menu to navigate tasks, withdraw, referral link, or proof")

async def withdraw_command(update: Update, context: ContextTypes.DEFAULT_TYPE): user_id = update.from_user.id amount = ' '.join(context.args) if context.args else None if not amount or not amount.isdigit(): await update.message.reply_text("❌ Invalid amount. Usage: /withdraw <amount>") return

amount = float(amount)
balance = get_user_balance(user_id)
if amount > balance:
    await update.message.reply_text(f"❌ Insufficient balance. Your balance: {balance}")
    return

# Deduct balance and add withdrawal entry
update_user_balance(user_id, -amount)
add_withdrawal(user_id, amount, status="pending")

# Call Binance withdrawal (mock)
success, message = process_binance_withdrawal(user_id, amount)
if success:
    # Update withdrawal status to completed
    cursor.execute("UPDATE withdrawals SET status=? WHERE user_id=? AND amount=? AND status='pending'",
                   ("completed", user_id, amount))
    conn.commit()
await update.message.reply_text(message)

==============================

Binance integration (mock)

==============================

def process_binance_withdrawal(user_id, amount): try: logger.info(f"Processing withdrawal for user {user_id} amount {amount}") # Replace with real Binance API logic return True, f"✅ Withdrawal of {amount} units successful!" except Exception as e: logger.error(e) return False, f"❌ Withdrawal failed: {str(e)}"

==============================

Main App

==============================

def main(): app = ApplicationBuilder().token(BOT_TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(CallbackQueryHandler(button_handler))
app.add_handler(CommandHandler("withdraw", withdraw_command))

logger.info("Starting bot in Webhook mode with DB and Binance integration")
app.run_webhook(
    listen="0.0.0.0",
    port=PORT,
    url_path=BOT_TOKEN,
    webhook_url=f"{WEBHOOK_URL}"
)

if name == "main": main()
