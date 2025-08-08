import logging
logger = logging.getLogger("tradebot")
logger.setLevel(logging.INFO)
if not logger.hasHandlers():
    handler = logging.StreamHandler()
    formatter = logging.Formatter('%(asctime)s %(levelname)s %(message)s')
    handler.setFormatter(formatter)
    logger.addHandler(handler)

# --- TradeError Exception ---
class TradeError(Exception):
    pass

from telegram import Update
from telegram.ext import CommandHandler, ContextTypes
HELP_MESSAGE = (
    "🤖 *Lunessa Shi’ra Gork* – Automated Crypto Trading Bot\n\n"
    "*Features:*\n"
    "- Rule-driven signals (RSI, MACD, Bollinger Bands)\n"
    "- Risk controls: stop-loss, trailing stop, allocation\n"
    "- LIVE/TEST modes\n"
    "- Telegram alerts and remote control\n\n"
    "*Main Commands:*\n"
    "/help – Show usage and features\n"
    "/status – Show wallet and trade status\n"
    "/import – Import trades manually\n"
    "/about – Learn more about Lunessa\n\n"
    "*Supported Coins:*\n"
    "BTCUSDT, ETHUSDT, BNBUSDT, SOLUSDT, ADAUSDT, XRPUSDT, DOGEUSDT, MATICUSDT, DOTUSDT, AVAXUSDT, LINKUSDT, ARBUSDT, OPUSDT, LTCUSDT, TRXUSDT, SHIBUSDT, PEPEUSDT, UNIUSDT, SUIUSDT, INJUSDT, RNDRUSDT, PENGUUSDT, CTKUSDT, OMBTC, ENAUSDT, HYPERUSDT, BABYUSDT, KAITOUSDT\n\n"
    "*Get started:* Add your Binance API keys and Telegram bot token, then run the bot!"
)

ABOUT_MESSAGE = (
    "*About Lunessa Shi’ra Gork*\n\n"
    "Lunessa is your AI-powered crypto trading companion. She monitors markets, manages risk, and keeps you updated via Telegram.\n\n"
    "Project: https://github.com/Drknessheo/lunara-bot\n"
    "License: MIT\n"
)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(HELP_MESSAGE, parse_mode='Markdown')

async def about_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(ABOUT_MESSAGE, parse_mode='Markdown')

import logging
import numpy as np
import time
import asyncio
import math
from datetime import datetime, timezone
import logging
import numpy as np
from indicators import calc_atr
from risk_management import get_trade_size, get_atr_stop, update_daily_pl, should_pause_trading, is_market_crash_or_big_buyer
from modules.monitoring import ai_trade_monitor
from modules.adaptive_strategy import adaptive_strategy_job
from binance.client import Client
from binance.exceptions import BinanceAPIException
from telegram import Update
from telegram.ext import ContextTypes
import pandas as pd
from functools import lru_cache
import re

from Simulation import resonance_engine
from trading_module import TradeAction
import config
from modules import db_access as db
import memory
import statistics

# --- Market Crash/Big Buyer Shield ---
# Now imported from risk_management.py

@lru_cache(maxsize=128)
def get_symbol_info(symbol: str):
    """
    Fetches and caches trading rules for a symbol, like precision.
    Returns a dictionary with symbol information or None on error.
    """
    try:
        if not client:
            return None
        return client.get_symbol_info(symbol)
    except BinanceAPIException as e:
        logger.error(f"Could not fetch symbol info for {symbol}: {e}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error fetching symbol info for {symbol}: {e}")
        return None

# Initialize Binance client
if config.BINANCE_API_KEY and config.BINANCE_SECRET_KEY:
    client = Client(config.BINANCE_API_KEY, config.BINANCE_SECRET_KEY)
else:
    logger.warning("Binance API keys not found. Trading functions will be disabled.")
    client = None

def get_user_client(user_id: int):
    """Creates a Binance client instance for a specific user using their stored keys."""
    # For the admin user, prioritize API keys from config.py (loaded from .env)
    if user_id == config.ADMIN_USER_ID:
        if config.BINANCE_API_KEY and config.BINANCE_SECRET_KEY:
            try:
                return Client(config.BINANCE_API_KEY, config.BINANCE_SECRET_KEY)
            except Exception as e:
                logger.error(f"Failed to create Binance client for ADMIN_USER_ID from config: {e}")
                return None
        else:
            logger.warning("ADMIN_USER_ID detected, but BINANCE_API_KEY or BINANCE_SECRET_KEY not found in config.")
            return None

    # For other users, fetch API keys from the database
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

def get_all_spot_balances(user_id: int) -> list[dict] | None:
    """Fetches all non-zero asset balances from the user's Binance spot account."""
    user_client = get_user_client(user_id)
    if not user_client:
        logger.warning(f"Cannot get spot balances for user {user_id}: client not available.")
        return None
    try:
        account_info = user_client.get_account()
        balances = [
            b for b in account_info.get('balances', [])
            if float(b['free']) > 0 or float(b['locked']) > 0
        ]
        return balances
    except BinanceAPIException as e:
        logger.error(f"Binance API error getting all balances for user {user_id}: {e}")
        raise TradeError(f"Binance API Error: {e.message}")
    except Exception as e:
        logger.error(f"Unexpected error getting all balances for user {user_id}: {e}")
        raise TradeError(f"An unexpected error occurred: {e}")

