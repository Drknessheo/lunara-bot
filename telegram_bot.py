import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
import config
import trade
import db

# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Sends a welcome message when the /start command is issued."""
    await update.message.reply_text(
        "Welcome to Lunara Bot! I can help you with your crypto trading. "
        "Use /help to see a list of available commands."
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Sends a help message when the /help command is issued."""
    help_text = """
    Here are the available commands:
    `/start` - Welcome message
    `/help` - Shows this help message
    `/quest <SYMBOL>` - Get price/RSI and watch a symbol for a buy signal.
    `/import <SYMBOL> [PRICE]` - Import a trade from Binance or manually.
    `/status` - View your open trades and watchlist.
    `/performance` - View win/loss and PnL performance per coin.
    `/balance` - Check your USDT balance (live or paper).
    `/wallet` - View all your spot wallet balances (live only).
    `/close <TRADE_ID>` - Manually close an open trade.
    `/setapi <KEY> <SECRET>` - Set your Binance API keys (in private chat).
    `/mode <LIVE|PAPER>` - Switch between live and paper trading.
    """
    await update.message.reply_text(help_text, parse_mode='Markdown')

async def wallet_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles the /wallet command."""
    user_id = update.effective_user.id
    mode, _ = db.get_user_trading_mode_and_balance(user_id)

    if mode == 'PAPER':
        await update.message.reply_text("You are in Paper Trading mode. The /wallet command is for live trading only.")
        return

    api_key, _ = db.get_user_api_keys(user_id)
    if not api_key:
        await update.message.reply_text("Your Binance API keys are not set. Please use `/setapi <key> <secret>` in a private chat with me.")
        return

    await update.message.reply_text("Fetching your spot wallet balances from Binance...")
    try:
        balances = trade.get_all_spot_balances(user_id)
        if not balances:
            await update.message.reply_text("You do not seem to have any assets in your spot wallet.")
            return

        # Sort balances by asset name
        balances.sort(key=lambda x: x['asset'])

        message = "💎 **Your Spot Wallet** 💎\n\n"
        for bal in balances:
            # Only show assets with a free balance greater than a small threshold
            if float(bal['free']) > 0.00000001:
                 message += f"**{bal['asset']}:** `{bal['free']}`\n"

        await update.message.reply_text(message, parse_mode='Markdown')

    except trade.TradeError as e:
        await update.message.reply_text(f"Could not retrieve your wallet balance.\n\n*Reason:* `{e}`\n\nPlease check your API key permissions and IP restrictions on Binance.", parse_mode='Markdown')
    except Exception as e:
        logger.error(f"An unexpected error occurred in wallet_command: {e}")
        await update.message.reply_text("An unexpected error occurred while fetching your wallet.")

async def set_api_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Sets the user's Binance API key and secret."""
    user_id = update.effective_user.id

    if update.effective_chat.type != 'private':
        await update.message.reply_text("For security reasons, please set your API keys in a private chat with me.")
        return

    try:
        api_key = context.args[0]
        secret_key = context.args[1]
    except IndexError:
        await update.message.reply_text("Please provide both API key and secret. Usage: `/setapi <KEY> <SECRET>`")
        return

    db.set_user_api_keys(user_id, api_key, secret_key)
    await update.message.reply_text("Your Binance API keys have been securely saved.")

async def set_mode_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Sets the user's trading mode (LIVE or PAPER)."""
    user_id = update.effective_user.id

    try:
        mode = context.args[0].upper()
        if mode not in ['LIVE', 'PAPER']:
            raise ValueError("Invalid mode.")
    except (IndexError, ValueError):
        await update.message.reply_text("Please specify a valid mode: `/mode LIVE` or `/mode PAPER`.")
        return

    db.set_user_trading_mode(user_id, mode)
    await update.message.reply_text(f"Your trading mode has been set to **{mode}**.", parse_mode='Markdown')

def main() -> None:
    """Start the bot."""
    if not config.TELEGRAM_BOT_TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN not found in config. Please set it.")
        return

    application = Application.builder().token(config.TELEGRAM_BOT_TOKEN).build()

    # Add command handlers
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("quest", trade.quest_command))
    application.add_handler(CommandHandler("balance", trade.balance_command))
    application.add_handler(CommandHandler("wallet", wallet_command))
    application.add_handler(CommandHandler("import", trade.import_last_trade_command))
    application.add_handler(CommandHandler("status", trade.status_command))
    application.add_handler(CommandHandler("performance", trade.performance_command))
    application.add_handler(CommandHandler("close", trade.close_trade_command))
    application.add_handler(CommandHandler("setapi", set_api_command))
    application.add_handler(CommandHandler("mode", set_mode_command))

    logger.info("Starting bot...")
    application.run_polling()

if __name__ == "__main__":
    main()
