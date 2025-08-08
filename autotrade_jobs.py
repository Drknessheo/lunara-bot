
import logging
from telegram.ext import ContextTypes
import trade
import slip_manager
import config
import google.generativeai as genai
import asyncio
import modules.db_access as autotrade_db

logger = logging.getLogger(__name__)

async def get_trade_suggestions_from_gemini(symbols):
    if not config.GEMINI_API_KEY:
        logger.warning("GEMINI_API_KEY not found. Cannot get trade suggestions.")
        return {}

    model = genai.GenerativeModel('gemini-1.5-flash')
    suggestions = {}

    for symbol in symbols:
        try:
            rsi = trade.get_rsi(symbol)
            upper_band, sma, lower_band, bb_std = trade.get_bollinger_bands(symbol)
            macd, macd_signal, macd_hist = trade.get_macd(symbol)
            micro_vwap = trade.get_micro_vwap(symbol)
            volume_ratio = trade.get_bid_ask_volume_ratio(symbol)
            mad = trade.get_mad(symbol)

            prompt = (
                f"Analyze the current market for {symbol} using these metrics:\n"
                f"RSI: {rsi}\n"
                f"Bollinger Bands: upper={upper_band}, sma={sma}, lower={lower_band}, std={bb_std}\n"
                f"MACD: {macd}, Signal: {macd_signal}, Histogram: {macd_hist}\n"
                f"Micro-VWAP: {micro_vwap}\n"
                f"Bid/Ask Volume Ratio: {volume_ratio}\n"
                f"MAD: {mad}\n"
                "Should I buy now for a small gain? Answer with only 'buy' or 'hold'."
            )
            response = await model.generate_content_async(prompt)
            decision = response.text.strip().lower()
            if decision in ['buy', 'hold']:
                suggestions[symbol] = decision
        except Exception as e:
            logger.error(f"Error getting Gemini suggestion for {symbol}: {e}")
        await asyncio.sleep(1)  # Add a 1-second delay between requests

    return suggestions

async def autotrade_cycle(context: ContextTypes.DEFAULT_TYPE):
    logger.info("Starting autotrade cycle...")
    user_id = config.ADMIN_USER_ID

    if not autotrade_db.get_autotrade_status(user_id):
        logger.info("Autotrade is disabled. Skipping cycle.")
        return

    monitored_coins = config.AI_MONITOR_COINS
    suggestions = await get_trade_suggestions_from_gemini(monitored_coins)

    for symbol, decision in suggestions.items():
        if decision == 'buy':
            try:
                usdt_balance = trade.get_account_balance(user_id, 'USDT')
                if usdt_balance is None or usdt_balance < 10:
                    logger.warning(f"Insufficient balance to autotrade {symbol}.")
                    continue

                trade_size = usdt_balance * 0.1  # Use 10% of balance for each trade
                order, entry_price, quantity = trade.place_buy_order(user_id, symbol, trade_size)

                slip_manager.create_and_store_slip(symbol, 'buy', quantity, entry_price)

                await context.bot.send_message(
                    chat_id=user_id,
                    text=f"🤖 Autotrade executed: Bought {quantity:.4f} {symbol} at ${entry_price:.8f}"
                )
            except trade.TradeError as e:
                logger.error(f"Error executing autotrade for {symbol}: {e}")

async def monitor_autotrades(context: ContextTypes.DEFAULT_TYPE):
    logger.info("Monitoring open autotrades...")
    encrypted_slips = slip_manager.redis_client.keys('*')

    for encrypted_slip in encrypted_slips:
        try:
            slip = slip_manager.get_and_decrypt_slip(encrypted_slip)
            current_price = trade.get_current_price(slip['symbol'])
            if not current_price:
                continue

            pnl_percent = ((current_price - slip['price']) / slip['price']) * 100

            if pnl_percent >= autotrade_db.get_user_effective_settings(config.ADMIN_USER_ID)['PROFIT_TARGET_PERCENTAGE']:
                trade.place_sell_order(config.ADMIN_USER_ID, slip['symbol'], slip['amount'])
                slip_manager.delete_slip(encrypted_slip)

                await context.bot.send_message(
                    chat_id=config.ADMIN_USER_ID,
                    text=f"🤖 Autotrade closed: Sold {slip['amount']:.4f} {slip['symbol']} at ${current_price:.8f} for a {pnl_percent:.2f}% gain."
                )
        except Exception as e:
            logger.error(f"Error monitoring autotrade: {e}")
