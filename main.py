import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

from . import config
from . import db
from . import quest
from . import trade

# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- Command Handlers ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Sends a welcome message when the /start command is issued."""
    user = update.effective_user
    await update.message.reply_html(
        rf"Greetings, {user.mention_html()}! I am Lunura, your guide on this crypto quest. "
        "Use /quest to begin your journey or /help to see all commands."
    )

async def quest_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handler for the /quest command. Calls the quest module."""
    await quest.start_quest_flow(update, context)

async def crypto_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handler for the /crypto command. Calls the trade module."""
    await trade.crypto_scan_command(update, context)

async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handler for the /status command. Will query the database."""
    user_id = update.effective_user.id
    open_trades = db.get_open_trades(user_id)

    if not open_trades:
        await update.message.reply_text("You have no open trades. Use /crypto to find an opportunity.")
        return

    message = "📜 **Your Open Quests (Trades):**\n\n"
    for trade in open_trades:
        # The target price is +25% as per your plan
        target_price = trade['buy_price'] * (1 + config.PROFIT_TARGET_PERCENTAGE / 100)
        message += (
            f"🔹 **{trade['coin_symbol']}** (ID: {trade['id']})\n"
            f"   - Bought at: `${trade['buy_price']:,.2f}`\n"
            f"   - Target Sell: `${target_price:,.2f}`\n\n")
    await update.message.reply_text(message, parse_mode='Markdown')

async def resonate_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Static handler for the /resonate command."""
    await update.message.reply_text(
        "Listen to the market's hum. Patience is a virtue. The right moment will reveal itself."
    )

async def safety_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Static handler for the /safety command."""
    await update.message.reply_text(
        "Protect your capital like a sacred treasure. Never invest more than you are willing to lose. "
        "A stop-loss is your shield in the volatile realm of crypto."
    )

async def hubspeedy_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Static handler for the /hubspeedy command."""
    await update.message.reply_text("For more advanced tools and community, check out our main application! [Link Here]")

async def balance_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handler for the /balance command. Calls the trade module."""
    await trade.balance_command(update, context)

def main() -> None:
    """Start the bot."""
    db.initialize_database()

    application = Application.builder().token(config.TELEGRAM_BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("quest", quest_command))
    application.add_handler(CommandHandler("crypto", crypto_command))
    application.add_handler(CommandHandler("status", status_command))
    application.add_handler(CommandHandler("balance", balance_command))
    application.add_handler(CommandHandler("resonate", resonate_command))
    application.add_handler(CommandHandler("safety", safety_command))
    application.add_handler(CommandHandler("hubspeedy", hubspeedy_command))

    logger.info("Starting bot...")
    application.run_polling()

if __name__ == "__main__":
    main()