def place_buy_order(user_id: int, symbol: str, usdt_amount: float, is_test=False):
    """Places a live market buy order on Binance for a specific user."""
    user_client = get_user_client(user_id)
    if not user_client:
        logger.error(f"Cannot place buy order for user {user_id}: client not available.")
        raise TradeError("Binance client is not available. Please check your API keys.")

    # --- Get Symbol Trading Rules ---
    info = get_symbol_info(symbol)
    if not info:
        raise TradeError(f"Could not retrieve trading rules for {symbol}.")

    # --- Validate Order against Filters (minNotional, stepSize) ---
    min_notional = 0.0
    step_size = 0.0
    for f in info['filters']:
        if f['filterType'] == 'NOTIONAL':
            min_notional = float(f['minNotional'])
        if f['filterType'] == 'LOT_SIZE':
            step_size = float(f['stepSize'])

    if usdt_amount < min_notional:
        raise TradeError(f"Order value of ${usdt_amount:.2f} is below the minimum of ${min_notional:.2f} for {symbol}.")

    try:
        logger.info(f"Attempting to BUY {usdt_amount} USDT of {symbol} for user {user_id}...")
        # Use quoteOrderQty for market buys to specify the amount in USDT
        order = user_client.create_order( # type: ignore
            symbol=symbol,
            side=Client.SIDE_BUY,
            type=Client.ORDER_TYPE_MARKET,
            quoteOrderQty=usdt_amount
        )
        if is_test:
            # In a test, we can't get fill details, so we simulate them.
            # This part is for unit testing or dry runs if you expand on that.
            return {"symbol": symbol, "orderId": "test_order"}, get_current_price(symbol), usdt_amount / get_current_price(symbol)

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

def place_sell_order(user_id: int, symbol: str, quantity: float):
    """Places a live market sell order on Binance for a specific user."""
    user_client = get_user_client(user_id)
    if not user_client:
        logger.error(f"Cannot place SELL order for user {user_id}: client not available.")
        raise TradeError("Binance client is not available for selling.")

    info = get_symbol_info(symbol)
    if not info:
        raise TradeError(f"Could not retrieve trading rules for {symbol} to sell.")

    # Format quantity according to the symbol's stepSize filter
    step_size = float([f['stepSize'] for f in info['filters'] if f['filterType'] == 'LOT_SIZE'][0])
    precision = int(round(-math.log(step_size, 10), 0))
    formatted_quantity = f"{quantity:.{precision}f}"

    try:
        logger.info(f"Attempting to SELL {formatted_quantity} of {symbol} for user {user_id}...")
        order = user_client.order_market_sell(symbol=symbol, quantity=formatted_quantity)
        logger.info(f"LIVE SELL order successful for {symbol} for user {user_id}: {order}")
        return order
    except BinanceAPIException as e:
        logger.error(f"LIVE SELL order failed for {symbol} for user {user_id}: {e.message}")
        raise TradeError(f"Binance API Error on Sell: {e.message}")

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

