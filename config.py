import os
from dotenv import load_dotenv

# Load environment variables from a .env file
load_dotenv()

# Telegram and Binance API credentials from .env file
TELEGRAM_BOT_TOKEN = os.getenv("BOT_TOKEN")
BINANCE_API_KEY = os.getenv("BINANCE_API_KEY")
BINANCE_SECRET_KEY = os.getenv("BINANCE_SECRET_KEY")
CHAT_ID = os.getenv("CHAT_ID")

# Database configuration
DB_NAME = "sprttrade.db"

# Trading parameters from your plan
RSI_BUY_THRESHOLD = 30.0
RSI_SELL_THRESHOLD = 70.0
PROFIT_TARGET_PERCENTAGE = 25.0
STOP_LOSS_PERCENTAGE = 10.0

# Strategic Alert configuration
BTC_ALERT_THRESHOLD_PERCENT = 2.0  # Alert if BTC moves more than this % in 1 hour.

# Dip-Buying Logic
RSI_BUY_RECOVERY_THRESHOLD = 32.0 # Buy if RSI crosses above this after dipping below 30.
WATCHLIST_TIMEOUT_HOURS = 24      # Remove from watchlist after this many hours.