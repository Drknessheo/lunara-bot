import logging
from datetime import datetime, timezone
import asyncio
import os
from telegram import Update, Chat, InputFile
from telegram.constants import ParseMode
from telegram.ext import Application, CommandHandler, ContextTypes
import google.generativeai as genai

import config
import db
import trade
from Simulation import resonance_engine

# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- AI Configuration ---
if config.GEMINI_API_KEY:
    genai.configure(api_key=config.GEMINI_API_KEY)
    model = genai.GenerativeModel('gemini-1.5-flash-latest')
else:
    model = None
    logger.warning("GEMINI_API_KEY not found. The /ask command will be disabled.")

# --- Command Handlers ---
async def linkbinance_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Provides instructions for linking Binance API keys."""
    await update.message.reply_html(
        "<b>How to Link Your Binance API Keys</b>\n\n"
        "1. Go to your Binance account and create an API key.\n"
        "2. Copy your API Key and Secret Key.\n"
        "3. Send them to me in a private chat using:\n"
        "<code>/setapi YOUR_API_KEY YOUR_SECRET_KEY</code>\n\n"
        "Your keys are encrypted and stored securely."
    )

async def learn_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Provides educational resources and tips for new traders."""
    await update.message.reply_html(
        "<b>Welcome to the Crypto Academy!</b>\n\n"
        "- <b>RSI:</b> The Relative Strength Index helps you spot overbought and oversold conditions.\n"
        "- <b>Bollinger Bands:</b> These show price volatility and potential buy/sell zones.\n"
        "- <b>Paper Trading:</b> Practice trading with virtual funds using /papertrade.\n\n"
        "For more tips, ask me anything or use /help."
    )

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Sends a welcome message when the /start command is issued."""
    user_id = update.effective_user.id
    db.get_or_create_user(user_id) # Ensure user is in the DB

    user = update.effective_user
    await update.message.reply_html(
        rf"🌑 <b>A new trader emerges from the shadows.</b> {user.mention_html()}, you have been summoned by <b>Lunessa Shai'ra Gork</b>, Sorceress of DeFi and guardian of RSI gates.\n\n"
        "🧭 <i>Your journey begins now.</i>\n"
        "- Quest 1: Link your API Key (Binance/OKX)\n"
        "- Quest 2: Choose your weapon: RSI or Bollinger\n"
        "- Quest 3: Survive 3 trades\n\n"
        "Reply with: /linkbinance or /learn\n\n"
        "To unlock the arcane powers, send your Binance API keys in a private message with: <code>/setapi YOUR_API_KEY YOUR_SECRET_KEY</code>\n\n"
        "Use /help to see all available commands."
    )

async def quest_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handler for the /crypto command. Calls the trade module."""
    await trade.quest_command(update, context)

