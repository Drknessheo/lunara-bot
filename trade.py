import logging
import numpy as np
import time
from datetime import datetime, timezone
from binance.client import Client
from binance.exceptions import BinanceAPIException
from telegram import Update
from telegram.ext import ContextTypes
import pandas as pd

import config
import db

logger = logging.getLogger(__name__)

class TradeError(Exception):
    """Custom exception for trading errors that can be shown to the user."""
    pass

# Initialize Binance client
if config.BINANCE_API_KEY and config.BINANCE_SECRET_KEY:
    client = Client(config.BINANCE_API_KEY, config.BINANCE_SECRET_KEY)
else:
    logger.warning("Binance API keys not found. Trading functions will be disabled.")
    client = None

def get_user_client(user_id: int):
    """Creates a Binance client instance for a specific user using their stored keys."""
    api_key, secret_key = db.get_user_api_keys(user_id)
    if not api_key or not secret_key:
        logger.warning(f"API keys not found for user {user_id}.")
        return None
    try:
        return Client(api_key, secret_key)
    except Exception as e:
        logger.error(f"Failed to create Binance client for user {user_id}: {e}")
        return None

def is_weekend():
    """Checks if the current day is Saturday or Sunday (UTC)."""
    # weekday() returns 5 for Saturday, 6 for Sunday
    return datetime.now(timezone.utc).weekday() >= 5

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

def get_bollinger_bands(symbol, interval=Client.KLINE_INTERVAL_1HOUR, period=20, std_dev=2):
    """Calculates Bollinger Bands for a given symbol."""
    try:
        # Fetch more klines to ensure SMA calculation is accurate
        klines = client.get_historical_klines(symbol, interval, f"{period + 50} hours ago UTC")
        if len(klines) < period:
            return None, None, None, None

        closes = np.array([float(k[4]) for k in klines])

        # Calculate SMA and Standard Deviation for the most recent `period`
        sma = np.mean(closes[-period:])
        std = np.std(closes[-period:])

        upper_band = sma + (std * std_dev)
        lower_band = sma - (std * std_dev)
        return upper_band, sma, lower_band, std
    except Exception as e:
        logger.error(f"An unexpected error occurred getting Bollinger Bands for {symbol}: {e}")
        return None, None, None, None

def get_macd(symbol, interval=Client.KLINE_INTERVAL_1HOUR, fast_period=12, slow_period=26, signal_period=9):
    """Calculates the MACD for a given symbol."""
    try:
        # Fetch enough klines for the slow EMA + signal line
        klines = client.get_historical_klines(symbol, interval, f"{slow_period + signal_period + 50} hours ago UTC")
        if len(klines) < slow_period + signal_period:
            return None, None, None

        closes = pd.Series([float(k[4]) for k in klines])

        # Calculate EMAs
        ema_fast = closes.ewm(span=fast_period, adjust=False).mean()
        ema_slow = closes.ewm(span=slow_period, adjust=False).mean()

        # Calculate MACD line
        macd_line = ema_fast - ema_slow

        # Calculate Signal line
        signal_line = macd_line.ewm(span=signal_period, adjust=False).mean()

        # Calculate MACD Histogram
        macd_histogram = macd_line - signal_line

        # Return the most recent values
        return macd_line.iloc[-1], signal_line.iloc[-1], macd_histogram.iloc[-1]
    except Exception as e:
        logger.error(f"An unexpected error occurred getting MACD for {symbol}: {e}")
        return None, None, None

def get_account_balance(user_id: int, asset="USDT"):
    """Fetches the free balance for a specific asset from the Binance spot account."""
    user_client = get_user_client(user_id)
    if not user_client:
        return None
    try:
        balance = user_client.get_asset_balance(asset=asset)
        return float(balance['free']) if balance else 0.0
    except BinanceAPIException as e:
        logger.error(f"Binance API error getting account balance for user {user_id}: {e}")
        # Pass the specific error message up to the command handler
        raise TradeError(f"Binance API Error: {e.message}")
    except Exception as e:
        logger.error(f"An unexpected error occurred getting account balance for user {user_id}: {e}")
        raise TradeError(f"An unexpected error occurred: {e}")

