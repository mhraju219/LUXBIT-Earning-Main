import os
import threading
from flask import Flask
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

BOT_TOKEN = os.environ.get("BOT_TOKEN")
PORT = int(os.environ.get("PORT", 10000))  # Render provides PORT variable

# ------------------- Flask web server (for Render port) -------------------
app_flask = Flask(__name__)

@app_flask.route("/")
def home():
    return "Bot is running with keyboard menu!"

def run_flask():
    app_flask.run(host="0.0.0.0", port=PORT)

# Start Flask server in a separate thread
flask_thread = threading.Thread(target=run_flask)
flask_thread.start()

# ------------------- Telegram Bot -------------------

# Keyboard menu
keyboard = [
    ["💰 Earn Crypto", "📋 Tasks"],
    ["👥 Refer & Earn", "💸 Withdraw"],
    ["📊 My Balance", "🧾 Proof Payment"],
    ["❓ Help"]
]
reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

# /start command
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Welcome! Choose an option from the menu below:",
        reply_markup=reply_markup
    )

# Handle user messages
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text

    responses = {
        "💰 Earn Crypto": "💰 Earn Crypto:\nComplete tasks and earn crypto daily!",
        "📋 Tasks": "📋 Tasks:\n1. Watch videos\n2. Visit websites\n3. Complete surveys",
        "👥 Refer & Earn": "👥 Refer & Earn:\nShare your referral link and earn rewards!",
        "💸 Withdraw": "💸 Withdraw:\nClick here to withdraw your balance to your wallet.",
        "📊 My Balance": "📊 My Balance:\nYour current balance is: 0.0 Crypto",
        "🧾 Proof Payment": "🧾 Proof Payment:\nCheck our proof payments here:\nhttps://t.me/your_payment_proof_channel",
        "❓ Help": "❓ Help:\nIf you face any issue, contact admin: @YourAdminUsername"
    }

    await update.message.reply_text(responses.get(text, "Please choose an option from the menu below."), reply_markup=reply_markup)

# ------------------- Run Bot -------------------
if __name__ == "__main__":
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    print("Bot is running with keyboard menu + Flask server on Render...")
    app.run_polling()
