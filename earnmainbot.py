import os
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

BOT_TOKEN = os.environ.get("BOT_TOKEN")

# Define keyboard menu
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

# Handle user messages (keyboard input)
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text

    if text == "💰 Earn Crypto":
        await update.message.reply_text("💰 Earn Crypto:\nComplete tasks and earn crypto daily!")
    elif text == "📋 Tasks":
        await update.message.reply_text("📋 Tasks:\n1. Watch videos\n2. Visit websites\n3. Complete surveys")
    elif text == "👥 Refer & Earn":
        await update.message.reply_text("👥 Refer & Earn:\nShare your referral link and earn rewards!")
    elif text == "💸 Withdraw":
        await update.message.reply_text("💸 Withdraw:\nClick here to withdraw your balance to your wallet.")
    elif text == "📊 My Balance":
        await update.message.reply_text("📊 My Balance:\nYour current balance is: 0.0 Crypto")
    elif text == "🧾 Proof Payment":
        await update.message.reply_text("🧾 Proof Payment:\nCheck our proof payments here:\nhttps://t.me/your_payment_proof_channel")
    elif text == "❓ Help":
        await update.message.reply_text("❓ Help:\nIf you face any issue, contact admin: @YourAdminUsername")
    else:
        await update.message.reply_text("Please choose an option from the menu below.", reply_markup=reply_markup)

if __name__ == "__main__":
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    print("Bot is running with keyboard menu...")
    app.run_polling()