def get_last_trade_from_binance(user_id: int, symbol: str):
    """Fetches the user's most recent trade for a given symbol from Binance."""
    user_client = get_user_client(user_id)
    if not user_client: return None
    try:
        # Fetch the last trade. The list is ordered from oldest to newest.
        trades = user_client.get_my_trades(symbol=symbol, limit=1) # type: ignore
        if not trades:
            return None
        return trades[0] # The most recent trade
    except BinanceAPIException as e:
        logger.error(f"Binance API error getting last trade for {symbol} for user {user_id}: {e}")
        return None
    except Exception as e:
        logger.error(f"An unexpected error occurred getting last trade for {symbol} for user {user_id}: {e}")
        return None

def place_buy_order(user_id: int, symbol: str, usdt_amount: float):
    """Places a live market buy order on Binance for a specific user."""
    user_client = get_user_client(user_id)
    if not user_client:
        logger.error(f"Cannot place buy order for user {user_id}: client not available.")
        raise TradeError("Binance client is not available. Please check your API keys.")

    try:
        logger.info(f"Attempting to BUY {usdt_amount} USDT of {symbol} for user {user_id}...")
        # Use quoteOrderQty for market buys to specify the amount in USDT
        order = user_client.create_order( # type: ignore
            symbol=symbol,
            side=Client.SIDE_BUY,
            type=Client.ORDER_TYPE_MARKET,
            quoteOrderQty=usdt_amount
        )
        logger.info(f"LIVE BUY order successful for {symbol} for user {user_id}: {order}")

        # Extract details from the fill(s)
        entry_price = float(order['fills'][0]['price'])
        quantity = float(order['executedQty'])
        
        return order, entry_price, quantity

    except BinanceAPIException as e:
        logger.error(f"LIVE BUY order failed for {symbol} for user {user_id}: {e.message}")
        raise TradeError(f"Binance API Error: {e.message}")
    except Exception as e:
        logger.error(f"An unexpected error occurred during LIVE BUY for {symbol} for user {user_id}: {e}")
        raise TradeError(f"An unexpected error occurred: {e}")

