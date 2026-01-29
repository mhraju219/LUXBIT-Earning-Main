import os
import threading
from flask import Flask
from telegram import Update, ReplyKeyboardMarkup, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes

BOT_TOKEN = os.environ.get("BOT_TOKEN")
PORT = int(os.environ.get("PORT", 10000))  # Render port

# ---------------- Flask server for Render port ----------------
app_flask = Flask(__name__)

@app_flask.route("/")
def home():
    return "Bot is running with keyboard menu + tasks submenu!"

def run_flask():
    app_flask.run(host="0.0.0.0", port=PORT)

flask_thread = threading.Thread(target=run_flask)
flask_thread.start()

# ---------------- Telegram Bot ----------------
# Main keyboard menu
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

# Handle keyboard messages
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text

    if text == "📋 Tasks":
        # Show inline buttons for tasks
        task_keyboard = [
            [InlineKeyboardButton("🎥 Watch Video", callback_data="watch_video")],
            [InlineKeyboardButton("📝 Complete Survey", callback_data="survey")],
            [InlineKeyboardButton("🌐 Visit Website", callback_data="visit_website")]
        ]
        reply_markup_inline = InlineKeyboardMarkup(task_keyboard)
        await update.message.reply_text("📋 Choose a task:", reply_markup=reply_markup_inline)

    else:
        # Other main menu options
        responses = {
            "💰 Earn Crypto": "💰 Earn Crypto:\nComplete tasks and earn crypto daily!",
            "👥 Refer & Earn": "👥 Refer & Earn:\nShare your referral link and earn rewards!",
            "💸 Withdraw": "💸 Withdraw:\nClick here to withdraw your balance to your wallet.",
            "📊 My Balance": "📊 My Balance:\nYour current balance is: 0.0 Crypto",
            "🧾 Proof Payment": "🧾 Proof Payment:\nCheck our proof payments here:\nhttps://t.me/your_payment_proof_channel",
            "❓ Help": "❓ Help:\nIf you face any issue, contact admin: @YourAdminUsername"
        }
        await update.message.reply_text(responses.get(text, "Please choose an option from the menu."), reply_markup=reply_markup)

# Handle inline button clicks
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "watch_video":
        # Show an advertising link
        await query.edit_message_text(
            "🎥 Watch this video ad to earn rewards:\nhttps://example.com/ad_video"
        )
    elif query.data == "survey":
        await query.edit_message_text(
            "📝 Complete this survey:\nhttps://example.com/survey"
        )
    elif query.data == "visit_website":
        await query.edit_message_text(
            "🌐 Visit this website:\nhttps://example.com/visit"
        )
    else:
        await query.edit_message_text("Unknown option!")

# ---------------- Run Bot ----------------
if __name__ == "__main__":
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(CallbackQueryHandler(button_handler))
    print("Bot is running with keyboard + tasks submenu + Flask server...")
    app.run_polling()
