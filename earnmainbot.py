import os
from datetime import datetime, timedelta

import psycopg
from psycopg_pool import ConnectionPool
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
    ContextTypes,
    filters,
)

# ================= CONFIG =================
BOT_TOKEN = os.environ["BOT_TOKEN"]
DATABASE_URL = os.environ["DATABASE_URL"]
ADMIN_ID = int(os.environ.get("ADMIN_ID", "0"))

TASK_REWARD = 0.10
REF_REWARD = 0.50
TASK_RESET_TIME = timedelta(hours=24)

# ================= DB POOL (FIX) =================
db_pool = ConnectionPool(
    DATABASE_URL,
    min_size=1,
    max_size=5,
    timeout=30,
)

def init_db():
    with db_pool.connection() as conn:
        with conn.cursor() as cur:
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
                task TEXT,
                completed_at TIMESTAMP,
                UNIQUE(user_id, task)
            )
            """)
            cur.execute("""
            CREATE TABLE IF NOT EXISTS withdrawals (
                user_id BIGINT,
                method TEXT,
                info TEXT,
                amount NUMERIC DEFAULT 0,
                status TEXT DEFAULT 'Pending',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """)

init_db()

# ================= TASKS =================
TASKS = {
    "watch": {"name": "🎥 Watch Video", "url": "https://example.com", "secret": "VIDEO123"},
    "visit": {"name": "🌐 Visit Website", "url": "https://example.com", "secret": "VISIT123"},
    "airdrop": {"name": "🪂 Claim Airdrop", "url": "https://example.com", "secret": "AIRDROP123"},
}

# ================= HELPERS (SAFE) =================
def db_exec(query, params=None, fetchone=False, fetchall=False):
    try:
        with db_pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, params or ())
                if fetchone:
                    return cur.fetchone()
                if fetchall:
                    return cur.fetchall()
    except Exception as e:
        print("DB ERROR:", e)
        return None

def ref_code(uid):
    return f"REF{uid}"

def add_user(uid, referred_by=None):
    db_exec(
        """INSERT INTO users (user_id, ref_code, referred_by)
           VALUES (%s,%s,%s)
           ON CONFLICT (user_id) DO NOTHING""",
        (uid, ref_code(uid), referred_by),
    )

def add_balance(uid, amount):
    db_exec(
        "UPDATE users SET balance = balance + %s WHERE user_id=%s",
        (amount, uid),
    )

def balance(uid):
    row = db_exec(
        "SELECT balance FROM users WHERE user_id=%s",
        (uid,),
        fetchone=True,
    )
    return float(row[0]) if row else 0.0

def can_do_task(uid, task):
    row = db_exec(
        "SELECT completed_at FROM tasks WHERE user_id=%s AND task=%s",
        (uid, task),
        fetchone=True,
    )
    if not row:
        return True
    return datetime.utcnow() - row[0] >= TASK_RESET_TIME

def complete_task(uid, task):
    db_exec(
        """INSERT INTO tasks (user_id, task, completed_at)
           VALUES (%s,%s,%s)
           ON CONFLICT (user_id, task)
           DO UPDATE SET completed_at=%s""",
        (uid, task, datetime.utcnow(), datetime.utcnow()),
    )
    add_balance(uid, TASK_REWARD)

def get_withdraw_status(uid):
    rows = db_exec(
        """SELECT method, amount, status, created_at
           FROM withdrawals
           WHERE user_id=%s
           ORDER BY created_at DESC
           LIMIT 5""",
        (uid,),
        fetchall=True,
    )
    if not rows:
        return "No withdrawals yet."
    return "\n".join(
        f"{r[0]} | {float(r[1]):.2f} USD | {r[2]} | {r[3].strftime('%Y-%m-%d %H:%M')}"
        for r in rows
    )

# ================= MENUS =================
menu = ReplyKeyboardMarkup(
    [
        ["💰 Earn Crypto", "📋 Tasks"],
        ["👥 Refer & Earn", "📊 My Stats"],
        ["💸 Withdraw"],
        ["🧾 Proof Payment", "❓ Help"],
    ],
    resize_keyboard=True,
)

def task_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(t["name"], callback_data=f"task_{k}")]
        for k, t in TASKS.items()
    ])

# ================= START =================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    referred_by = context.args[0] if context.args else None
    add_user(uid, referred_by)
    await update.message.reply_text(
        "👋 Welcome!\n\nComplete tasks and earn crypto.",
        reply_markup=menu,
    )

# ================= MESSAGE HANDLER =================
async def messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return

    uid = update.effective_user.id
    text = update.message.text.strip()

    if text in ("💰 Earn Crypto", "📋 Tasks"):
        await update.message.reply_text("Choose a task:", reply_markup=task_keyboard())
        return

    if text == "📊 My Stats":
        stats = (
            f"📊 *Your Stats*\n\n"
            f"💰 Balance: {balance(uid):.2f} USD\n\n"
            f"🔹 Tasks:\n" +
            "\n".join(
                f"{t['name']}: {'✅' if not can_do_task(uid, k) else '❌'}"
                for k, t in TASKS.items()
            ) +
            "\n\n💸 Withdrawals:\n" +
            get_withdraw_status(uid)
        )
        await update.message.reply_text(stats, parse_mode="Markdown")
        return

# ================= CALLBACK =================
async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()

    if q.data.startswith("task_"):
        task = q.data.replace("task_", "")
        data = TASKS[task]
        await q.edit_message_text(
            f"{data['name']}\n\n🔗 {data['url']}\n\nSend the secret code."
        )

# ================= ERROR HANDLER =================
async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    print("BOT ERROR:", context.error)

# ================= RUN =================
if __name__ == "__main__":
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(callback_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, messages))
    app.add_error_handler(error_handler)

    app.run_polling(drop_pending_updates=True)