async def quest_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handles the /quest command, providing price and RSI for a given symbol.
    Usage: /quest <SYMBOL> (e.g., /quest PEPEUSDT)
    """
    if not client:
        await update.message.reply_text("The connection to the crypto realm (Binance) is not configured. Please check API keys.")
        return

    try:
        symbol = context.args[0].upper()
    except IndexError:
        await update.message.reply_text("Please specify a trading pair. Usage: `/quest BTCUSDT`", parse_mode='Markdown')
        return

    user_id = update.effective_user.id
    settings = db.get_user_effective_settings(user_id)

    # Check if a trade is already open or on the watchlist for this symbol
    if db.is_trade_open(user_id, symbol):
        await update.message.reply_text(f"You already have an open quest for {symbol}. Use /status to see it.")
        return

    if db.is_on_watchlist(user_id, symbol):
        await update.message.reply_text(f"You are already watching {symbol} for a dip. Use /status to check.")
        return

    await update.message.reply_text(f"Lunessa is gazing into the cosmic energies of {symbol}... 🔮")
    price = get_current_price(symbol)
    rsi = get_rsi(symbol)

    if price is not None and rsi is not None:
        message = (
            f"**Cosmic Insight: {symbol}**\n\n"
            f"✨ **Current Price:** `${price:,.8f}`\n"
            f"⚖️ **Hourly RSI({14}):** `{rsi:.2f}`\n\n"
        )

        # --- Premium Feature: Enhanced Buy Signal with Bollinger Bands ---
        is_bollinger_buy = False
        is_premium_user = settings.get('USE_BOLLINGER_BANDS')
        if settings.get('USE_BOLLINGER_BANDS'):
            _, _, lower_band, _ = get_bollinger_bands(
                symbol,
                period=settings.get('BOLL_PERIOD', 20),
                std_dev=settings.get('BOLL_STD_DEV', 2)
            )
            if lower_band:
                message += f"📊 **Lower Bollinger Band:** `${lower_band:,.8f}`\n\n"
                if price <= lower_band:
                    is_bollinger_buy = True

        # --- Determine Buy Condition based on user tier ---
        is_rsi_low = rsi < settings['RSI_BUY_THRESHOLD']

        # For premium users, both conditions must be met. For free users, only RSI.
        should_add_to_watchlist = (is_premium_user and is_rsi_low and is_bollinger_buy) or \
                                  (not is_premium_user and is_rsi_low)

        if should_add_to_watchlist:
            db.add_to_watchlist(user_id=user_id, coin_symbol=symbol)

            if is_premium_user: # This implies a strong, combined signal was found
                message += (
                    f"**⭐ Premium Signal!** The price has pierced the lower Bollinger Band while the RSI is low. A confluence of energies suggests a prime opportunity.\n\n"
                )

            message += (
                f"The energies for {symbol} are low. I will watch it for the perfect moment to strike (buy the dip) and notify you.\n\n"
                f"*I will automatically open a quest if the RSI shows signs of recovery.*"
            )
            if is_weekend():
                message += "\n\n*Note: Weekend trading can have lower volume and higher risk. Please trade with caution.*"
        elif rsi > settings['RSI_SELL_THRESHOLD']:
            message += "The energies are high. It may be a time to consider taking profits."
        else:
            message += "The market is in balance. Patience is a virtue."

        message += "\n*New to trading?* Join Binance with my link!"

        await update.message.reply_text(message, parse_mode='Markdown')
    else:
        await update.message.reply_text(f"Could not retrieve data for {symbol}. Please ensure it's a valid symbol on Binance (e.g., BTCUSDT).")

async def balance_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles the /balance command."""
    user_id = update.effective_user.id
    mode, paper_balance = db.get_user_trading_mode_and_balance(user_id)

    if mode == 'PAPER':
        await update.message.reply_text(f"You are in Paper Trading mode.\n💰 **Paper Balance:** ${paper_balance:,.2f} USDT", parse_mode='Markdown')
        return

    # Live mode logic
    api_key, _ = db.get_user_api_keys(user_id)
    if not api_key:
        await update.message.reply_text("Your Binance API keys are not set. Please use `/setapi <key> <secret>` in a private chat with me.")
        return

    
    await update.message.reply_text("Checking your treasure chest (Binance)...")
    try:
        balance = get_account_balance(user_id, asset="USDT")
        if balance is not None:
            await update.message.reply_text(f"You hold **{balance:.2f} USDT**.", parse_mode='Markdown')
    except TradeError as e:
        # This will now catch the specific error message from the API
        await update.message.reply_text(f"Could not retrieve your balance.\n\n*Reason:* `{e}`\n\nPlease check your API key permissions and IP restrictions on Binance.", parse_mode='Markdown')

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