async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handler for the /status command. Shows open quests and watched symbols."""
    user_id = update.effective_user.id
    open_trades = db.get_open_trades(user_id)
    watched_items = db.get_watched_items_by_user(user_id)

    if not open_trades and not watched_items:
        await update.message.reply_text("You have no open quests or watched symbols. Use /quest to find an opportunity.")
        return

    message = ""
    if open_trades:
        message += "📜 **Your Open Quests:**\n"

        # --- Refactored Price Fetching Logic ---
        prices = {}
        symbols_to_fetch = {t['coin_symbol'] for t in open_trades}

        # Check for cached prices from the monitor job
        cached_prices_data = context.bot_data.get('all_prices', {})
        if cached_prices_data:
            cached_prices = cached_prices_data.get('prices', {})
            cache_timestamp = cached_prices_data.get('timestamp')

            # Cache is valid if it's less than 65 seconds old (job runs every 60s)
            if cache_timestamp and (datetime.now(timezone.utc) - cache_timestamp).total_seconds() < 65:
                logger.info(f"Using cached prices for /status for user {user_id}.")
                for symbol in symbols_to_fetch:
                    if symbol in cached_prices:
                        prices[symbol] = cached_prices[symbol]

        # Identify and fetch any prices that were not in the valid cache
        symbols_to_fetch_now = {s for s in symbols_to_fetch if s not in prices}
        if symbols_to_fetch_now:
            logger.info(f"Cache miss for {len(symbols_to_fetch_now)} symbol(s). Fetching individually for /status for user {user_id}.")
            for symbol in symbols_to_fetch_now:
                prices[symbol] = trade.get_current_price(symbol) # Fallback to individual API call

        for trade_item in open_trades:
            symbol = trade_item['coin_symbol']
            buy_price = trade_item['buy_price']
            current_price = prices.get(symbol)

            message += f"\n🔹 **{symbol}** (ID: {trade_item['id']})"

            if current_price:
                pnl_percent = ((current_price - buy_price) / buy_price) * 100
                pnl_emoji = "📈" if pnl_percent >= 0 else "📉"
                
                # --- Indicator Calculations ---
                rsi = trade.get_rsi(symbol)
                upper_band, middle_band, lower_band, _ = trade.get_bollinger_bands(symbol)

                # --- Progress Bar Logic ---
                tp_price = trade_item['take_profit_price']
                total_gain_needed = tp_price - buy_price
                current_gain = current_price - buy_price
                progress_str = ""
                if total_gain_needed > 0 and current_gain > 0:
                    progress_percent = (current_gain / total_gain_needed) * 100
                    progress_str = f" ({min(progress_percent, 100):.0f}% there)"

                message += (
                    f"\n   {pnl_emoji} P/L: `{pnl_percent:+.2f}%`"
                    f"\n   Bought: `${buy_price:,.8f}`"
                    f"\n   Current: `${current_price:,.8f}`"
                    f"\n   ✅ Target: `${tp_price:,.8f}`{progress_str}"
                    f"\n   🛡️ Stop: `${trade_item['stop_loss_price']:,.8f}`"
                )

                if rsi is not None:
                    message += f"\n   ⚖️ RSI: `{rsi:.2f}`"
                if upper_band is not None:
                    message += f"\n   📊 BBands: `${lower_band:,.8f}` - `${upper_band:,.8f}`"

            else:
                message += "\n   _(Could not fetch current price)_"

        message += "\n" # Add a newline for spacing before the watchlist

    if watched_items:
        message += "\n🔭 **Your Watched Symbols:**\n"
        for item in watched_items:
            # Calculate time since added
            add_time = datetime.strptime(item['add_timestamp'], '%Y-%m-%d %H:%M:%S').replace(tzinfo=timezone.utc)
            time_watching = datetime.now(timezone.utc) - add_time
            hours, remainder = divmod(time_watching.total_seconds(), 3600)
            minutes, _ = divmod(remainder, 60)
            message += (
                f"\n🔸 **{item['coin_symbol']}**"
                f"\n   *Watching for {int(hours)}h {int(minutes)}m*"
            )

    await update.message.reply_text(message, parse_mode='Markdown')

async def resonate_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Runs Lunessa's quantum resonance simulation and sends the results."""
    user_id = update.effective_user.id
    symbol = None
    if context.args:
        symbol = context.args[0].upper()
        await update.message.reply_text(f"Attuning my quantum senses to the vibrations of **{symbol}**... Please wait. 🔮", parse_mode=ParseMode.MARKDOWN)
    else:
        await update.message.reply_text("Attuning my quantum senses to the general market vibration... Please wait. 🔮")

    metric_plot_path = None
    clock_plot_path = None
    try:
        # Run the potentially long-running simulation in a separate thread
        # to avoid blocking the bot's event loop.
        # Pass the symbol to the simulation engine.
        loop = asyncio.get_running_loop()
        results = await loop.run_in_executor(
            None, resonance_engine.run_resonance_simulation, user_id, symbol
        )

        narrative = results['narrative']
        metric_plot_path = results['metric_plot']
        clock_plot_path = results['clock_plot']

        # Send the narrative text
        await update.message.reply_text(narrative, parse_mode=ParseMode.MARKDOWN)

        # Send the plots
        await update.message.reply_photo(photo=open(metric_plot_path, 'rb'), caption="Soul Waveform Analysis")
        await update.message.reply_photo(photo=open(clock_plot_path, 'rb'), caption="Clock Phase Distortions")

    except Exception as e:
        logger.error(f"Error running resonance simulation for user {user_id}: {e}", exc_info=True)
        await update.message.reply_text("The cosmic energies are scrambled. I could not generate a resonance report at this time.")
    finally:
        # Clean up the generated plot files
        if metric_plot_path and os.path.exists(metric_plot_path):
            os.remove(metric_plot_path)
        if clock_plot_path and os.path.exists(clock_plot_path):
            os.remove(clock_plot_path)

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

