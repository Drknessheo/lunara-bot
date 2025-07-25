import logging
import numpy as np
import datetime
from binance.client import Client
from binance.exceptions import BinanceAPIException
from telegram import Update
from telegram.ext import ContextTypes

import config
import db

logger = logging.getLogger(__name__)

# Initialize Binance client
if config.BINANCE_API_KEY and config.BINANCE_SECRET_KEY:
    client = Client(config.BINANCE_API_KEY, config.BINANCE_SECRET_KEY)
else:
    logger.warning("Binance API keys not found. Trading functions will be disabled.")
    client = None

def is_weekend():
    """Checks if the current day is Saturday or Sunday (UTC)."""
    # weekday() returns 5 for Saturday, 6 for Sunday
    return datetime.datetime.utcnow().weekday() >= 5

def get_current_price(symbol: str):
    """Fetches the current price of a given symbol from Binance."""
    try:
        ticker = client.get_symbol_ticker(symbol=symbol)
        return float(ticker['price'])
    except BinanceAPIException as e:
        logger.error(f"Binance API error getting price for {symbol}: {e}")
        return None
    except Exception as e:
        logger.error(f"An unexpected error occurred getting price for {symbol}: {e}")
        return None

def get_rsi(symbol="BTCUSDT", interval=Client.KLINE_INTERVAL_1HOUR, period=14):
    """Calculates the Relative Strength Index (RSI) for a given symbol."""
    try:
        # Fetch klines (candlestick data)
        klines = client.get_historical_klines(symbol, interval, f"{period + 10} hours ago UTC")
        if len(klines) < period:
            return None # Not enough data

        closes = np.array([float(k[4]) for k in klines])
        deltas = np.diff(closes)
        seed = deltas[:period+1]
        up = seed[seed >= 0].sum()/period
        down = -seed[seed < 0].sum()/period
        rs = up / down if down != 0 else 0
        rsi = 100 - (100 / (1 + rs))
        return rsi
    except BinanceAPIException as e:
        logger.error(f"Binance API error getting RSI for {symbol}: {e}")
        return None
    except Exception as e:
        logger.error(f"An unexpected error occurred getting RSI for {symbol}: {e}")
        return None

def get_account_balance(asset="USDT"):
    """Fetches the free balance for a specific asset from the Binance spot account."""
    try:
        balance = client.get_asset_balance(asset=asset)
        return float(balance['free']) if balance else 0.0
    except BinanceAPIException as e:
        logger.error(f"Binance API error getting account balance: {e}")
        return None
    except Exception as e:
        logger.error(f"An unexpected error occurred getting account balance: {e}")
        return None

def get_last_trade_from_binance(symbol: str):
    """Fetches the user's most recent trade for a given symbol from Binance."""
    try:
        # Fetch the last trade. The list is ordered from oldest to newest.
        trades = client.get_my_trades(symbol=symbol, limit=1)
        if not trades:
            return None
        return trades[0] # The most recent trade
    except BinanceAPIException as e:
        logger.error(f"Binance API error getting last trade for {symbol}: {e}")
        return None
    except Exception as e:
        logger.error(f"An unexpected error occurred getting last trade for {symbol}: {e}")
        return None