async def check_watchlist_for_buys(context: ContextTypes.DEFAULT_TYPE, prices: dict, indicator_cache: dict):
    """Monitors coins on the watchlist to find a dip-buy opportunity."""
    watchlist_items = db.get_all_watchlist_items()
    if not watchlist_items:
        return

    logger.info(f"Checking {len(watchlist_items)} item(s) on the watchlist for dip-buy opportunities...") # type: ignore

    now = datetime.now(timezone.utc)

    for item in watchlist_items:
        symbol = item['coin_symbol'] # type: ignore
        item_id = item['id']
        user_id = item['user_id']
        settings = db.get_user_effective_settings(user_id)

        # Check for timeout
        add_time = datetime.datetime.strptime(item['add_timestamp'], '%Y-%m-%d %H:%M:%S')
        hours_passed = (now - add_time).total_seconds() / 3600
        if hours_passed > config.WATCHLIST_TIMEOUT_HOURS:
            db.remove_from_watchlist(item_id)
            logger.info(f"Removed {symbol} from watchlist for user {user_id} due to timeout.")
            try:
                await context.bot.send_message(
                    chat_id=user_id,
                    text=f"⏳ Your watch on **{symbol}** has expired without a buy signal. The opportunity has passed for now.",
                    parse_mode='Markdown'
                )
            except Exception as e:
                logger.error(f"Failed to send watchlist timeout notification to user {user_id}: {e}")
            continue

        # Check for buy signal (RSI recovery)
        # Use cache to avoid redundant API calls
        if symbol not in indicator_cache:
            try:
                indicator_cache[symbol] = {'rsi': get_rsi(symbol)}
                time.sleep(0.1) # Stagger API calls to be safe
            except BinanceAPIException as e:
                logger.warning(f"API error getting RSI for watchlist item {symbol}: {e}")
                continue # Skip this symbol for this run # type: ignore

        cached_data = indicator_cache.get(symbol, {})
        current_rsi = cached_data.get('rsi')

        if current_rsi and current_rsi > settings.get('RSI_BUY_RECOVERY_THRESHOLD', config.RSI_BUY_RECOVERY_THRESHOLD):
            # We have a buy signal!
            # Use the pre-fetched price
            buy_price = prices.get(symbol)
            if not buy_price:
                logger.warning(f"Could not get price for {symbol} to execute watchlist buy. Will retry.")
                continue

            # Check user's trading mode
            mode, paper_balance = db.get_user_trading_mode_and_balance(user_id)

            # --- LIVE TRADING LOGIC ---
            if mode == 'LIVE':
                # Check live balance
                usdt_balance = get_account_balance(user_id, 'USDT')
                if usdt_balance is None or usdt_balance < 10: # Use a minimum trade value like 10 USDT
                     logger.info(f"User {user_id} has insufficient LIVE USDT balance ({usdt_balance}) to open trade for {symbol}.")
                     continue
                
                # Use a fixed trade size for now. This can be made a user setting later.
                trade_size_usdt = 12.0
                if usdt_balance < trade_size_usdt:
                    trade_size_usdt = usdt_balance # Use what's available if less than desired

                try:
                    order, entry_price, quantity = place_buy_order(user_id, symbol, trade_size_usdt)

                    stop_loss_price = entry_price * (1 - settings['STOP_LOSS_PERCENTAGE'] / 100)
                    take_profit_price = entry_price * (1 + settings['PROFIT_TARGET_PERCENTAGE'] / 100)
                    db.log_trade(user_id=user_id, coin_symbol=symbol, buy_price=entry_price,
                                 stop_loss=stop_loss_price, take_profit=take_profit_price,
                                 mode='LIVE', quantity=quantity)
                    db.remove_from_watchlist(item_id)
                    logger.info(f"Executed LIVE dip-buy for {symbol} for user {user_id} at price {entry_price}")

                    # Notify user
                    message = (
                        f"🎯 **Live Quest Started!** 🎯\n\n"
                        f"Lunessa has executed a **LIVE** buy for **{quantity:.4f} {symbol}** after spotting a recovery!\n\n"
                        f"   - Bought at: `${entry_price:,.8f}`\n"
                        f"   - ✅ Take Profit: `${take_profit_price:,.8f}`\n"
                        f"   - 🛡️ Stop Loss: `${stop_loss_price:,.8f}`\n\n"
                        f"Use /status to see your open quests."
                    )
                    await context.bot.send_message(chat_id=user_id, text=message, parse_mode='Markdown')
                except TradeError as e:
                    await context.bot.send_message(
                        chat_id=user_id, text=f"⚠️ **Live Buy FAILED** for {symbol}.\n\n*Reason:* `{e}`\n\nPlease check your account balance and API key permissions.", parse_mode='Markdown'
                    )

            # --- PAPER TRADING LOGIC ---
            elif mode == 'PAPER':
                trade_size_usdt = config.PAPER_TRADE_SIZE_USDT
                if paper_balance < trade_size_usdt:
                    logger.info(f"User {user_id} has insufficient paper balance to open trade for {symbol}.")
                    continue
                
                db.update_paper_balance(user_id, -trade_size_usdt)
                
                entry_price = buy_price # For paper trades, we use the fetched market price
                stop_loss_price = entry_price * (1 - settings['STOP_LOSS_PERCENTAGE'] / 100)
                take_profit_price = entry_price * (1 + settings['PROFIT_TARGET_PERCENTAGE'] / 100)
                db.log_trade(user_id=user_id, coin_symbol=symbol, buy_price=entry_price,
                             stop_loss=stop_loss_price, take_profit=take_profit_price,
                             mode='PAPER', trade_size_usdt=trade_size_usdt)
                db.remove_from_watchlist(item_id)
                logger.info(f"Executed PAPER dip-buy for {symbol} for user {user_id} at price {entry_price}")
                
                message = (
                    f"🎯 **Paper Quest Started!** 🎯\n\n"
                    f"Lunessa has opened a new **PAPER** quest for **{symbol}** after spotting a recovery!\n\n"
                    f"   - Bought at: `${entry_price:,.8f}`\n"
                    f"   - ✅ Take Profit: `${take_profit_price:,.8f}`\n"
                    f"   - 🛡️ Stop Loss: `${stop_loss_price:,.8f}`\n\n"
                    f"Use /status to see your open quests."
                )
                await context.bot.send_message(chat_id=user_id, text=message, parse_mode='Markdown')

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

    # --- Step 1: Fetch all market prices in a single batch call ---
    try:
        all_tickers = client.get_all_tickers()
        prices = {item['symbol']: float(item['price']) for item in all_tickers}
        # Store prices in bot_data for other commands to use as a cache
        context.bot_data['all_prices'] = {
            'prices': prices, # type: ignore
            'timestamp': datetime.now(timezone.utc)
        }
    except BinanceAPIException as e:
        if e.status_code in [429, 418]:
            logger.warning(f"Rate limit hit during price fetch. Pausing monitor. Message: {e.message}")
        else:
            logger.error(f"API error fetching all tickers: {e}")
        return # Exit this run
    except Exception as e:
        logger.error(f"Generic error fetching all tickers: {e}")
        return

    # --- Step 2: Initialize a cache for this run to store calculated indicators ---
    indicator_cache = {}

    # --- Step 3: Run monitoring sub-tasks, passing the fetched data ---
    await check_btc_volatility_and_alert(context)
    await check_watchlist_for_buys(context, prices, indicator_cache)

    # --- Step 4: Check individual open trades ---
    open_trades = db.get_all_open_trades()
    for trade in open_trades:
        symbol = trade['coin_symbol']
        if symbol not in prices:
            continue

        settings = db.get_user_effective_settings(trade['user_id'])

        current_price = prices[symbol]
        notification = None
        close_reason = None

        pnl_percent = ((current_price - trade['buy_price']) / trade['buy_price']) * 100 # type: ignore

        # --- Stop-Loss is the ultimate safety net, check it first ---
        if current_price <= trade['stop_loss_price']:
            notification = f"🛡️ **Stop-Loss Triggered!** Your {symbol} quest (ID: {trade['id']}) was closed at `${current_price:,.8f}` (P/L: {pnl_percent:.2f}%)."
            close_reason = "Stop-Loss"

        # --- If not stopped out, check profit-taking logic ---
        else:
            # --- Premium Feature: Trailing Take Profit ---
            if settings.get('USE_TRAILING_TAKE_PROFIT'):
                is_trailing_active = trade['peak_price'] is not None

                if is_trailing_active:
                    peak_price = trade['peak_price']

                    # Update peak price if a new high is reached
                    if current_price > peak_price:
                        db.activate_trailing_stop(trade['id'], current_price)
                        peak_price = current_price # Update for current iteration

                    # Check if the price dropped below the trailing stop
                    trailing_stop_price = peak_price * (1 - settings['TRAILING_STOP_DROP_PERCENT'] / 100)
                    if current_price <= trailing_stop_price:
                        notification = (
                            f"📈 **Trailing Stop Triggered!** Your {symbol} quest (ID: {trade['id']}) "
                            f"was closed at `${current_price:,.8f}` (P/L: {pnl_percent:.2f}%).\n"
                            f"*Peak price reached: `${peak_price:,.8f}`*"
                        )
                        close_reason = "Trailing Stop"

                # --- Trailing Stop Activation Logic ---
                elif pnl_percent >= settings['TRAILING_PROFIT_ACTIVATION_PERCENT']:
                    # Activate the trailing stop for the first time
                    db.activate_trailing_stop(trade['id'], current_price)
                    logger.info(f"Activated trailing stop for trade {trade['id']} at price {current_price}")

                    # Send a one-time notification to the user
                    activation_msg = (
                        f"🔔 **Trailing Stop Activated for {symbol}!** (Quest ID: {trade['id']})\n\n"
                        f"Your quest has reached **{pnl_percent:.2f}%** profit. I will now secure your gains by trailing the price.\n\n"
                        f"The stop will adjust upwards as the price rises."
                    )
                    try:
                        await context.bot.send_message(chat_id=trade['user_id'], text=activation_msg, parse_mode='Markdown')
                    except Exception as e:
                        logger.error(f"Failed to send trailing stop activation message to user {trade['user_id']}: {e}")

                # --- Fallback to fixed Take-Profit if trailing is not yet active ---
                elif current_price >= trade['take_profit_price']:
                    notification = f"🎉 **Take-Profit Hit!** Your {symbol} quest (ID: {trade['id']}) was closed at `${current_price:,.8f}` (P/L: {pnl_percent:.2f}%). Congratulations!"
                    close_reason = "Take-Profit"

            # --- Logic for FREE users (or if trailing is disabled) ---
            elif current_price >= trade['take_profit_price']:
                notification = f"🎉 **Take-Profit Hit!** Your {symbol} quest (ID: {trade['id']}) was closed at `${current_price:,.8f}` (P/L: {pnl_percent:.2f}%). Congratulations!"
                close_reason = "Take-Profit"

        if notification:
            logger.info(f"Closing trade {trade['id']} for user {trade['user_id']} due to: {close_reason}")
            
            # --- Trade Execution Logic ---
            if trade['mode'] == 'LIVE':
                if trade['quantity'] and trade['quantity'] > 0:
                    user_client = get_user_client(trade['user_id'])
                    if user_client:
                        try:
                            logger.info(f"Attempting to place MARKET SELL for {trade['quantity']} {symbol} for user {trade['user_id']}")
                            # IMPORTANT: This places a real order on Binance
                            order = user_client.order_market_sell(symbol=symbol, quantity=trade['quantity'])
                            logger.info(f"Successfully executed market sell for trade {trade['id']}. Order ID: {order['orderId']}")
                            # Add execution confirmation to the notification
                            notification += "\n\n**✅ Successfully executed on Binance.**"
                        except BinanceAPIException as e:
                            logger.error(f"Binance API error executing sell for trade {trade['id']}: {e}")
                            notification += f"\n\n**⚠️ Binance Execution FAILED:** `{e.message}`. Please close the trade manually."
                        except Exception as e:
                            logger.error(f"Generic error executing sell for trade {trade['id']}: {e}")
                            notification += "\n\n**⚠️ An unknown error occurred during execution.** Please check Binance manually."
                    else:
                        notification += "\n\n**⚠️ Execution FAILED:** Could not create Binance client for user."
                else:
                    logger.warning(f"Cannot execute LIVE sell for trade {trade['id']}: quantity not available.")
                    notification += "\n\n**⚠️ Execution SKIPPED:** The quantity for this trade was not recorded. Please close manually."
            
            elif trade['mode'] == 'PAPER':
                # Close the paper trade in the DB
                success = db.close_trade(trade_id=trade['id'], user_id=trade['user_id'], sell_price=current_price)
                if success:
                    # Update the paper balance
                    profit_or_loss = (current_price - trade['buy_price']) * (trade['trade_size_usdt'] / trade['buy_price'])
                    db.update_paper_balance(trade['user_id'], profit_or_loss)
                    logger.info(f"Updated paper balance for user {trade['user_id']} by ${profit_or_loss:.2f}")
                    notification += "\n\n*This was a paper trade.*"

            # Send the final notification to the user
            try:
                await context.bot.send_message(chat_id=trade['user_id'], text=notification, parse_mode='Markdown')
            except Exception as e:
                logger.error(f"Failed to send final trade close notification to user {trade['user_id']}: {e}")

        # --- Premium Feature: Bollinger Bands Intelligence ---
        if settings.get('USE_BOLLINGER_BANDS') and not notification: # Only if trade is still open
            # Check cache for indicators first
            if symbol not in indicator_cache:
                try:
                    # Calculate and cache indicators for this symbol
                    rsi = get_rsi(symbol)
                    upper, mid, lower, std = get_bollinger_bands(symbol, period=settings.get('BOLL_PERIOD', 20), std_dev=settings.get('BOLL_STD_DEV', 2))
                    indicator_cache[symbol] = {'rsi': rsi, 'bbands': (upper, mid, lower, std)}
                    time.sleep(0.1) # Stagger API calls
                except BinanceAPIException as e:
                    if e.status_code in [429, 418]:
                        logger.warning(f"Rate limit hit fetching indicators for {symbol}. Skipping symbol for this run.")
                    else:
                        logger.error(f"API error fetching indicators for {symbol}: {e}")
                    continue # Skip this trade for this run
                except Exception as e:
                    logger.error(f"Generic error fetching indicators for {symbol}: {e}")
                    continue

            cached_data = indicator_cache.get(symbol, {})
            upper_band, middle_band, lower_band, std = cached_data.get('bbands', (None, None, None, None))
            if upper_band and middle_band and lower_band: # Check if we got valid data
                # 1. Upper Band Alert
                boll_alert_key = f"boll_alert_{trade['id']}"
                if current_price >= upper_band and not context.bot_data.get(boll_alert_key, False):
                    alert_message = (
                        f"📈 **Volatility Alert for {symbol}** (Quest ID: {trade['id']}) 📈\n\n"
                        f"The price has touched or broken the upper Bollinger Band at `${upper_band:,.8f}`.\n\n"
                        f"This indicates high volatility. Consider tightening your stop-loss or taking profits. Your current P/L is **{pnl_percent:.2f}%**."
                    )
                    try:
                        await context.bot.send_message(chat_id=trade['user_id'], text=alert_message, parse_mode='Markdown')
                        context.bot_data[boll_alert_key] = True
                        logger.info(f"Sent Bollinger Upper Band alert for trade {trade['id']}")
                    except Exception as e:
                        logger.error(f"Failed to send Bollinger alert for trade {trade['id']}: {e}")
                elif current_price < middle_band and context.bot_data.get(boll_alert_key, False):
                    # Reset the alert flag once the price returns to the middle band
                    context.bot_data[boll_alert_key] = False
                    logger.info(f"Reset Bollinger Upper Band alert flag for trade {trade['id']}.")

                # 2. Squeeze Expansion Alert
                squeeze_alert_key = f"squeeze_alert_{symbol}_{trade['user_id']}" # Per user, per symbol
                if settings.get('BOLL_SQUEEZE_ALERT_ENABLED'):
                    band_width = (upper_band - lower_band) / middle_band
                    is_squeezing = band_width < settings.get('BOLL_SQUEEZE_THRESHOLD', 0.08)

                    if is_squeezing and not context.bot_data.get(squeeze_alert_key, False):
                        context.bot_data[squeeze_alert_key] = True
                        logger.info(f"Bollinger Squeeze detected for {symbol} for user {trade['user_id']}. Awaiting expansion.")
                    elif not is_squeezing and context.bot_data.get(squeeze_alert_key, False):
                        alert_message = f"💥 **Volatility Expansion for {symbol}** 💥\n\n" \
                                        "The Bollinger Bands are expanding after a squeeze. Expect a significant price move soon. Please monitor your positions."
                        try:
                            await context.bot.send_message(chat_id=trade['user_id'], text=alert_message, parse_mode='Markdown')
                            logger.info(f"Sent Bollinger Squeeze expansion alert for {symbol} to user {trade['user_id']}")
                        except Exception as e:
                            logger.error(f"Failed to send squeeze alert for {symbol} to user {trade['user_id']}: {e}")
                        finally:
                            context.bot_data[squeeze_alert_key] = False

        # Part 3: Proactive RSI-based sell suggestion (if the trade is still open)
        if not notification:
            trade_suggestion_key = f"suggestion_{trade['id']}"

            # Use cached RSI if available, otherwise fetch it
            if symbol in indicator_cache and 'rsi' in indicator_cache[symbol]:
                current_rsi = indicator_cache[symbol]['rsi']
            else:
                current_rsi = get_rsi(symbol)
                if symbol not in indicator_cache: indicator_cache[symbol] = {}
                indicator_cache[symbol]['rsi'] = current_rsi

            if current_rsi and current_rsi > settings['RSI_SELL_THRESHOLD']:
                # If we haven't already sent a suggestion for this high-RSI state
                if not context.bot_data.get(trade_suggestion_key, False):
                    suggestion_message = (
                        f"💡 **Strategic Suggestion for {symbol}** (Quest ID: {trade['id']}) 💡\n\n"
                        f"The hourly RSI is now **{current_rsi:.2f}**, which is above the sell threshold of {settings['RSI_SELL_THRESHOLD']}.\n\n"
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
    settings = db.get_user_effective_settings(user_id)

    if db.is_trade_open(user_id, symbol):
        await update.message.reply_text(f"You already have an open quest for {symbol}. Use /status to see it.")
        return

    buy_price = 0.0
    quantity = None

    if manual_price is not None:
        buy_price = manual_price
        await update.message.reply_text(f"Manually logging your {symbol} quest at a price of `${buy_price:,.8f}`... ✍️")
    else:
        api_key, _ = db.get_user_api_keys(user_id)
        if not api_key:
            await update.message.reply_text("To import from Binance, your API keys must be set. Please use `/setapi <key> <secret>` in a private chat with me.")
            return

        await update.message.reply_text(f"Searching your Binance history for your last {symbol} spot trade... 📜")
        last_trade = get_last_trade_from_binance(user_id, symbol)

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
        quantity = float(last_trade['qty'])

    # Log the trade (common for both manual and automatic imports)
    stop_loss_price = buy_price * (1 - settings['STOP_LOSS_PERCENTAGE'] / 100)
    take_profit_price = buy_price * (1 + settings['PROFIT_TARGET_PERCENTAGE'] / 100)

    # Check user's trading mode for imported trades
    # Imported trades are always considered 'LIVE' unless user is in paper mode
    user_mode, _ = db.get_user_trading_mode_and_balance(user_id) 
    trade_mode = 'LIVE'
    trade_size = None
    if user_mode == 'PAPER':
        trade_mode = 'PAPER'
        trade_size = config.PAPER_TRADE_SIZE_USDT

    db.log_trade(user_id=user_id, coin_symbol=symbol, buy_price=buy_price, stop_loss=stop_loss_price, take_profit=take_profit_price, mode=trade_mode, trade_size_usdt=trade_size, quantity=quantity)

    message = (
        f"✅ **Quest Imported!**\n\n"
        f"Successfully logged your {symbol} quest.\n"
        f"   - Bought at: `${buy_price:,.8f}`\n"
        f"   - ✅ Take Profit: `${take_profit_price:,.8f}`\n"
        f"   - 🛡️ Stop Loss: `${stop_loss_price:,.8f}`\n\n"
        f"I will now monitor this quest for you. Check its progress with /status."
    )
    await update.message.reply_text(message, parse_mode='Markdown')