async def import_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handler for the /import command. Calls the trade module."""
    await trade.import_last_trade_command(update, context)

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
    best_trade = None
    worst_trade = None
    # Use -inf and inf to correctly handle all possible P/L values
    best_pnl = -float('inf')
    worst_pnl = float('inf')

    for t in closed_trades:
        profit_percent = ((t['sell_price'] - t['buy_price']) / t['buy_price']) * 100

        # Track best and worst trades
        if profit_percent > best_pnl:
            best_pnl = profit_percent
            best_trade = t
        if profit_percent < worst_pnl:
            worst_pnl = profit_percent
            worst_trade = t

        if profit_percent >= 0:
            wins += 1
        else:
            losses += 1
        total_profit_percent += profit_percent

    total_trades = len(closed_trades)
    win_rate = (wins / total_trades) * 100 if total_trades > 0 else 0
    avg_pnl_percent = total_profit_percent / total_trades if total_trades > 0 else 0

    message = (
        f"🌟 **Lunessa's Performance Review** 🌟\n\n"
        f"**Completed Quests:** {total_trades}\n"
        f"**Victories (Wins):** {wins}\n"
        f"**Setbacks (Losses):** {losses}\n"
        f"**Win Rate:** {win_rate:.2f}%\n\n"
        f"**Average P/L:** `{avg_pnl_percent:,.2f}%`\n"
    )

    if best_trade and worst_trade:
        message += (
            f"\n**Top Performers:**\n"
            f"🚀 **Best Quest:** {best_trade['coin_symbol']} (`{best_pnl:+.2f}%`)\n"
            f"💔 **Worst Quest:** {worst_trade['coin_symbol']} (`{worst_pnl:+.2f}%`)\n"
        )

    message += "\nKeep honing your skills, seeker. The market's rhythm is complex."
    await update.message.reply_text(message, parse_mode='Markdown')

async def top_trades_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Displays the user's top 3 most profitable closed trades."""
    user_id = update.effective_user.id
    top_trades = db.get_top_closed_trades(user_id, limit=3)

    if not top_trades:
        await update.message.reply_text("You have no completed profitable quests to rank. Close a winning trade to enter the Hall of Fame!", parse_mode='Markdown')
        return

    message = "🏆 **Your Hall of Fame** 🏆\n\n_Here are your most legendary victories:_\n\n"
    rank_emojis = ["🥇", "🥈", "🥉"]

    for i, trade in enumerate(top_trades):
        emoji = rank_emojis[i] if i < len(rank_emojis) else "🔹"
        message += f"{emoji} **{trade['coin_symbol']}**: `{trade['pnl_percent']:+.2f}%`\n"

    message += "\nMay your future quests be even more glorious!"
    await update.message.reply_text(message, parse_mode='Markdown')