async def crypto_scan_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handles the /crypto command, providing price and RSI for a given symbol.
    Usage: /crypto <SYMBOL> (e.g., /crypto PEPEUSDT)
    """
    if not client:
        await update.message.reply_text("The connection to the crypto realm (Binance) is not configured. Please check API keys.")
        return

    try:
        symbol = context.args[0].upper()
    except IndexError:
        await update.message.reply_text("Please specify a trading pair. Usage: `/crypto BTCUSDT`", parse_mode='Markdown')
        return

    await update.message.reply_text(f"Lunura is gazing into the cosmic energies of {symbol}... 🔮")
    price = get_current_price(symbol)
    rsi = get_rsi(symbol)

    if price is not None and rsi is not None:
        message = (
            f"**Cosmic Insight: {symbol}**\n\n"
            f"✨ **Current Price:** `${price:,.8f}`\n"
            f"⚖️ **Hourly RSI({14}):** `{rsi:.2f}`\n\n"
        )
        if rsi < config.RSI_BUY_THRESHOLD:
            message += "The energies are low. A potential buying opportunity appears on the horizon."
            if is_weekend():
                message += "\n\n*Note: Weekend trading can have lower volume and higher risk. Please trade with caution.*"
        elif rsi > config.RSI_SELL_THRESHOLD:
            message += "The energies are high. It may be a time to consider taking profits."
        else:
            message += "The market is in balance. Patience is a virtue."

        # Log the trade signal as an open trade for the user
        if rsi < config.RSI_BUY_THRESHOLD:
            user_id = update.effective_user.id
            # Calculate Stop-Loss (-10%) and Take-Profit (+25%)
            stop_loss_price = price * (1 - config.STOP_LOSS_PERCENTAGE / 100)
            take_profit_price = price * (1 + config.PROFIT_TARGET_PERCENTAGE / 100)

            db.log_trade(user_id=user_id, coin_symbol=symbol, buy_price=price, stop_loss=stop_loss_price, take_profit=take_profit_price)
            message += "\n\n*A new quest has been recorded with automated risk management! Use /status to see your open trades.*\n"

        message += "\n*New to trading?* Join Binance with my link!"

        await update.message.reply_text(message, parse_mode='Markdown')
    else:
        await update.message.reply_text(f"Could not retrieve data for {symbol}. Please ensure it's a valid symbol on Binance (e.g., BTCUSDT).")

async def balance_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles the /balance command."""
    if not client:
        await update.message.reply_text("The connection to the crypto realm (Binance) is not configured.")
        return

    await update.message.reply_text("Checking your treasure chest (Binance)...")
    balance = get_account_balance(asset="USDT")
    if balance is not None:
        await update.message.reply_text(f"You hold **{balance:.2f} USDT**.", parse_mode='Markdown')
    else:
        await update.message.reply_text("Could not retrieve your balance. Check your API key permissions.")

async def check_btc_volatility_and_alert(context: ContextTypes.DEFAULT_TYPE):
    """
    Checks BTC's recent price movement and sends an alert if it's significant.
    This helps users understand the overall market pressure.
    """
    try:
        # Fetch the last 2 closed hourly candles for BTC
        klines = client.get_historical_klines("BTCUSDT", Client.KLINE_INTERVAL_1HOUR, "2 hours ago UTC")
        if len(klines) < 2:
            logger.warning("Not enough BTC kline data to check for volatility.")
            return

        # klines[0] is the older candle, klines[1] is the most recent closed candle
        old_price = float(klines[0][4])  # Close price of the n-2 candle
        new_price = float(klines[1][4])  # Close price of the n-1 candle

        percent_change = ((new_price - old_price) / old_price) * 100

        # Initialize bot_data for state management if it doesn't exist
        if 'market_state' not in context.bot_data:
            context.bot_data['market_state'] = 'CALM'

        last_state = context.bot_data.get('market_state', 'CALM')
        current_state = 'CALM'
        alert_message = None

        if percent_change > config.BTC_ALERT_THRESHOLD_PERCENT:
            current_state = 'BTC_PUMP'
            if last_state != 'BTC_PUMP':
                alert_message = (
                    f"🚨 **Market Alert: BTC Pumping** 🚨\n\n"
                    f"Bitcoin has increased by **{percent_change:.2f}%** in the last hour.\n\n"
                    f"This could lead to volatility in altcoins. Please review your open positions carefully."
                )
        elif percent_change < -config.BTC_ALERT_THRESHOLD_PERCENT:
            current_state = 'BTC_DUMP'
            if last_state != 'BTC_DUMP':
                alert_message = (
                    f"🚨 **Market Alert: BTC Dumping** 🚨\n\n"
                    f"Bitcoin has decreased by **{percent_change:.2f}%** in the last hour.\n\n"
                    f"This could lead to significant drops in altcoins. Please review your open positions carefully."
                )

        # If the market has calmed down after being volatile
        if current_state == 'CALM' and last_state != 'CALM':
            alert_message = (
                f"✅ **Market Update: BTC Stabilizing** ✅\n\n"
                f"Bitcoin's movement has stabilized. The previous period of high volatility appears to be over."
            )

        if alert_message and config.CHAT_ID:
            try:
                await context.bot.send_message(chat_id=config.CHAT_ID, text=alert_message, parse_mode='Markdown')
                logger.info(f"Sent market alert to CHAT_ID {config.CHAT_ID}. New state: {current_state}")
                context.bot_data['market_state'] = current_state
            except Exception as e:
                logger.error(f"Failed to send market alert to CHAT_ID {config.CHAT_ID}: {e}")
        elif current_state != last_state:
            context.bot_data['market_state'] = current_state

    except BinanceAPIException as e:
        logger.error(f"Binance API error during market volatility check: {e}")
    except Exception as e:
        logger.error(f"An unexpected error occurred during market volatility check: {e}")

