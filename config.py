# Coins to monitor for AI trading logic
AI_MONITOR_COINS = [
    'BTCUSDT', 'ETHUSDT', 'BNBUSDT', 'SOLUSDT', 'ADAUSDT', 'XRPUSDT', 'DOGEUSDT', 'MATICUSDT', 'DOTUSDT', 'AVAXUSDT',
    'LINKUSDT', 'ARBUSDT', 'OPUSDT', 'LTCUSDT', 'TRXUSDT', 'SHIBUSDT', 'PEPEUSDT', 'UNIUSDT', 'SUIUSDT', 'INJUSDT', 'RNDRUSDT',
    'PENGUUSDT', 'CTKUSDT', 'OMBTC', 'ENAUSDT', 'HYPERUSDT', 'BABYUSDT', 'KAITOUSDT'
]

# --- Per-trade allocation limit (as a percentage of available USDT balance) ---
PER_TRADE_ALLOCATION_PERCENT = 5.0 # Example: Allocate 5% of available USDT per trade

# --- Telegram Sync Log ---
TELEGRAM_SYNC_LOG_ENABLED = True # Set to True to enable trade sync logs via Telegram
# Interval (in minutes) for the AI autotrade monitor job
AI_TRADE_INTERVAL_MINUTES = 10
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
ADMIN_REFERRAL_CODE = os.getenv("ADMIN_REFERRAL_CODE") # For the /referral command
GDRIVE_REMOTE_NAME = "LuneesaBook" # For database backups

# --- Database Configuration ---
DB_NAME = "lunara_bot.db" # Dedicated database file for reliability

# --- Global Market & Bot Behavior Settings (Not Tier-Dependent) ---

# Strategic Alert configuration
BTC_ALERT_THRESHOLD_PERCENT = 2.0  # Alert if BTC moves more than this % in 1 hour.
HELD_TOO_LONG_HOURS = 48           # Alert if a trade is open longer than this.
NEAR_STOP_LOSS_THRESHOLD_PERCENT = 2.0 # Alert if price is within this % of stop-loss.
NEAR_TAKE_PROFIT_THRESHOLD_PERCENT = 2.0 # Alert if price is within this % of the take-profit target.

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
    'PROFIT_TARGET_PERCENTAGE': 1.0,
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
    'PROFIT_TARGET_PERCENTAGE': 1.0, # Default, can be overridden by dynamic logic
        'STOP_LOSS_PERCENTAGE': 4.0,     # Default, can be overridden by dynamic logic

        # --- Dynamic Logic & Advanced Features ---
        # Trailing Take Profit: Sells if price drops X% from a recent peak
        'USE_TRAILING_TAKE_PROFIT': True,
        'TRAILING_PROFIT_ACTIVATION_PERCENT': 7.0, # Trailing activates after this % profit
        'TRAILING_STOP_DROP_PERCENT': 3.0,          # Sell if price drops this % from peak

        # Bollinger Bands (BOLL) Intelligence
        'USE_BOLLINGER_BANDS': True,
        'BOLL_PERIOD': 20,
        'BOLL_STD_DEV': 2,
        'BOLL_SQUEEZE_ALERT_ENABLED': True,
        'BOLL_SQUEEZE_THRESHOLD': 0.08, # Alert if (Upper-Lower)/Middle band is less than this

        # Enhanced RSI Signals
        'RSI_OVERBOUGHT_ALERT_THRESHOLD': 80.0, # Send special alert if RSI exceeds this
        'RSI_BEARISH_EXIT_THRESHOLD': 65.0,

        # --- Dynamic Stop-Loss (DSLA) ---
        'DSLA_MODE': 'step_ladder', # Other modes: 'volatility_based', 'ATR_based'
        'DSLA_LADDER': [
            {'profit': 5.0, 'sl': 0.0},    # At +5% profit, move SL to breakeven
            {'profit': 8.0, 'sl': 3.0},    # At +8% profit, move SL to +3%
            {'profit': 12.0, 'sl': 6.0}    # At +12% profit, move SL to +6%
        ],

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