async def leaderboard_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Displays the global leaderboard of top trades."""
    top_trades = db.get_global_top_trades(limit=3)

    if not top_trades:
        await update.message.reply_text("The Hall of Legends is still empty. No legendary quests have been completed yet!", parse_mode='Markdown')
        return

    message = "🏆 **Hall of Legends: Global Top Quests** 🏆\n\n_These are the most glorious victories across the realm:_\n\n"
    rank_emojis = ["🥇", "🥈", "🥉"]

    for i, trade in enumerate(top_trades):
        emoji = rank_emojis[i] if i < len(rank_emojis) else "🔹"
        user_id = trade['user_id']
        user_name = "A mysterious adventurer" # Default name
        try:
            chat = await context.bot.get_chat(user_id)
            user_name = chat.first_name
        except Exception as e:
            logger.warning(f"Could not fetch user name for {user_id} for leaderboard: {e}")

        message += f"{emoji} **{trade['coin_symbol']}**: `{trade['pnl_percent']:+.2f}%` (by {user_name})\n"

    message += "\nWill your name be etched into legend?"
    await update.message.reply_text(message, parse_mode='Markdown')

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Displays a help message with all available commands."""
    help_text = """<b>Lunessa's Guide 🔮</b>

Here are the commands to guide your journey:

<b>--- Account & Setup ---</b>
<b>/start</b> - Begin your journey
<b>/setapi</b> <code>KEY SECRET</code> - Link your Binance keys (in private chat)
<b>/linkbinance</b> - Instructions for creating API keys
<b>/myprofile</b> - View your profile and settings
<b>/settings</b> - [Premium] Customize your trading parameters
<b>/subscribe</b> - See premium benefits and how to upgrade

<b>--- Trading & Analysis ---</b>
<b>/quest</b> <code>SYMBOL</code> - Scan a crypto pair for opportunities
<b>/status</b> - View your open trades and watchlist
<b>/balance</b> - Check your LIVE or PAPER balance
<b>/close</b> <code>ID</code> - Manually complete a quest (trade)
<b>/import</b> <code>SYMBOL [PRICE]</code> - Log an existing trade
<b>/papertrade</b> - Toggle practice mode

<b>--- Performance & Community ---</b>
<b>/review</b> - See your personal performance stats
<b>/top_trades</b> - View your 3 best trades
<b>/leaderboard</b> - See the global top 3 trades

<b>--- General ---</b>
<b>/ask</b> <code>QUESTION</code> - Ask the AI Oracle about trading
<b>/learn</b> - Get quick educational tips
<b>/pay</b> - See how to support Lunessa's development
<b>/safety</b> - Read important trading advice
<b>/resonate</b> - A word of wisdom from Lunessa
<b>/help</b> - Show this help message"""
    await update.message.reply_text(help_text, parse_mode=ParseMode.HTML)

async def myprofile_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Displays the user's profile information, including tier and settings."""
    user_id = update.effective_user.id
    user_tier = db.get_user_tier(user_id)
    settings = db.get_user_effective_settings(user_id)
    trading_mode, paper_balance = db.get_user_trading_mode_and_balance(user_id)

    message = (
        f"👤 **Your Profile** 👤\n\n"
        f"**User ID:** `{user_id}`\n"
        f"**Trading Mode:** {trading_mode}\n"
        f"**Subscription Tier:** {user_tier}\n\n"
    )

    if user_tier == 'PREMIUM':
        message += (
            "**Your Effective Trading Parameters:**\n"
            f"- `rsi_buy`: {settings['RSI_BUY_THRESHOLD']}\n"
            f"- `rsi_sell`: {settings['RSI_SELL_THRESHOLD']}\n"
            f"- `stop_loss`: {settings['STOP_LOSS_PERCENTAGE']}%\n"
            f"- `trailing_activation`: {settings['TRAILING_PROFIT_ACTIVATION_PERCENT']}%\n"
            f"- `trailing_drop`: {settings['TRAILING_STOP_DROP_PERCENT']}%\n\n"
            "You can change these with the `/settings` command."
        )
        message += (
            f"**Paper Balance:** `${paper_balance:,.2f}`\n"
        )
    else:
        message += "Upgrade to Premium with `/subscribe` to unlock custom settings and advanced features!"

    await update.message.reply_text(message, parse_mode='Markdown')