async def monitor_market_and_trades(context: ContextTypes.DEFAULT_TYPE):
    """
    The intelligent core of the bot. Called by the JobQueue to:
    1. Monitor overall market conditions based on BTC movement.
    2. Check all open trades against their Stop-Loss and Take-Profit levels.
    """
    if not client:
        logger.warning("Market monitor skipped: Binance client not configured.")
        return

    logger.info("Running market monitor...")
    
    # Part 1: Strategic Market Condition Alert
    await check_btc_volatility_and_alert(context)

    # Part 2: Check individual open trades
    # 1. Get all unique symbols from open trades to check
    unique_symbols = db.get_unique_open_trade_symbols()
    if not unique_symbols:
        # logger.info("No open trades to monitor.") # Can be noisy, so commented out
        return

    # 2. Fetch current prices for all needed symbols efficiently
    prices = {}
    for symbol in unique_symbols:
        price = get_current_price(symbol)
        if price:
            prices[symbol] = price
        else:
            logger.warning(f"Could not fetch price for {symbol}, skipping checks for it.")

    if not prices:
        logger.error("Market monitor failed: Could not fetch price for any open trade symbols.")
        return

    # 3. Check all open trades for all users
    open_trades = db.get_all_open_trades()
    for trade in open_trades:
        symbol = trade['coin_symbol']
        if symbol not in prices:
            continue

        current_price = prices[symbol]
        notification = None
        close_reason = None

        pnl_percent = ((current_price - trade['buy_price']) / trade['buy_price']) * 100
        if current_price <= trade['stop_loss_price']:
            notification = f"🛡️ **Stop-Loss Triggered!** Your {symbol} quest (ID: {trade['id']}) was closed at `${current_price:,.8f}` (P/L: {pnl_percent:.2f}%)."
            close_reason = "Stop-Loss"
        elif current_price >= trade['take_profit_price']:
            notification = f"🎉 **Take-Profit Hit!** Your {symbol} quest (ID: {trade['id']}) was closed at `${current_price:,.8f}` (P/L: {pnl_percent:.2f}%). Congratulations!"
            close_reason = "Take-Profit"

        if notification:
            logger.info(f"Closing trade {trade['id']} for user {trade['user_id']} due to: {close_reason}")
            db.close_trade(trade_id=trade['id'], user_id=trade['user_id'], sell_price=current_price)
            try:
                await context.bot.send_message(chat_id=trade['user_id'], text=notification, parse_mode='Markdown')
            except Exception as e:
                logger.error(f"Failed to send auto-close notification to user {trade['user_id']}: {e}")

        # Part 3: Proactive RSI-based sell suggestion (if the trade is still open)
        if not notification:
            trade_suggestion_key = f"suggestion_{trade['id']}"
            current_rsi = get_rsi(symbol)

            if current_rsi and current_rsi > config.RSI_SELL_THRESHOLD:
                # If we haven't already sent a suggestion for this high-RSI state
                if not context.bot_data.get(trade_suggestion_key, False):
                    suggestion_message = (
                        f"💡 **Strategic Suggestion for {symbol}** (Quest ID: {trade['id']}) 💡\n\n"
                        f"The hourly RSI is now **{current_rsi:.2f}**, which is above the sell threshold of {config.RSI_SELL_THRESHOLD}.\n\n"
                        f"You might consider taking profits. Your current P/L is **{pnl_percent:.2f}%**.\n\n"
                        f"To close this quest, use: `/close {trade['id']}`"
                    )

                    # Add context about market conditions
                    market_state = context.bot_data.get('market_state', 'CALM')
                    if market_state == 'BTC_PUMP':
                        suggestion_message += "\n\n*Market Context: BTC is currently pumping, which may be driving this price action.*"
                    elif market_state == 'BTC_DUMP':
                        suggestion_message += "\n\n*Market Context: Be cautious, BTC is currently dumping. This could be a short-lived bounce.*"

                    if is_weekend():
                        suggestion_message += "\n\n*Note: It's the weekend, which can mean unpredictable volatility.*"

                    try:
                        await context.bot.send_message(chat_id=trade['user_id'], text=suggestion_message, parse_mode='Markdown')
                        context.bot_data[trade_suggestion_key] = True # Mark suggestion as sent
                        logger.info(f"Sent high-RSI sell suggestion for trade {trade['id']}")
                    except Exception as e:
                        logger.error(f"Failed to send sell suggestion for trade {trade['id']}: {e}")
            # If RSI drops back below the threshold, reset the suggestion flag so it can trigger again in the future.
            elif context.bot_data.get(trade_suggestion_key, False):
                context.bot_data[trade_suggestion_key] = False
                logger.info(f"Reset sell suggestion flag for trade {trade['id']} as RSI dropped.")

