import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

import config
import db
import quest
import trade

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
        "I can help you find trading opportunities based on RSI and track your progress.\n\n"
        "Use /quest to begin your journey or /help to see all available commands."
    )

async def quest_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handler for the /quest command. Calls the quest module."""
    await quest.start_quest_flow(update, context)

async def crypto_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handler for the /crypto command. Calls the trade module."""
    await trade.crypto_scan_command(update, context)

async def import_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handler for the /import command. Calls the trade module."""
    await trade.import_last_trade_command(update, context)

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
        message += (
            f"🔹 **{trade['coin_symbol']}** (ID: {trade['id']})\n"
            f"   - Bought at: `${trade['buy_price']:,.8f}`\n"
            f"   - ✅ Take Profit: `${trade['take_profit_price']:,.8f}`\n"
            f"   - 🛡️ Stop Loss: `${trade['stop_loss_price']:,.8f}`\n"
            f"   - *Opened: {trade['buy_timestamp']}*\n\n"
        )
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

async def close_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Closes an open trade. Usage: /close <trade_id>"""
    user_id = update.effective_user.id
    try:
        # context.args contains the words after the command, e.g., ['123']
        trade_id = int(context.args[0])
    except (IndexError, ValueError):
        await update.message.reply_text("Please provide a valid trade ID.\nUsage: `/close <trade_id>`", parse_mode='Markdown')
        return

    trade_to_close = db.get_trade_by_id(trade_id=trade_id, user_id=user_id)

    if not trade_to_close:
        await update.message.reply_text("Could not find an open trade with that ID under your name. Check `/status`.", parse_mode='Markdown')
        return

    # Now fetch the price for that specific symbol
    symbol = trade_to_close['coin_symbol']
    current_price = trade.get_current_price(symbol)
    if current_price is None:
        await update.message.reply_text(f"Could not fetch the current price for {symbol} to close the trade. Please try again.")
        return

    success = db.close_trade(trade_id=trade_id, user_id=user_id, sell_price=current_price)

    if success:
        await update.message.reply_text(f"✅ Quest (ID: {trade_id}) for {symbol} has been completed at a price of ${current_price:,.8f}!\n\nUse /review to see your performance.")
    else:
        await update.message.reply_text("An unexpected error occurred while closing the trade.")

async def review_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Reviews the user's completed trade performance."""
    user_id = update.effective_user.id
    closed_trades = db.get_closed_trades(user_id)

    if not closed_trades:
        await update.message.reply_text("You have no completed trades to review. Close a trade using `/close <id>`.", parse_mode='Markdown')
        return

    wins = 0
    losses = 0
    total_profit_percent = 0.0

    for t in closed_trades:
        profit_percent = ((t['sell_price'] - t['buy_price']) / t['buy_price']) * 100
        if profit_percent >= 0:
            wins += 1
        else:
            losses += 1
        total_profit_percent += profit_percent

    total_trades = len(closed_trades)
    win_rate = (wins / total_trades) * 100 if total_trades > 0 else 0
    avg_pnl_percent = total_profit_percent / total_trades if total_trades > 0 else 0

    message = (
        f"🌟 **Lunura’s Performance Review** 🌟\n\n"
        f"**Completed Quests:** {total_trades}\n"
        f"**Victories (Wins):** {wins}\n"
        f"**Setbacks (Losses):** {losses}\n"
        f"**Win Rate:** {win_rate:.2f}%\n\n"
        f"**Average P/L:** `{avg_pnl_percent:,.2f}%`\n\n"
        f"Keep honing your skills, seeker. The market's rhythm is complex."
    )
    await update.message.reply_text(message, parse_mode='Markdown')

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Displays a help message with all available commands."""
    help_text = (
        "🌟 **Lunura's Guide** 🌟\n\n"
        "Here are the commands you can use on your quest:\n\n"
        "**/start** - Begin your journey with me.\n"
        "**/quest** - Get a thematic introduction to trading.\n"
        "**/crypto `<SYMBOL>`** - Scan a crypto pair (e.g., `/crypto BTCUSDT`). If RSI is low, a trade is automatically opened for you.\n"
        "**/import `<SYMBOL> [PRICE]`** - Import a trade. Fetches from Binance or uses the price you provide (e.g., `/import CTKUSDT 0.75`).\n"
        "**/status** - View all your currently open trades (quests).\n"
        "**/close `<ID>`** - Manually close an open trade using its ID from `/status`.\n"
        "**/review** - See your performance statistics for all completed trades.\n"
        "**/balance** - Check your USDT balance on Binance.\n"
        "**/safety** - A reminder on safe trading practices.\n"
        "**/resonate** - A word of wisdom from Lunura.\n"
        "**/pay** - Information on how to support Lunura's development.\n"
        "**/help** - Show this help message."
    )
    await update.message.reply_text(help_text, parse_mode='Markdown')

async def pay_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Shows donation and premium access information."""
    message = (
        f"🌟 **Support Lunura's Journey** 🌟\n\n"
        f"Your support helps keep the signals sharp and the quests engaging. Thank you for considering a donation!\n\n"
        f"**Local Donations (Bangladesh):**\n"
        f"- **bKash:** `01717948095`\n"
        f"- **Rocket:** `01717948095`\n\n"
        f"For premium features and quests, stay tuned!"
    )
    await update.message.reply_text(message, parse_mode='Markdown')

def main() -> None:
    """Start the bot."""
    db.initialize_database()

    application = Application.builder().token(config.TELEGRAM_BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("quest", quest_command))
    application.add_handler(CommandHandler("crypto", crypto_command))
    application.add_handler(CommandHandler("import", import_command))
    application.add_handler(CommandHandler("status", status_command))
    application.add_handler(CommandHandler("balance", balance_command))
    application.add_handler(CommandHandler("close", close_command))
    application.add_handler(CommandHandler("review", review_command))
    application.add_handler(CommandHandler("resonate", resonate_command))
    application.add_handler(CommandHandler("pay", pay_command))
    application.add_handler(CommandHandler("safety", safety_command))
    application.add_handler(CommandHandler("hubspeedy", hubspeedy_command))

    # --- Set up background jobs ---
    job_queue = application.job_queue
    # Schedule the auto-scan job to run every 10 minutes (600 seconds).
    # The 'first=10' parameter makes it run for the first time 10 seconds after startup.
    job_queue.run_repeating(trade.monitor_market_and_trades, interval=60, first=10) # Check every minute for responsiveness

    logger.info("Starting bot with auto-scan enabled...")
    application.run_polling()

if __name__ == "__main__":
    main()