import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes

BOT_TOKEN = os.environ.get("BOT_TOKEN")

# /start command shows the main menu
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("💰 Earn Crypto", callback_data='earn')],
        [InlineKeyboardButton("📋 Tasks", callback_data='tasks')],
        [InlineKeyboardButton("👥 Refer & Earn", callback_data='refer')],
        [InlineKeyboardButton("💸 Withdraw", callback_data='withdraw')],
        [InlineKeyboardButton("📊 My Balance", callback_data='balance')],
        [InlineKeyboardButton("🧾 Proof Payment", callback_data='proof')],
        [InlineKeyboardButton("❓ Help", callback_data='help')],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Welcome! Choose an option:", reply_markup=reply_markup)

# Handle button clicks
async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()  # acknowledge click

    if query.data == "earn":
        await query.edit_message_text("💰 Earn Crypto:\nComplete tasks and earn crypto daily!")
    elif query.data == "tasks":
        await query.edit_message_text("📋 Tasks:\n1. Watch videos\n2. Visit websites\n3. Complete surveys")
    elif query.data == "refer":
        await query.edit_message_text("👥 Refer & Earn:\nShare your referral link and earn rewards!")
    elif query.data == "withdraw":
        await query.edit_message_text("💸 Withdraw:\nClick here to withdraw your balance to your wallet.")
    elif query.data == "balance":
        await query.edit_message_text("📊 My Balance:\nYour current balance is: 0.0 Crypto")
    elif query.data == "proof":
        # You can replace this URL with your own proof channel or images
        await query.edit_message_text("🧾 Proof Payment:\nCheck our proof payments here:\nhttps://t.me/your_payment_proof_channel")
    elif query.data == "help":
        await query.edit_message_text("❓ Help:\nIf you face any issue, contact admin: @YourAdminUsername")

if __name__ == "__main__":
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button))
    print("Bot is running with full menu...")
    app.run_polling()