async def import_last_trade_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Imports a trade. Can fetch the last trade from Binance or log a manual price.
    Usage:
    /import <SYMBOL> - Fetches last trade from Binance.
    /import <SYMBOL> <PRICE> - Logs a trade at a specific price.
    """
    if not client:
        await update.message.reply_text("The connection to the crypto realm (Binance) is not configured.")
        return

    if not context.args:
        await update.message.reply_text("Please specify a trading pair. Usage: `/import CTKUSDT` or `/import CTKUSDT 0.75`", parse_mode='Markdown')
        return

    symbol = context.args[0].upper()
    manual_price = None
    if len(context.args) > 1:
        try:
            manual_price = float(context.args[1])
            if manual_price <= 0:
                await update.message.reply_text("The price must be a positive number.")
                return
        except ValueError:
            await update.message.reply_text("The price you provided is not a valid number. Usage: `/import CTKUSDT 0.75`", parse_mode='Markdown')
            return

    user_id = update.effective_user.id

    if db.is_trade_open(user_id, symbol):
        await update.message.reply_text(f"You already have an open quest for {symbol}. Use /status to see it.")
        return

    buy_price = 0.0

    if manual_price is not None:
        buy_price = manual_price
        await update.message.reply_text(f"Manually logging your {symbol} quest at a price of `${buy_price:,.8f}`... ✍️")
    else:
        await update.message.reply_text(f"Searching your Binance history for your last {symbol} spot trade... 📜")
        last_trade = get_last_trade_from_binance(symbol)

        if not last_trade:
            await update.message.reply_text(
                f"Could not find any recent spot trade history for {symbol}.\n\n"
                "**Note:** This can happen if you used **Binance Convert**. To log it, please provide the price manually:\n"
                "`/import SYMBOL PRICE` (e.g., `/import CTKUSDT 0.75`)",
                parse_mode='Markdown'
            )
            return

        if not last_trade['isBuyer']:
            await update.message.reply_text(
                f"Your last spot trade for {symbol} was a sell, not a buy.\n\n"
                "If you bought it via **Binance Convert** or another method, please provide the price manually:\n"
                "`/import SYMBOL PRICE` (e.g., `/import CTKUSDT 0.75`)",
                parse_mode='Markdown'
            )
            return

        buy_price = float(last_trade['price'])

    # Log the trade (common for both manual and automatic imports)
    stop_loss_price = buy_price * (1 - config.STOP_LOSS_PERCENTAGE / 100)
    take_profit_price = buy_price * (1 + config.PROFIT_TARGET_PERCENTAGE / 100)

    db.log_trade(user_id=user_id, coin_symbol=symbol, buy_price=buy_price, stop_loss=stop_loss_price, take_profit=take_profit_price)

    message = (
        f"✅ **Quest Imported!**\n\n"
        f"Successfully logged your {symbol} quest.\n"
        f"   - Bought at: `${buy_price:,.8f}`\n"
        f"   - ✅ Take Profit: `${take_profit_price:,.8f}`\n"
        f"   - 🛡️ Stop Loss: `${stop_loss_price:,.8f}`\n\n"
        f"I will now monitor this quest for you. Check its progress with /status."
    )
    await update.message.reply_text(message, parse_mode='Markdown')