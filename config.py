import os
from dotenv import load_dotenv

# Load environment variables from a .env file
load_dotenv()

# Telegram and Binance API credentials from .env file
TELEGRAM_BOT_TOKEN = os.getenv("BOT_TOKEN")
BINANCE_API_KEY = os.getenv("BINANCE_API_KEY")
BINANCE_SECRET_KEY = os.getenv("BINANCE_SECRET_KEY")
CHAT_ID = os.getenv("CHAT_ID") # For global bot alerts
ADMIN_USER_ID = int(os.getenv("ADMIN_USER_ID")) if os.getenv("ADMIN_USER_ID") else None
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GDRIVE_REMOTE_NAME = os.getenv("GDRIVE_REMOTE_NAME") # For database backups

# --- Database Configuration ---
DB_NAME = "sprttrade.db" # Can be moved to .env if needed

# --- Global Market & Bot Behavior Settings (Not Tier-Dependent) ---

# Strategic Alert configuration
BTC_ALERT_THRESHOLD_PERCENT = 2.0  # Alert if BTC moves more than this % in 1 hour.

# Dip-Buying Logic
RSI_BUY_RECOVERY_THRESHOLD = 32.0 # Buy if RSI crosses above this after dipping below RSI_BUY_THRESHOLD.
WATCHLIST_TIMEOUT_HOURS = 24      # Remove from watchlist after this many hours.

# --- Paper Trading ---
PAPER_TRADE_SIZE_USDT = 1000.0
PAPER_STARTING_BALANCE = 10000.0


# --- Subscription Tier Configuration ---
# This structure allows for easy management of different user levels.
# In the future, the bot's logic will check a user's subscription
# and apply the appropriate settings. For now, we can set a global default.

SUBSCRIPTION_TIERS = {
    'FREE': {
        'NAME': 'Free',
        # Basic fixed trading parameters
        'RSI_BUY_THRESHOLD': 30.0,
        'RSI_SELL_THRESHOLD': 70.0,
        'PROFIT_TARGET_PERCENTAGE': 10.0,
        'STOP_LOSS_PERCENTAGE': 5.0,
        # Feature flags for this tier
        'USE_TRAILING_TAKE_PROFIT': False,
        'USE_BOLLINGER_BANDS': False,
        'ALLOWED_COIN_TYPES': ['MAJOR'], # e.g., only BTC, ETH, BNB
    },
    'PREMIUM': {
        'NAME': 'Premium',
        # Core trading parameters (can be customized by user later)
        'RSI_BUY_THRESHOLD': 30.0,
        'RSI_SELL_THRESHOLD': 70.0,
        'PROFIT_TARGET_PERCENTAGE': 25.0, # Default, can be overridden by dynamic logic
        'STOP_LOSS_PERCENTAGE': 10.0,     # Default, can be overridden by dynamic logic

        # --- Dynamic Logic & Advanced Features ---
        # Trailing Take Profit: Sells if price drops X% from a recent peak
        'USE_TRAILING_TAKE_PROFIT': True,
        'TRAILING_PROFIT_ACTIVATION_PERCENT': 15.0, # Trailing activates after this % profit
        'TRAILING_STOP_DROP_PERCENT': 5.0,          # Sell if price drops this % from peak

        # Bollinger Bands (BOLL) Intelligence
        'USE_BOLLINGER_BANDS': True,
        'BOLL_PERIOD': 20,
        'BOLL_STD_DEV': 2,
        'BOLL_SQUEEZE_ALERT_ENABLED': True,
        'BOLL_SQUEEZE_THRESHOLD': 0.08, # Alert if (Upper-Lower)/Middle band is less than this

        # Enhanced RSI Signals
        'RSI_OVERBOUGHT_ALERT_THRESHOLD': 80.0, # Send special alert if RSI exceeds this

        # DeFi & Altcoin Support
        'ALLOWED_COIN_TYPES': ['MAJOR', 'DEFI', 'ALTCOIN'],
        'DEFI_TOKEN_LIST': [ # Example list, can be expanded
            'UNIUSDT', 'AAVEUSDT', 'LINKUSDT', 'MKRUSDT', 'SNXUSDT', 'COMPUSDT'
        ],
    }
}

# --- Helper function to get current settings ---
# This will be crucial for the rest of the code to adapt to the tier system.
def get_active_settings(tier: str):
    """
    Returns the settings dictionary for the given subscription tier.
    """
    # Fallback to FREE tier if the configured tier is invalid
    return SUBSCRIPTION_TIERS.get(tier.upper(), SUBSCRIPTION_TIERS['FREE'])