async def settings_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Allows Premium users to view and customize their trading settings."""
    user_id = update.effective_user.id
    user_tier = db.get_user_tier(user_id)

    if user_tier != 'PREMIUM':
        await update.message.reply_text("Custom settings are a Premium feature. Use /subscribe to upgrade.")
        return

    # If no args, show current settings and usage
    if not context.args:
        settings = db.get_user_effective_settings(user_id)
        message = (
            "⚙️ **Your Custom Settings** ⚙️\n\n"
            "Here are your current effective trading parameters. You can override the defaults.\n\n"
            f"- `rsi_buy`: {settings['RSI_BUY_THRESHOLD']}\n"
            f"- `rsi_sell`: {settings['RSI_SELL_THRESHOLD']}\n"
            f"- `stop_loss`: {settings['STOP_LOSS_PERCENTAGE']}%\n"
            f"- `trailing_activation`: {settings['TRAILING_PROFIT_ACTIVATION_PERCENT']}%\n"
            f"- `trailing_drop`: {settings['TRAILING_STOP_DROP_PERCENT']}%\n\n"
            "**To change a setting:**\n`/settings <name> <value>`\n*Example: `/settings stop_loss 8.5`*\n\n"
            "**To reset a setting to default:**\n`/settings <name> reset`"
        )
        await update.message.reply_text(message, parse_mode='Markdown')
        return

    # Logic to set a value
    try:
        setting_name = context.args[0].lower()
        value_str = context.args[1].lower()
    except IndexError:
        await update.message.reply_text("Invalid format. Usage: `/settings <name> <value>`", parse_mode='Markdown')
        return

    try:
        if setting_name not in db.SETTING_TO_COLUMN_MAP:
            await update.message.reply_text(f"Unknown setting '{setting_name}'. Valid settings are: {', '.join(db.SETTING_TO_COLUMN_MAP.keys())}")
            return

        new_value = None if value_str == 'reset' else float(value_str)
        if new_value is not None and new_value <= 0:
            await update.message.reply_text("Value must be a positive number.")
            return
        
        db.update_user_setting(user_id, setting_name, new_value)
        await update.message.reply_text(f"✅ Successfully updated **{setting_name}** to **{value_str}**.")
    except ValueError:
        await update.message.reply_text(f"Invalid value '{value_str}'. Please provide a number (e.g., 8.5) or 'reset'.")

async def pay_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Shows donation and premium access information."""
    message = (
        f"🌟 **Support Lunessa's Journey** 🌟\n\n"
        f"Your support helps keep the signals sharp and the quests engaging. Thank you for considering a donation!\n\n"
        f"**Local Donations (Bangladesh):**\n"
        f"- **bKash:** `01717948095`\n"
        f"- **Rocket:** `01717948095`\n\n"
        f"For premium features and quests, stay tuned!"
    )
    await update.message.reply_text(message, parse_mode='Markdown')

async def set_api_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Securely sets the user's Binance API keys."""
    user_id = update.effective_user.id

    if update.message.chat.type != Chat.PRIVATE:
        await update.message.reply_text("For your security, please send this command in a private chat with me.")
        return

    try:
        api_key = context.args[0]
        secret_key = context.args[1]
    except (IndexError, ValueError):
        await update.message.reply_text(
            "Please provide both API Key and Secret Key.\n"
            "Usage (in a private chat):\n`/setapi <your_api_key> <your_secret_key>`",
            parse_mode='Markdown'
        )
        return

    db.store_user_api_keys(user_id, api_key, secret_key)

    # For security, delete the message containing the keys
    try:
        await context.bot.delete_message(chat_id=update.message.chat_id, message_id=update.message.message_id)
        await update.message.reply_text("✅ Your API keys have been securely stored and your message has been deleted. You can now use commands like /balance and /import.")
    except Exception as e:
        logger.error(f"Could not delete API key message for user {user_id}: {e}")
        await update.message.reply_text("✅ Your API keys have been securely stored. Please delete your message containing the keys manually.")

async def subscribe_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Displays subscription information."""
    user_id = update.effective_user.id
    user_tier = db.get_user_tier(user_id)

    message = (
        f"🌟 **Subscription Status** 🌟\n\n"
        f"You are currently on the **{user_tier}** tier.\n\n"
        f"To upgrade to **Premium** and unlock advanced features like Bollinger Band intelligence and dynamic take-profit, please make a payment to the address below.\n\n"
        f"**Payment Method:**\n"
        f"- **Network:** Solana (SOL)\n"
        f"- **Address:** `0xD96E942fDb4A0e7059Ae4548b5f410aA6E4F2dBe`\n\n"
        f"**After Payment:**\n"
        f"Once you have sent the payment, copy the **Transaction ID** and use the following command to request activation:\n"
        f"`/verifypayment <your_transaction_id>`"
    )
    await update.message.reply_text(message, parse_mode='Markdown')

async def activate_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Admin command to activate a user's premium subscription."""
    admin_id = update.effective_user.id

    if admin_id != config.ADMIN_USER_ID:
        await update.message.reply_text("You are not authorized to use this command.")
        return

    try:
        target_user_id = int(context.args[0])
        tier = context.args[1].upper()
        if tier not in config.SUBSCRIPTION_TIERS:
            await update.message.reply_text(f"Invalid tier '{tier}'. Valid tiers are: {list(config.SUBSCRIPTION_TIERS.keys())}")
            return
    except (IndexError, ValueError):
        await update.message.reply_text(
            "Usage: `/activate <user_id> <TIER>`\n"
            "Example: `/activate 123456789 PREMIUM`",
            parse_mode='Markdown'
        )
        return

    db.update_user_tier(target_user_id, tier)
    await update.message.reply_text(f"Successfully updated user {target_user_id} to the {tier} tier.")

    # Notify the user
    try:
        await context.bot.send_message(chat_id=target_user_id, text=f"🎉 Congratulations! Your account has been upgraded to the **{tier}** tier. Enjoy your new features!", parse_mode='Markdown')
    except Exception as e:
        logger.error(f"Failed to send activation notification to user {target_user_id}: {e}")
        await update.message.reply_text(f"Could not notify user {target_user_id} of the upgrade.")