async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles the /status command, showing open trades and wallet holdings."""
    user_id = update.effective_user.id
    mode, paper_balance = db.get_user_trading_mode_and_balance(user_id)

    message = f"✨ **Your Current Status ({mode} Mode)** ✨\n\n"

    # --- Display Open Trades ---
    open_trades = db.get_open_trades(user_id)
    if open_trades:
        message += "📊 **Open Quests:**\n"
        for trade_item in open_trades:
            symbol = trade_item['coin_symbol']
            buy_price = trade_item['buy_price']
            quantity = trade_item['quantity']
            trade_id = trade_item['id']
            
            # Attempt to get current price for P/L calculation
            current_price = get_current_price(symbol)
            pnl_text = ""
            if current_price:
                pnl_percent = ((current_price - buy_price) / buy_price) * 100
                pnl_text = f" (P/L: `{pnl_percent:+.2f}%`)"
            
            message += (
                f"- **{symbol}** (ID: {trade_id})\n"
                f"  - Bought: `${buy_price:,.8f}`\n"
                f"  - Qty: `{quantity:.4f}`{pnl_text}\n"
            )
        message += "\n"
    else:
        message += "📊 **Open Quests:** None\n\n"

    # --- Display Watchlist ---
    watchlist_items = db.get_all_watchlist_items_for_user(user_id)
    if watchlist_items:
        message += "👀 **Watching for Dips:**\n"
        for item in watchlist_items:
            message += f"- **{item['coin_symbol']}** (Added: {item['add_timestamp']})\n"
        message += "\n"
    else:
        message += "👀 **Watching for Dips:** None\n\n"

    # --- Display Wallet Holdings (Live Mode Only) ---
    if mode == 'LIVE':
        message += "💰 **Wallet Holdings:**\n"
        try:
            wallet_balances = get_all_spot_balances(user_id)
            if wallet_balances:
                # Get symbols from open trades for differentiation
                open_trade_symbols = {trade_item['coin_symbol'].replace('USDT', '') for trade_item in open_trades}
                
                core_holdings_found = False
                for bal in wallet_balances:
                    asset = bal['asset']
                    free = float(bal['free'])
                    locked = float(bal['locked'])
                    total = free + locked

                    # Only show assets with a significant balance
                    if total > 0.00000001:
                        # Check if this asset is part of an open trade
                        if asset in open_trade_symbols:
                            message += f"- **{asset}:** `{total:.4f}` (Open Trade)\n"
                        else:
                            message += f"- **{asset}:** `{total:.4f}` (Core Holding)\n"
                            core_holdings_found = True
                if not core_holdings_found and not open_trades:
                    message += "  No significant core holdings found.\n"
            else:
                message += "  No assets found in your spot wallet.\n"
        except TradeError as e:
            message += f"  *Could not retrieve wallet balances: {e.message}*\n"
        except Exception as e:
            logger.error(f"Unexpected error fetching wallet balances for status: {e}")
            message += "  *An unexpected error occurred while fetching wallet balances.*\n"
    elif mode == 'PAPER':
        message += f"💰 **Paper Balance:** ${paper_balance:,.2f} USDT\n"

    await update.message.reply_text(message, parse_mode='Markdown')

async def import_last_trade_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles the /import command to manually add a trade or import from Binance."""
    user_id = update.effective_user.id
    mode, _ = db.get_user_trading_mode_and_balance(user_id)

    if mode == 'PAPER':
        await update.message.reply_text("Trade import is only available in LIVE trading mode.")
        return

    if not context.args:
        await update.message.reply_text(
            "Please specify a symbol, price, and quantity.\n"
            "Usage: `/import <SYMBOL> <PRICE> <QUANTITY>`\n"
            "Example: `/import BTCUSDT 30000 0.01`\n"
            "You can also use `/import <SYMBOL>` to auto-import your last Binance trade for that symbol.",
            parse_mode='Markdown'
        )
        return

    symbol = context.args[0].upper()
    buy_price = None
    quantity = None

    # Robust validation for symbol format and existence on Binance
    if not re.fullmatch(r"[A-Z0-9]+(USDT|BTC)", symbol):
        await update.message.reply_text(f"Invalid symbol format: `{symbol}`. Please use a valid Binance trading pair like `BTCUSDT` or `ETHBTC`.", parse_mode='Markdown')
        return

    # Check if symbol exists on Binance
    symbol_info = get_symbol_info(symbol)
    if not symbol_info:
        await update.message.reply_text(f"Symbol `{symbol}` does not exist on Binance or is not available for trading. Please check the symbol and try again.", parse_mode='Markdown')
        return

    try:
        if len(context.args) > 1:
            # Manual import with price and quantity (optional)
            buy_price = float(context.args[1])
            if len(context.args) > 2:
                quantity = float(context.args[2])
            else:
                # If price is given but quantity is not, try to get it from Binance
                last_trade = get_last_trade_from_binance(user_id, symbol)
                if last_trade and float(last_trade['price']) == buy_price:
                    quantity = float(last_trade['qty'])
                else:
                    await update.message.reply_text("For manual import, if quantity is not provided, the given price must match your last Binance trade for that symbol.")
                    return
        else:
            # Auto-import from Binance
            await update.message.reply_text(f"Attempting to import your last trade for {symbol} from Binance...")
            last_trade = get_last_trade_from_binance(user_id, symbol)

            if not last_trade:
                await update.message.reply_text(f"Could not find a recent trade for {symbol} on Binance. Please specify the buy price and quantity manually: `/import {symbol} <PRICE> <QUANTITY>`.", parse_mode='Markdown')
                return

            buy_price = float(last_trade['price'])
            quantity = float(last_trade['qty'])
            logger.info(f"Imported trade for {symbol}: price={buy_price}, quantity={quantity}")

        if buy_price and quantity:
            # Calculate stop loss and take profit based on current settings
            settings = db.get_user_effective_settings(user_id)
            stop_loss_price = buy_price * (1 - settings['STOP_LOSS_PERCENTAGE'] / 100)
            take_profit_price = buy_price * (1 + settings['PROFIT_TARGET_PERCENTAGE'] / 100)

            trade_id = db.log_trade(user_id=user_id, coin_symbol=symbol, buy_price=buy_price,
                                    stop_loss=stop_loss_price, take_profit=take_profit_price,
                                    mode='LIVE', quantity=quantity, rsi_at_buy=None) # RSI at buy is not available for imported trades

            await update.message.reply_text(
                f"✅ **Trade Imported!**\n\n"
                f"   - **{symbol}** (ID: {trade_id})\n"
                f"   - Bought at: `${buy_price:,.8f}`\n"
                f"   - Quantity: `{quantity:.4f}`\n"
                f"   - ✅ Take Profit: `${take_profit_price:,.8f}`\n"
                f"   - 🛡️ Stop Loss: `${stop_loss_price:,.8f}`\n\n"
                f"This trade will now be monitored. Use /status to see your open quests.",
                parse_mode='Markdown'
            )
        else:
            await update.message.reply_text("Could not determine trade details for import.")

    except ValueError:
        await update.message.reply_text("Invalid price or quantity. Please ensure they are numbers.")
    except TradeError as e:
        await update.message.reply_text(f"Error importing trade: {e}")
    except Exception as e:
        logger.error(f"An unexpected error occurred during trade import: {e}", exc_info=True)
        await update.message.reply_text("An unexpected error occurred while importing the trade.")