async def verifypayment_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Allows a user to submit a transaction ID for verification."""
    user = update.effective_user
    user_id = user.id

    try:
        tx_id = context.args[0]
    except IndexError:
        await update.message.reply_text("Please provide your transaction ID.\nUsage: `/verifypayment <transaction_id>`", parse_mode='Markdown')
        return

    if len(tx_id) < 60: # Basic validation for a Solana TX ID
        await update.message.reply_text("That does not look like a valid transaction ID. Please double-check and try again.")
        return

    # Send a confirmation to the user
    await update.message.reply_text("✅ Thank you! Your payment verification request has been sent to the admin. Please allow some time for activation.")

    # Prepare the verification message for the admin
    verification_message = (
        f"🔔 **New Premium Activation Request** 🔔\n\n"
        f"**User:** {user.mention_html()} (ID: `{user_id}`)\n"
        f"**Transaction ID:** `{tx_id}`\n\n"
        f"**Actions:**\n"
        f"1. **Verify on Solscan:** Click here to view transaction\n"
        f"2. **Activate Premium:** `/activate {user_id} PREMIUM`"
    )
    await context.bot.send_message(chat_id=config.ADMIN_USER_ID, text=verification_message, parse_mode='HTML')

async def broadcast_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Admin command to send a message to all users."""
    admin_id = update.effective_user.id

    if admin_id != config.ADMIN_USER_ID:
        await update.message.reply_text("You are not authorized to use this command.")
        return

    if not context.args:
        await update.message.reply_text("Please provide a message to broadcast.\nUsage: `/broadcast <your message>`", parse_mode='Markdown')
        return

    message_to_send = " ".join(context.args)
    all_user_ids = db.get_all_user_ids()

    if not all_user_ids:
        await update.message.reply_text("No users found in the database to broadcast to.")
        return

    await update.message.reply_text(f"Starting broadcast to {len(all_user_ids)} users... This may take a moment.")

    success_count = 0
    fail_count = 0
    broadcast_header = "📢 **A Message from Lunessa** 📢\n\n"
    full_message = broadcast_header + message_to_send

    for user_id in all_user_ids:
        try:
            # Use Markdown for better formatting in the broadcast message
            await context.bot.send_message(chat_id=user_id, text=full_message, parse_mode='Markdown')
            success_count += 1
        except Exception as e:
            logger.warning(f"Failed to send broadcast to user {user_id}: {e}")
            fail_count += 1

    await update.message.reply_text(f"✅ Broadcast complete!\n\nSuccessfully sent to: {success_count} users\nFailed to send to: {fail_count} users")