async def close_trade_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Manually closes an open trade by its ID."""
    user_id = update.effective_user.id

    if not context.args or not context.args[0].isdigit():
        await update.message.reply_text("Please provide the ID of the trade you want to close. Usage: `/close <TRADE_ID>`", parse_mode='Markdown')
        return

    trade_id = int(context.args[0])
    trade_to_close = db.get_trade_by_id(trade_id)

    if not trade_to_close or trade_to_close['user_id'] != user_id or trade_to_close['close_timestamp']:
        await update.message.reply_text(f"Trade with ID `{trade_id}` not found or already closed.", parse_mode='Markdown')
        return

    symbol = trade_to_close['coin_symbol']
    buy_price = trade_to_close['buy_price']
    quantity = trade_to_close['quantity']
    mode = trade_to_close['mode']

    current_price = get_current_price(symbol)
    if not current_price:
        await update.message.reply_text(f"Could not get current price for {symbol}. Please try again.")
        return

    pnl_percent = ((current_price - buy_price) / buy_price) * 100
    profit_usdt = (current_price - buy_price) * quantity if quantity else 0.0

    close_reason = "Manual Close"
    win_loss = 'win' if pnl_percent > 0 else ('loss' if pnl_percent < 0 else 'break_even')

    if mode == 'LIVE':
        try:
            # Attempt to sell on Binance
            if quantity and quantity > 0:
                await update.message.reply_text(f"Attempting to sell {quantity:.4f} of {symbol} on Binance...")
                place_sell_order(user_id, symbol, quantity)
                db.close_trade(trade_id=trade_id, user_id=user_id, sell_price=current_price, close_reason=close_reason, win_loss=win_loss, pnl_percentage=pnl_percent)
                update_daily_pl(profit_usdt, db)
                await update.message.reply_text(
                    f"✅ **Trade Closed!**\n\n"
                    f"Your **{symbol}** quest (ID: {trade_id}) was manually closed at `${current_price:,.8f}`.\n\n"
                    f"   - **P/L:** `{pnl_percent:+.2f}%` (`${profit_usdt:,.2f}` USDT)\n\n"
                    f"Your position on Binance has been sold.",
                    parse_mode='Markdown'
                )
            else:
                await update.message.reply_text(f"Cannot close trade {trade_id} on Binance: quantity is zero or not recorded.")
                db.close_trade(trade_id=trade_id, user_id=user_id, sell_price=current_price, close_reason=close_reason, win_loss=win_loss, pnl_percentage=pnl_percent)
                update_daily_pl(profit_usdt, db)
                await update.message.reply_text(
                    f"✅ **Trade Closed (Database Only)!**\n\n"
                    f"Your **{symbol}** quest (ID: {trade_id}) was manually closed at `${current_price:,.8f}`.\n\n"
                    f"   - **P/L:** `{pnl_percent:+.2f}%` (`${profit_usdt:,.2f}` USDT)\n\n"
                    f"*Note: No Binance sale was executed as quantity was not found or zero.*",
                    parse_mode='Markdown'
                )

        except TradeError as e:
            await update.message.reply_text(f"⚠️ **Failed to close trade {trade_id} on Binance.**\n\n*Reason:* `{e}`\n\nThe trade remains open in the bot's records. Please try again or close manually on Binance.", parse_mode='Markdown')
        except Exception as e:
            logger.error(f"An unexpected error occurred during manual trade close for {trade_id}: {e}", exc_info=True)
            await update.message.reply_text("An unexpected error occurred while trying to close the trade.")

    elif mode == 'PAPER':
        success = db.close_trade(trade_id=trade_id, user_id=user_id, sell_price=current_price, close_reason=close_reason, win_loss=win_loss, pnl_percentage=pnl_percent)
        if success:
            db.update_paper_balance(user_id, profit_usdt) # Update paper balance with profit/loss
            await update.message.reply_text(
                f"✅ **Paper Trade Closed!**\n\n"
                f"Your **{symbol}** paper quest (ID: {trade_id}) was manually closed at `${current_price:,.8f}`.\n\n"
                f"   - **P/L:** `{pnl_percent:+.2f}%` (`${profit_usdt:,.2f}` USDT)\n\n"
                f"Your paper balance has been updated.",
                parse_mode='Markdown'
            )
        else:
            await update.message.reply_text(f"Failed to close paper trade {trade_id}.")

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

    logger.info(f"Checking {len(watchlist_items)} item(s) on the watchlist for dip-buy opportunities...")

    now = datetime.now(timezone.utc)

    for item in watchlist_items:
        symbol = item['coin_symbol']
        item_id = item['id']
        user_id = item['user_id']
        settings = db.get_user_effective_settings(user_id)

        # Check for timeout
        add_time = datetime.strptime(item['add_timestamp'], '%Y-%m-%d %H:%M:%S').replace(tzinfo=timezone.utc)
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
        if symbol not in indicator_cache:
            try:
                indicator_cache[symbol] = {'rsi': get_rsi(symbol)}
                time.sleep(0.1) # Stagger API calls to be safe
            except BinanceAPIException as e:
                logger.warning(f"API error getting RSI for watchlist item {symbol}: {e}")
                continue

        cached_data = indicator_cache.get(symbol, {})
        current_rsi = cached_data.get('rsi')

        if current_rsi and current_rsi > settings.get('RSI_BUY_RECOVERY_THRESHOLD', config.RSI_BUY_RECOVERY_THRESHOLD):
            # We have a buy signal!
            buy_price = prices.get(symbol)
            if not buy_price:
                logger.warning(f"Could not get price for {symbol} to execute watchlist buy. Will retry.")
                continue

            mode, paper_balance = db.get_user_trading_mode_and_balance(user_id)

            # --- Risk Management: Pause trading if daily drawdown exceeded ---
            account_balance = get_account_balance(user_id, 'USDT')
            if should_pause_trading(db, account_balance, getattr(config, 'MAX_DAILY_DRAWDOWN_PERCENT', 0.10)):
                logger.info(f"Trading paused for user {user_id} due to daily drawdown limit.")
                continue

            if mode == 'LIVE':
                usdt_balance = account_balance
                if usdt_balance is None or usdt_balance < 5:
                    logger.info(f"User {user_id} has insufficient LIVE USDT balance ({usdt_balance}) to open trade for {symbol}.")
                    continue

                trade_size_usdt = get_trade_size(usdt_balance, getattr(config, 'MIN_TRADE_SIZE_USDT', 5.0), getattr(config, 'TRADE_RISK_PERCENT', 0.05))

                # --- ATR-based stop-loss ---
                klines = client.get_historical_klines(symbol, Client.KLINE_INTERVAL_1HOUR, "30 hours ago UTC")
                atr = calc_atr(klines, period=14) if klines else None

                try:
                    order, entry_price, quantity = place_buy_order(user_id, symbol, trade_size_usdt)
                    stop_loss_price = get_atr_stop(entry_price, atr, getattr(config, 'ATR_STOP_MULTIPLIER', 1.5)) if atr else entry_price * (1 - settings['STOP_LOSS_PERCENTAGE'] / 100)
                    take_profit_price = entry_price * (1 + settings['PROFIT_TARGET_PERCENTAGE'] / 100)
                    db.log_trade(user_id=user_id, coin_symbol=symbol, buy_price=entry_price,
                                 stop_loss=stop_loss_price, take_profit=take_profit_price,
                                 mode='LIVE', quantity=quantity, rsi_at_buy=current_rsi)
                    db.remove_from_watchlist(item_id)
                    logger.info(f"Executed LIVE dip-buy for {symbol} for user {user_id} at price {entry_price}")

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

            elif mode == 'PAPER':
                trade_size_usdt = config.PAPER_TRADE_SIZE_USDT
                if paper_balance < trade_size_usdt:
                    logger.info(f"User {user_id} has insufficient paper balance to open trade for {symbol}.")
                    continue
                
                db.update_paper_balance(user_id, -trade_size_usdt)
                
                entry_price = buy_price
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

async def ai_trade_monitor(context: ContextTypes.DEFAULT_TYPE, prices: dict, indicator_cache: dict):
    """The core AI logic to automatically open trades based on market signals."""
    logger.info("AI trade monitor is running...")
    # Market crash/big buyer shield
    if is_market_crash_or_big_buyer(prices):
        logger.warning("Trading paused due to market crash or big buyer activity.")
        return
    user_id = config.ADMIN_USER_ID
    if not user_id or not db.get_autotrade_status(user_id):
        return

    # --- Layer 1: Market Weather Filter ---
    def get_market_sentiment():
        try:
            klines = client.get_historical_klines("BTCUSDT", Client.KLINE_INTERVAL_1DAY, "60 days ago UTC")
            if len(klines) < 50:
                logger.warning("Not enough BTC kline data for market sentiment. Defaulting to BULLISH.")
                return "BULLISH"
            closes = [float(k[4]) for k in klines[-50:]]
            btc_price = closes[-1]
            btc_ma_50 = sum(closes) / len(closes)
            if btc_price > btc_ma_50:
                logger.info(f"Market Sentiment: BULLISH (BTC {btc_price:.2f} > MA50 {btc_ma_50:.2f})")
                return "BULLISH"
            else:
                logger.info(f"Market Sentiment: BEARISH (BTC {btc_price:.2f} < MA50 {btc_ma_50:.2f})")
                return "BEARISH"
        except Exception as e:
            logger.error(f"Error getting market sentiment: {e}. Defaulting to BULLISH.")
            return "BULLISH"

    market_sentiment = get_market_sentiment()
    if market_sentiment == "BEARISH":
        logger.info("Pausing new buys: Market sentiment is BEARISH")
        return

    settings = db.get_user_effective_settings(user_id)
    monitored_coins = getattr(config, "AI_MONITOR_COINS", [])

    for symbol in monitored_coins:
        if db.is_trade_open(user_id, symbol) or db.is_on_watchlist(user_id, symbol):
            logger.info(f"Skipping {symbol}: Already open or on watchlist.")
            continue

        if symbol not in indicator_cache:
            rsi = None
            upper = None
            lower = None
            macd = None
            macd_signal = None
            try:
                rsi = get_rsi(symbol)
                upper, _, lower, _ = get_bollinger_bands(symbol)
                macd, macd_signal, _ = get_macd(symbol)
                indicator_cache[symbol] = {'rsi': rsi, 'bbands': (upper, _, lower, _), 'macd': macd, 'macd_signal': macd_signal}
                time.sleep(0.2) # Stagger API calls
            except Exception as e:
                logger.error(f"Error fetching indicators for {symbol} in AI monitor: {e}")
                continue
        cached_data = indicator_cache.get(symbol, {})
        rsi = cached_data.get('rsi')
        lower_band = cached_data.get('bbands', (None, None, None, None))[2]
        current_price = prices.get(symbol)
        macd = cached_data.get('macd')
        macd_signal = cached_data.get('macd_signal') if 'macd_signal' in cached_data else None
        if rsi is None or lower_band is None or current_price is None or macd is None or macd_signal is None:
            logger.info(f"Skipping {symbol}: Missing indicator data.")
            continue

        rsi_is_low = rsi < settings['RSI_BUY_THRESHOLD']
        macd_bullish = macd > macd_signal
        price_below_lower_band = current_price < lower_band

        if not rsi_is_low:
            logger.info(f"Skipping {symbol}: RSI {rsi:.2f} not below {settings['RSI_BUY_THRESHOLD']}")
            continue
        if not macd_bullish:
            logger.info(f"Skipping {symbol}: MACD {macd:.4f} not above Signal {macd_signal:.4f}")
            continue
        if not price_below_lower_band:
            logger.info(f"Skipping {symbol}: Price {current_price:.4f} not below lower band {lower_band:.4f}")
            continue

        usdt_balance = get_account_balance(user_id, 'USDT')
        if usdt_balance is None or usdt_balance < 5:
            logger.info(f"Skipping {symbol}: USDT balance {usdt_balance} too low.")
            continue

        trade_size_usdt = usdt_balance * (config.PER_TRADE_ALLOCATION_PERCENT / 100)
        if trade_size_usdt < 5.0:
            logger.info(f"Skipping {symbol}: Trade size {trade_size_usdt:.2f} below minimum.")
            trade_size_usdt = 5.0
        if usdt_balance < trade_size_usdt:
            trade_size_usdt = usdt_balance

        try:
            order, entry_price, quantity = place_buy_order(user_id, symbol, trade_size_usdt)
            stop_loss_price = entry_price * (1 - settings['STOP_LOSS_PERCENTAGE'] / 100)
            take_profit_price = entry_price * (1 + settings['PROFIT_TARGET_PERCENTAGE'] / 100)
            db.log_trade(user_id=user_id, coin_symbol=symbol, buy_price=entry_price,
                         stop_loss=stop_loss_price, take_profit=take_profit_price,
                         mode='LIVE', quantity=quantity, rsi_at_buy=rsi, highest_price=entry_price)

            message = (
                f"🤖 **AI Autotrade Initiated!** 🤖\n\n"
                f"Detected a high-confidence buy signal for **{symbol}**.\n\n"
                f"   - Bought: **{quantity:.4f} {symbol}** at `${entry_price:,.8f}`\n"
                f"   - Value: `${trade_size_usdt:,.2f}` USDT\n"
                f"   - Strategy: RSI ({rsi:.2f}), MACD ({macd:.4f} > {macd_signal:.4f}), Price < Lower BB\n\n"
                f"Use /status to monitor this new quest."
            )
            await context.bot.send_message(chat_id=user_id, text=message, parse_mode='Markdown')

        except TradeError as e:
            logger.error(f"AI failed to execute buy for {symbol}: {e}")
            await context.bot.send_message(chat_id=user_id, text=f"⚠️ **AI Autotrade FAILED** for {symbol}.\n*Reason:* `{e}`", parse_mode='Markdown')
        except Exception as e:
            logger.error(f"An unexpected error occurred in AI trade execution for {symbol}: {e}", exc_info=True)

async def run_monitoring_cycle(context: ContextTypes.DEFAULT_TYPE, open_trades, prices, indicator_cache):
    """
    The intelligent core of the bot. Called by the JobQueue to:
    1. Monitor overall market conditions based on BTC movement.
    2. Check all open trades against their Stop-Loss and Take-Profit levels.
    """
    if not client:
        logger.warning("Market monitor skipped: Binance client not configured.")
        return

    logger.info("Running market monitor...")

    # Guard clause: handle empty open_trades
    if not open_trades:
        logger.info("No open trades to monitor. Checking for new trade opportunities.")
        await ai_trade_monitor(context)
        return

    logger.info(f"Monitoring {len(open_trades)} open trade(s)...")
    now = datetime.now(timezone.utc)
    for trade in open_trades:
        # Use .get for dicts, fallback for missing keys
        mode = trade.get('mode') if hasattr(trade, 'get') else trade['mode'] if 'mode' in trade else None
        buy_ts = trade.get('buy_timestamp') if hasattr(trade, 'get') else trade['buy_timestamp'] if 'buy_timestamp' in trade else None
        user_id = trade.get('user_id') if hasattr(trade, 'get') else trade['user_id'] if 'user_id' in trade else None
        symbol = trade.get('coin_symbol') if hasattr(trade, 'get') else trade['coin_symbol'] if 'coin_symbol' in trade else None
        if not symbol or symbol not in prices:
            continue
        current_price = prices[symbol]
        pnl_percent = ((current_price - trade['buy_price']) / trade['buy_price']) * 100 if 'buy_price' in trade else 0
        held_hours = None
        if buy_ts:
            try:
                buy_timestamp_dt = datetime.strptime(buy_ts, '%Y-%m-%d %H:%M:%S').replace(tzinfo=timezone.utc)
                held_hours = (now - buy_timestamp_dt).total_seconds() / 3600
            except (ValueError, TypeError):
                held_hours = None
        try:
            settings = db.get_user_effective_settings(user_id)
        except IndexError:
            logger.error(f"No settings found for user_id {user_id}, using default settings.")
            settings = db.get_user_effective_settings(None)
        notification = None
        close_reason = None

        # --- Risk Management: Update daily P/L after trade close ---
        if mode == 'LIVE' and buy_ts:
            user_client = get_user_client(user_id)
            if user_client:
                try:
                    buy_timestamp_dt = datetime.strptime(buy_ts, '%Y-%m-%d %H:%M:%S').replace(tzinfo=timezone.utc)
                    start_time_ms = int(buy_timestamp_dt.timestamp() * 1000)
                    binance_trades = user_client.get_my_trades(symbol=symbol, startTime=start_time_ms)

                    for binance_trade in binance_trades:
                        if not binance_trade['isBuyer']:
                            sell_price = float(binance_trade['price'])
                            db.close_trade(trade_id=trade['id'], user_id=trade['user_id'],
                                           sell_price=sell_price, close_reason="Manual Binance Sale")
                            pnl_percent_manual = ((sell_price - trade['buy_price']) / trade['buy_price']) * 100
                            notification = (
                                f"ℹ️ **Manual Sale Detected!** ℹ️\n\n"
                                f"I see you manually sold your **{symbol}** position on Binance for `${sell_price:,.8f}`.\n\n"
                                f"   - **P/L:** `{pnl_percent_manual:+.2f}%`\n"
                                f"   - **Quest ID:** {trade['id']}\n\n"
                                f"I've updated my records and closed this quest for you. Well done!"
                            )
                            close_reason = "Manual"
                            update_daily_pl(sell_price - trade['buy_price'], db)
                            break
                except BinanceAPIException as e:
                    logger.error(f"Binance API error during trade sync for user {trade['user_id']}: {e}")
                except Exception as e:
                    logger.error(f"Unexpected error during trade sync for user {trade['user_id']}: {e}")

        if current_price <= trade['stop_loss_price']:
            notification = f"🛡️ **Stop-Loss Triggered!** Your {symbol} quest (ID: {trade['id']}) was closed at `${current_price:,.8f}` (P/L: {pnl_percent:.2f}%)."
            close_reason = "Stop-Loss"
            db.close_trade(trade_id=trade['id'], user_id=trade['user_id'], sell_price=current_price, close_reason=close_reason, win_loss='loss', pnl_percentage=pnl_percent)
            update_daily_pl(current_price - trade['buy_price'], db)

        if notification and close_reason == "Manual":
            try:
                await context.bot.send_message(chat_id=trade['user_id'], text=notification, parse_mode='Markdown')
                logger.info(f"Detected and synced manual sale for trade {trade['id']}.")
            except Exception as e:
                logger.error(f"Failed to send manual sale notification for trade {trade['id']}: {e}")
            continue

        if pnl_percent > -1.0:
            if symbol not in indicator_cache:
                try:
                    indicator_cache[symbol] = {'rsi': get_rsi(symbol)}
                    time.sleep(0.1)
                except BinanceAPIException as e:
                    logger.warning(f"API error getting RSI for {symbol} for RSI exit: {e}")
                except Exception as e:
                    logger.error(f"Generic error getting RSI for {symbol} for RSI exit: {e}")

            current_rsi = indicator_cache.get(symbol, {}).get('rsi')

            if current_rsi and current_rsi < settings['RSI_SELL_THRESHOLD'] and 'rsi_at_buy' in trade and trade['rsi_at_buy'] > settings['RSI_SELL_THRESHOLD']:
                profit_usdt = (current_price - trade['buy_price']) * trade['quantity'] if trade['quantity'] else 0.0
                notification = (
                    f"📉 **RSI Exit Triggered!** Your {symbol} quest (ID: {trade['id']}) was closed at `${current_price:,.8f}`.\n\n"
                    f"   - **P/L:** `{pnl_percent:.2f}%` (`${profit_usdt:,.2f}` USDT)\n"
                    f"   - Current RSI: `{current_rsi:.2f}`"
                )
                close_reason = "RSI Exit"
                db.close_trade(trade_id=trade['id'], user_id=trade['user_id'], sell_price=current_price, close_reason=close_reason, win_loss='win' if pnl_percent > 0 else 'loss', pnl_percentage=pnl_percent)
                update_daily_pl(current_price - trade['buy_price'], db)
        # Near Stop-Loss alert
        stop_loss_price = trade.get('stop_loss_price')
        sl_threshold_price = stop_loss_price * (1 + config.NEAR_STOP_LOSS_THRESHOLD_PERCENT / 100) if stop_loss_price else None
        near_sl_key = f"near_sl_alert_{trade['id']}"
        if stop_loss_price and sl_threshold_price and current_price > stop_loss_price and current_price <= sl_threshold_price:
            if not context.bot_data.get(near_sl_key):
                distance_to_sl = ((current_price - stop_loss_price) / stop_loss_price) * 100
                alert_message = (
                    f"⚠️ **Danger Zone Alert for {symbol}** (ID: {trade['id']}) ⚠️\n\n"
                    f"The price is now just **{distance_to_sl:.2f}%** away from your stop-loss at `${stop_loss_price:,.8f}`.\n\n"
                    f"Consider reviewing your position. You can close this quest with `/close {trade['id']}`."
                )
                await context.bot.send_message(chat_id=trade['user_id'], text=alert_message, parse_mode='Markdown')
                context.bot_data[near_sl_key] = True
                logger.info(f"Sent 'Near Stop-Loss' alert for trade {trade['id']}")
        elif context.bot_data.get(near_sl_key):
            context.bot_data[near_sl_key] = False
            logger.info(f"Reset 'Near Stop-Loss' alert flag for trade {trade['id']} as price moved away from SL.")

        # Near Take-Profit alert
        take_profit_price = trade.get('take_profit_price')
        tp_threshold_percent = getattr(config, 'NEAR_TAKE_PROFIT_THRESHOLD_PERCENT', 2)
        tp_threshold_price = take_profit_price * (1 - tp_threshold_percent / 100) if take_profit_price else None
        near_tp_key = f"near_tp_alert_{trade['id']}"
        if take_profit_price and tp_threshold_price and current_price >= tp_threshold_price and not context.bot_data.get(near_tp_key):
            distance_to_tp = ((take_profit_price - current_price) / take_profit_price) * 100
            alert_message = (
                f"🚀 **Profit Target Approaching for {symbol}** (ID: {trade['id']}) 🚀\n\n"
                f"The price is now just **{distance_to_tp:.2f}%** away from your take-profit target of `${take_profit_price:,.8f}`.\n\n"
                f"Current P/L is **{pnl_percent:.2f}%**. Consider if you want to secure profits now with `/close {trade['id']}`."
            )
            await context.bot.send_message(chat_id=trade['user_id'], text=alert_message, parse_mode='Markdown')
            context.bot_data[near_tp_key] = True
            logger.info(f"Sent 'Near Take-Profit' alert for trade {trade['id']}")
        elif take_profit_price and tp_threshold_price and current_price < tp_threshold_price and context.bot_data.get(near_tp_key):
            context.bot_data[near_tp_key] = False
            logger.info(f"Reset 'Near Take-Profit' alert flag for trade {trade['id']}.")

        # Trade close logic
        win_loss = 'win' if pnl_percent > 0 else ('loss' if pnl_percent < 0 else 'break_even')
        if trade['mode'] == 'LIVE':
            if trade['quantity'] and trade['quantity'] > 0:
                # ...LIVE trade close logic here...
                # TODO: Implement LIVE trade close logic if needed
                pass
            else:
                # ...LIVE trade fallback logic here...
                # TODO: Implement LIVE trade fallback logic if needed
                pass
        elif trade['mode'] == 'PAPER':
            success = db.close_trade(trade_id=trade['id'], user_id=trade['user_id'], sell_price=current_price, close_reason=close_reason, win_loss=win_loss, pnl_percentage=pnl_percent)
            if success:
                # ...PAPER trade close logic here...
                # TODO: Implement PAPER trade close logic if needed
                pass
        if config.TELEGRAM_SYNC_LOG_ENABLED:
            # ...telegram sync log logic here...
            # TODO: Implement telegram sync log logic if needed
            pass
        if settings.get('USE_BOLLINGER_BANDS') and not notification:
            # ...bollinger bands logic here...
            # TODO: Implement bollinger bands logic if needed
            pass

async def prefetch_prices(open_trades: list) -> dict:
    """Fetches current prices for all symbols in open trades."""
    prices = {}
    symbols_to_fetch = {trade['coin_symbol'] for trade in open_trades}
    for symbol in symbols_to_fetch:
        price = get_current_price(symbol)
        if price:
            prices[symbol] = price
        await asyncio.sleep(0.05) # Small delay to avoid hitting rate limits
    return prices

async def prefetch_indicators(open_trades: list) -> dict:
    """Fetches indicators for all symbols in open trades."""
    indicator_cache = {}
    symbols_to_fetch = {trade['coin_symbol'] for trade in open_trades}
    for symbol in symbols_to_fetch:
        # Only fetch RSI for now, as it's used in the exit logic
        rsi = get_rsi(symbol)
        if rsi:
            indicator_cache[symbol] = {'rsi': rsi}
        await asyncio.sleep(0.05) # Small delay to avoid hitting rate limits
    return indicator_cache

async def scheduled_monitoring_job(context: ContextTypes.DEFAULT_TYPE):
    """
    This is the wrapper function called by APScheduler.
    It gathers the latest data and then calls the main monitoring logic.
    """
    logger.info("Running scheduled_monitoring_job...")
    user_id = config.ADMIN_USER_ID # Assuming monitoring is for the admin user
    if not user_id or not db.get_autotrade_status(user_id):
        logger.info("Scheduled monitoring skipped: Admin user not set or autotrade disabled.")
        return

    try:
        # 1. Gather all the data needed
        open_trades = db.get_open_trades(user_id) # Assuming get_open_trades can take user_id
        prices = await prefetch_prices(open_trades)
        indicator_cache = await prefetch_indicators(open_trades)

        # 2. Call your powerful function with all the required data
        await run_monitoring_cycle(context, open_trades, prices, indicator_cache)

    except Exception as e:
        logger.error(f"Error in scheduled_monitoring_job: {e}", exc_info=True)

async def adaptive_strategy_job():
    """Periodically analyze trade history and adapt strategy parameters."""
    logger.info("Running adaptive strategy job...")
    conn = db.get_db_connection()
    cursor = conn.execute("SELECT rsi_at_buy, pnl_percentage, coin_symbol FROM trades WHERE status = 'closed' AND rsi_at_buy IS NOT NULL AND pnl_percentage IS NOT NULL")
    rows = cursor.fetchall()
    if not rows:
        logger.info("No closed trades with RSI and PnL data for learning.")
        return
    # Analyze RSI thresholds
    profitable_rsi = [row['rsi_at_buy'] for row in rows if row['pnl_percentage'] > 0]
    if profitable_rsi:
        new_rsi_threshold = int(statistics.median(profitable_rsi))
        config.LAST_LEARNED_RSI_THRESHOLD = new_rsi_threshold
        logger.info(f"Adaptive strategy: Updated RSI buy threshold to {new_rsi_threshold}")
    # Analyze best coins
    coin_pnl = {}
    for row in rows:
        coin = row['coin_symbol']
        coin_pnl.setdefault(coin, []).append(row['pnl_percentage'])
    avg_coin_pnl = {c: statistics.mean(pnls) for c, pnls in coin_pnl.items() if pnls}
    best_coins = sorted(avg_coin_pnl, key=avg_coin_pnl.get, reverse=True)[:5]
    config.ADAPTIVE_TOP_COINS = best_coins
    logger.info(f"Adaptive strategy: Top performing coins: {best_coins}")
    # Optionally, adjust allocation or other parameters here
    # ...existing code...

# Schedule the adaptive strategy job (example: every 6 hours)
from apscheduler.schedulers.asyncio import AsyncIOScheduler

# Scheduler setup
from apscheduler.schedulers.asyncio import AsyncIOScheduler
scheduler = AsyncIOScheduler()
scheduler.add_job(adaptive_strategy_job, 'interval', hours=6)

def start_scheduler():
    scheduler.start()

from telegram import Update
from telegram.ext import CommandHandler, ContextTypes
from modules import db_access as db

async def usercount_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conn = db.get_db_connection()
    cursor = conn.execute("SELECT COUNT(*) FROM users")
    count = cursor.fetchone()[0]
    await update.message.reply_text(f"Total users: {count}")