async def papertrade_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles paper trading mode and balance."""
    user_id = update.effective_user.id
    args = context.args

    if not args:
        mode, balance = db.get_user_trading_mode_and_balance(user_id)
        message = (
            f"**Paper Trading Mode**\n\n"
            f"You are currently in **{mode}** mode.\n"
            f"Your paper balance is: **${balance:,.2f} USDT**\n\n"
            "**Commands:**\n"
            "- `/papertrade on` - Enable paper trading.\n"
            "- `/papertrade off` - Switch to live trading (requires API keys).\n"
            "- `/papertrade reset` - Reset your paper balance and close all paper trades."
        )
        await update.message.reply_text(message, parse_mode='Markdown')
        return

    sub_command = args[0].lower()

    if sub_command == 'on':
        db.set_user_trading_mode(user_id, 'PAPER')
        await update.message.reply_text("✅ Paper trading mode **enabled**. All new quests will be simulated.")
    elif sub_command == 'off':
        # Admin doesn't need keys, others do.
        if user_id != config.ADMIN_USER_ID:
            api_key, _ = db.get_user_api_keys(user_id)
            if not api_key:
                await update.message.reply_text("You must set your API keys with `/setapi` before switching to live mode.")
                return
        db.set_user_trading_mode(user_id, 'LIVE')
        await update.message.reply_text("✅ Live trading mode **enabled**. Use with caution.")
    elif sub_command == 'reset':
        db.reset_paper_account(user_id)
        await update.message.reply_text(
            f"✅ Your paper trading account has been reset.\n"
            f"Your new balance is **${config.PAPER_STARTING_BALANCE:,.2f} USDT**."
        )
    else:
        await update.message.reply_text(
            f"Unknown command. Use `/papertrade` to see available options."
        )

async def ask_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Answers user questions using the Gemini AI model."""
    if not model:
        await update.message.reply_text("The AI Oracle is currently unavailable. Please check the bot's configuration.")
        return

    question = " ".join(context.args)
    if not question:
        await update.message.reply_text("What knowledge do you seek? Usage: `/ask <your question about trading>`", parse_mode='Markdown')
        return

    await update.message.reply_text("Lunessa is consulting the cosmic AI oracle... 🧠✨")

    try:
        user_name = update.effective_user.first_name
        # Add some context to the prompt to guide the AI
        prompt = (
            "You are a helpful crypto trading assistant named Lunessa. "
            f"A user named {user_name} has asked the following question. Greet them by name. Provide a clear, concise, and helpful answer. "
            "Do not give financial advice. Frame your answer from the perspective of a wise trading sorceress.\n\n"
            f"Question: {question}"
        )
        # The google-generativeai library's generate_content_async is awaitable
        response = await model.generate_content_async(prompt)
        await update.message.reply_text(response.text, parse_mode='Markdown')
    except Exception as e:
        logger.error(f"Error calling Gemini API: {e}")
        await update.message.reply_text("The cosmic energies are scrambled. I could not get an answer at this time.")


def main() -> None:
    """Start the bot."""
    db.initialize_database()
    # Run schema migrations to ensure DB is up to date
    db.migrate_schema()

    application = Application.builder().token(config.TELEGRAM_BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("quest", quest_command)) # This now handles the main trading logic
    application.add_handler(CommandHandler("import", import_command))
    application.add_handler(CommandHandler("status", status_command))
    application.add_handler(CommandHandler("balance", balance_command))
    application.add_handler(CommandHandler("close", close_command))
    application.add_handler(CommandHandler("review", review_command))
    application.add_handler(CommandHandler("resonate", resonate_command)) # This now calls the simulation
    application.add_handler(CommandHandler("top_trades", top_trades_command))
    application.add_handler(CommandHandler("leaderboard", leaderboard_command))
    application.add_handler(CommandHandler("myprofile", myprofile_command))
    application.add_handler(CommandHandler("settings", settings_command))
    application.add_handler(CommandHandler("subscribe", subscribe_command))
    application.add_handler(CommandHandler("setapi", set_api_command))
    application.add_handler(CommandHandler("activate", activate_command))
    application.add_handler(CommandHandler("broadcast", broadcast_command))
    application.add_handler(CommandHandler("papertrade", papertrade_command))
    application.add_handler(CommandHandler("verifypayment", verifypayment_command))
    application.add_handler(CommandHandler("pay", pay_command))
    application.add_handler(CommandHandler("safety", safety_command))
    application.add_handler(CommandHandler("hubspeedy", hubspeedy_command))
    application.add_handler(CommandHandler("linkbinance", linkbinance_command))
    application.add_handler(CommandHandler("learn", learn_command))
    application.add_handler(CommandHandler("ask", ask_command))

    # --- Set up background jobs ---
    job_queue = application.job_queue
    # Schedule the auto-scan job to run every 10 minutes (600 seconds).
    # The 'first=10' parameter makes it run for the first time 10 seconds after startup.
    job_queue.run_repeating(trade.monitor_market_and_trades, interval=60, first=10) # Check every minute for responsiveness

    logger.info("Starting bot with auto-scan enabled...")
    application.run_polling()

if __name__ == "__main__":
    main()