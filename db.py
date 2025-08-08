import logging
import sqlite3
import config
from config import DB_NAME
from security import encrypt_data, decrypt_data

logger = logging.getLogger(__name__)

# Global connection variable
_conn = None

def get_db_connection():
    """Establishes a connection to the SQLite database."""
    global _conn
    if _conn is None:
        _conn = sqlite3.connect(DB_NAME, check_same_thread=False)
        _conn.row_factory = sqlite3.Row  # Always return rows as dict-like objects
    return _conn

def close_db_connection():
    """Closes the database connection."""
    global _conn
    if _conn is not None:
        _conn.close()
        _conn = None

def initialize_database():
    """Creates the tables if they don't exist."""
    conn = get_db_connection()
    cursor = conn.cursor()
    # We add user_id to support multiple users
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            coin_symbol TEXT NOT NULL,
            buy_price REAL NOT NULL,
            buy_timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            status TEXT NOT NULL, -- e.g., 'open', 'closed'
            sell_price REAL,
            stop_loss_price REAL,
            take_profit_price REAL,
            peak_price REAL, -- For trailing take profit
            mode TEXT DEFAULT 'LIVE',
            trade_size_usdt REAL,
            quantity REAL, -- The actual amount of the coin bought
            close_reason TEXT,
            win_loss TEXT, -- 'win' or 'loss'
            pnl_percentage REAL, -- Profit/Loss percentage
            rsi_at_buy REAL -- RSI value at the time of buy
        );
    """)
    # Add a new table for coin performance tracking
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS coin_performance (
            coin_symbol TEXT PRIMARY KEY,
            wins INTEGER DEFAULT 0,
            losses INTEGER DEFAULT 0,
            total_pnl_percentage REAL DEFAULT 0.0
        );
    """)
    # Add a new table for the dip-buy watchlist
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS watchlist (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            coin_symbol TEXT NOT NULL,
            add_timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, coin_symbol)
        );
    """)
    # Add a new table for users, subscriptions, and API keys
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            api_key BLOB,
            secret_key BLOB,
            subscription_tier TEXT DEFAULT 'FREE',
            subscription_expires DATETIME,
            custom_rsi_buy REAL,
            custom_rsi_sell REAL,
            custom_stop_loss REAL,
            custom_trailing_activation REAL,
            custom_trailing_drop REAL,
            trading_mode TEXT DEFAULT 'LIVE',
            paper_balance REAL DEFAULT 10000.0,
            autotrade_enabled INTEGER DEFAULT NULL
        );
    """)
    # Add a new table for premium users
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS premium_users (
            user_id INTEGER PRIMARY KEY
        );
    """)
    conn.commit()
    logger.info("Database tables initialized successfully.")

def migrate_schema():
    """
    Checks the database schema and applies any necessary migrations,
    such as adding new columns to existing tables.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    changes_made = False

    # --- Schema Migration for trades table ---
    cursor.execute("PRAGMA table_info(trades)")
    trade_columns = [info[1] for info in cursor.fetchall()]

    if 'peak_price' not in trade_columns:
        logger.info("Migrating database: Adding 'peak_price' column to 'trades' table.")
        cursor.execute("ALTER TABLE trades ADD COLUMN peak_price REAL")
        changes_made = True

    if 'mode' not in trade_columns:
        logger.info("Migrating database: Adding 'mode' and 'trade_size_usdt' columns to 'trades' table.")
        cursor.execute("ALTER TABLE trades ADD COLUMN mode TEXT DEFAULT 'LIVE'")
        cursor.execute("ALTER TABLE trades ADD COLUMN trade_size_usdt REAL")
        changes_made = True

    if 'quantity' not in trade_columns:
        logger.info("Migrating database: Adding 'quantity' column to 'trades' table.")
        cursor.execute("ALTER TABLE trades ADD COLUMN quantity REAL")
        changes_made = True

    if 'close_reason' not in trade_columns:
        logger.info("Migrating database: Adding 'close_reason' column to 'trades' table.")
        cursor.execute("ALTER TABLE trades ADD COLUMN close_reason TEXT")
        changes_made = True

    if 'win_loss' not in trade_columns:
        logger.info("Migrating database: Adding 'win_loss' and 'pnl_percentage' columns to 'trades' table.")
        cursor.execute("ALTER TABLE trades ADD COLUMN win_loss TEXT")
        cursor.execute("ALTER TABLE trades ADD COLUMN pnl_percentage REAL")
        changes_made = True

    if 'dsl_mode' not in trade_columns:
        logger.info("Migrating database: Adding 'dsl_mode' and 'current_dsl_stage' columns to 'trades' table.")
        cursor.execute("ALTER TABLE trades ADD COLUMN dsl_mode TEXT")
        cursor.execute("ALTER TABLE trades ADD COLUMN current_dsl_stage INTEGER DEFAULT 0")
        changes_made = True

    # --- Schema Migration for users table ---
    cursor.execute("PRAGMA table_info(users)")
    user_columns = [info[1] for info in cursor.fetchall()]

    if 'trading_mode' not in user_columns:
        logger.info("Migrating database: Adding 'trading_mode' and 'paper_balance' columns to 'users' table.")
        cursor.execute("ALTER TABLE users ADD COLUMN trading_mode TEXT DEFAULT 'LIVE'")
        cursor.execute("ALTER TABLE users ADD COLUMN paper_balance REAL DEFAULT 10000.0")
        changes_made = True

    if 'custom_stop_loss' not in user_columns:
        logger.info("Migrating database: Adding custom setting columns to 'users' table.")
        cursor.execute("ALTER TABLE users ADD COLUMN custom_rsi_buy REAL")
        cursor.execute("ALTER TABLE users ADD COLUMN custom_rsi_sell REAL")
        cursor.execute("ALTER TABLE users ADD COLUMN custom_stop_loss REAL")
        cursor.execute("ALTER TABLE users ADD COLUMN custom_trailing_activation REAL")
        cursor.execute("ALTER TABLE users ADD COLUMN custom_trailing_drop REAL")
        changes_made = True

    if changes_made:
        conn.commit()
        logger.info("Database schema migration complete.")

def get_or_create_user(user_id: int):
    """Gets a user from the DB or creates a new one with default settings."""
    conn = get_db_connection()
    user = conn.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)).fetchone()
    if not user:
        conn.execute("INSERT INTO users (user_id) VALUES (?)", (user_id,))
        conn.commit()
        user = conn.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)).fetchone()
        logger.info(f"Created new user with ID: {user_id}")
    return user

def log_trade(user_id: int, coin_symbol: str, buy_price: float, stop_loss: float, take_profit: float, mode: str = 'LIVE', trade_size_usdt: float | None = None, quantity: float | None = None, rsi_at_buy: float | None = None, highest_price: float | None = None):
    """Logs a new open trade for a user in the database."""
    # Ensure user exists before logging a trade
    get_or_create_user(user_id)
    conn = get_db_connection()
    conn.execute(
        "INSERT INTO trades (user_id, coin_symbol, buy_price, status, stop_loss_price, take_profit_price, mode, trade_size_usdt, quantity, rsi_at_buy, highest_price) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (user_id, coin_symbol, buy_price, 'open', stop_loss, take_profit, mode, trade_size_usdt, quantity, rsi_at_buy, highest_price)
    )
    conn.commit()

# A mapping from user-friendly names to database columns for custom settings
SETTING_TO_COLUMN_MAP = {
    'rsi_buy': 'custom_rsi_buy',
    'rsi_sell': 'custom_rsi_sell',
    'stop_loss': 'custom_stop_loss',
    'trailing_activation': 'custom_trailing_activation',
    'trailing_drop': 'custom_trailing_drop',
}

def update_user_setting(user_id: int, setting_key: str, value: float | None):
    """Updates a single custom setting for a user. A value of None resets to default."""
    if setting_key not in SETTING_TO_COLUMN_MAP:
        logger.error(f"Attempted to update invalid setting: {setting_key}")
        return False
    
    column_name = SETTING_TO_COLUMN_MAP[setting_key]
    conn = get_db_connection()
    # Using f-string for column name is safe here because we control the input via the map
    query = f"UPDATE users SET {column_name} = ? WHERE user_id = ?"
    conn.execute(query, (value, user_id))
    conn.commit()
    logger.info(f"Updated setting '{setting_key}' for user {user_id} to {value}")
    return True

def get_user_effective_settings(user_id: int) -> dict:
    """
    Returns the effective settings for a user by layering their custom
    settings over their subscription tier's defaults.
    """
    tier = get_user_tier(user_id)
    settings = config.get_active_settings(tier).copy() # Start with a copy of tier defaults
    conn = get_db_connection()
    user_data = conn.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)).fetchone()
    if not user_data:
        # Always return defaults if user not found
        return settings
    user_keys = user_data.keys()
    # Override defaults with custom settings if they exist (are not NULL)
    if 'custom_rsi_buy' in user_keys and user_data['custom_rsi_buy'] is not None:
        settings['RSI_BUY_THRESHOLD'] = user_data['custom_rsi_buy']
    if 'custom_rsi_sell' in user_keys and user_data['custom_rsi_sell'] is not None:
        settings['RSI_SELL_THRESHOLD'] = user_data['custom_rsi_sell']
    if 'custom_stop_loss' in user_keys and user_data['custom_stop_loss'] is not None:
        settings['STOP_LOSS_PERCENTAGE'] = user_data['custom_stop_loss']
    if 'custom_trailing_activation' in user_keys and user_data['custom_trailing_activation'] is not None:
        settings['TRAILING_PROFIT_ACTIVATION_PERCENT'] = user_data['custom_trailing_activation']
    if 'custom_trailing_drop' in user_keys and user_data['custom_trailing_drop'] is not None:
        settings['TRAILING_STOP_DROP_PERCENT'] = user_data['custom_trailing_drop']
    return settings

def get_open_trades(user_id: int):
    """Retrieves all open trades for a specific user."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, user_id, coin_symbol, buy_price, buy_timestamp, stop_loss_price, take_profit_price FROM trades WHERE user_id = ? AND status = 'open'", (user_id,)
    )
    return cursor.fetchall()

def get_all_open_trades():
    """Retrieves all open trades for all users, for the market monitor."""
    conn = get_db_connection()
    return conn.execute("SELECT id, user_id, coin_symbol, buy_price, stop_loss_price, take_profit_price, peak_price, mode, trade_size_usdt, quantity, buy_timestamp FROM trades WHERE status = 'open'").fetchall()

def get_trade_by_id(trade_id: int, user_id: int):
    """
    Retrieves a specific open trade by its ID for a specific user.
    Used by the /close command to ensure a user can only close their own trade.
    """
    conn = get_db_connection()
    return conn.execute("SELECT * FROM trades WHERE id = ? AND user_id = ?", (trade_id, user_id)).fetchone()

def get_open_trade_by_symbol(user_id: int, symbol: str):
    """Retrieves an open trade by its symbol for a specific user."""
    conn = get_db_connection()
    return conn.execute("SELECT * FROM trades WHERE user_id = ? AND coin_symbol = ? AND status = 'open'", (user_id, symbol)).fetchone()

def close_trade(trade_id: int, user_id: int, sell_price: float, close_reason: str | None = None, win_loss: str | None = None, pnl_percentage: float | None = None, rsi_at_exit: float | None = None, held_duration_hours: float | None = None):
    """Updates a trade to 'closed' and records the sell price, reason, PnL, and win/loss status.

    Returns True on success, False on failure (e.g., trade not found).
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    # First, get the trade details to calculate PnL
    trade = conn.execute("SELECT buy_price, coin_symbol FROM trades WHERE id = ? AND user_id = ? AND status = 'open'", (trade_id, user_id)).fetchone()
    if not trade:
        return False

    buy_price = trade['buy_price']
    coin_symbol = trade['coin_symbol']

    if pnl_percentage is None:
        pnl_percentage = ((sell_price - buy_price) / buy_price) * 100
    if win_loss is None:
        win_loss = 'win' if pnl_percentage > 0 else ('loss' if pnl_percentage < 0 else 'break_even')

    # Update the trades table
    cursor.execute(
        "UPDATE trades SET status = 'closed', sell_price = ?, close_reason = ?, win_loss = ?, pnl_percentage = ? WHERE id = ? AND user_id = ? AND status = 'open'",
        (sell_price, close_reason, win_loss, pnl_percentage, trade_id, user_id)
    )

    # Update coin_performance table
    cursor.execute(
        "INSERT INTO coin_performance (coin_symbol, wins, losses, total_pnl_percentage) VALUES (?, ?, ?, ?) ON CONFLICT(coin_symbol) DO UPDATE SET wins = wins + ?, losses = losses + ?, total_pnl_percentage = total_pnl_percentage + ?",
        (coin_symbol, 1 if win_loss == 'win' else 0, 1 if win_loss == 'loss' else 0, pnl_percentage,
         1 if win_loss == 'win' else 0, 1 if win_loss == 'loss' else 0, pnl_percentage)
    )

    conn.commit()
    return cursor.rowcount > 0

def update_trade_stop_loss(trade_id: int, new_stop_loss_price: float, new_dsl_stage: int):
    """Updates the stop loss price and DSL stage for a given trade."""
    conn = get_db_connection()
    conn.execute(
        "UPDATE trades SET stop_loss_price = ?, current_dsl_stage = ? WHERE id = ?",
        (new_stop_loss_price, new_dsl_stage, trade_id)
    )
    conn.commit()

def activate_trailing_stop(trade_id: int, peak_price: float):
    """Activates the trailing stop for a trade by setting its initial peak price."""
    conn = get_db_connection()
    conn.execute(
        "UPDATE trades SET peak_price = ? WHERE id = ?",
        (peak_price, trade_id)
    )
    conn.commit()

def update_trade_field(trade_id, field_name, value):
    """
    Updates a specific field for a given trade in the database.
    """
    try:
        conn = get_db_connection()
        # Using a parameterized query to prevent SQL injection
        # Note the use of f-string for the field_name, this is safe ONLY if you control the field_name string
        conn.execute(f"UPDATE trades SET {field_name} = ? WHERE id = ?", (value, trade_id))
        conn.commit()
    except sqlite3.Error as e:
        logger.error(f"Database error updating field {field_name} for trade {trade_id}: {e}")

def get_closed_trades(user_id: int):
    """Retrieves all closed trades for a specific user."""
    conn = get_db_connection()
    return conn.execute(
        "SELECT coin_symbol, buy_price, sell_price FROM trades WHERE user_id = ? AND status = 'closed' AND sell_price IS NOT NULL",
        (user_id,)
    ).fetchall()

def get_top_closed_trades(user_id: int, limit: int = 3):
    """Retrieves the top N most profitable closed trades for a specific user."""
    conn = get_db_connection()
    # Calculate P/L percentage directly in the query to sort by it, and only include profitable trades
    query = """
        SELECT
            coin_symbol,
            buy_price,
            sell_price,
            ((sell_price - buy_price) / buy_price) * 100 AS pnl_percent
        FROM trades
        WHERE user_id = ? AND status = 'closed' AND sell_price IS NOT NULL AND ((sell_price - buy_price) / buy_price) > 0
        ORDER BY pnl_percent DESC
        LIMIT ?
    """
    return conn.execute(query, (user_id, limit)).fetchall()

def get_global_top_trades(limit: int = 3):
    """Retrieves the top N most profitable closed trades across all users."""
    conn = get_db_connection()
    # We need user_id to be able to fetch the user's name later
    query = """
        SELECT
            user_id,
            coin_symbol,
            buy_price,
            sell_price,
            ((sell_price - buy_price) / buy_price) * 100 AS pnl_percent
        FROM trades
        WHERE status = 'closed' AND sell_price IS NOT NULL AND ((sell_price - buy_price) / buy_price) > 0
        ORDER BY pnl_percent DESC
        LIMIT ?
    """
    return conn.execute(query, (limit,)).fetchall()

def get_unique_open_trade_symbols():
    """Retrieves a list of unique symbols for all open trades across all users."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT DISTINCT coin_symbol FROM trades WHERE status = 'open'"
    )
    # fetchall() returns a list of tuples, e.g., [('BTCUSDT',), ('ETHUSDT',)]
    # We convert it to a simple list: ['BTCUSDT', 'ETHUSDT']
    return [row['coin_symbol'] for row in cursor.fetchall()]

def is_trade_open(user_id: int, coin_symbol: str):
    """Checks if a user already has an open trade for a specific symbol."""
    conn = get_db_connection()
    trade = conn.execute(
        "SELECT id FROM trades WHERE user_id = ? AND coin_symbol = ? AND status = 'open'",
        (user_id, coin_symbol)
    ).fetchone()
    return trade is not None

def is_on_watchlist(user_id: int, coin_symbol: str):
    """Checks if a user is already watching a specific symbol."""
    conn = get_db_connection()
    item = conn.execute(
        "SELECT id FROM watchlist WHERE user_id = ? AND coin_symbol = ?",
        (user_id, coin_symbol)
    ).fetchone()
    return item is not None

# --- Watchlist Functions ---

def add_to_watchlist(user_id: int, coin_symbol: str):
    """Adds a coin to the user's watchlist. Ignores if already present."""
    conn = get_db_connection()
    # Use INSERT OR IGNORE to prevent errors on duplicate entries
    conn.execute(
        "INSERT OR IGNORE INTO watchlist (user_id, coin_symbol) VALUES (?, ?)",
        (user_id, coin_symbol)
    )
    conn.commit()

def set_user_trading_mode(user_id: int, mode: str):
    """Sets the user's trading mode ('LIVE' or 'PAPER')."""
    conn = get_db_connection()
    conn.execute("UPDATE users SET trading_mode = ? WHERE user_id = ?", (mode.upper(), user_id))
    conn.commit()

def get_user_trading_mode_and_balance(user_id: int):
    """Gets the user's trading mode and paper balance."""
    user = get_or_create_user(user_id)
    return user['trading_mode'], user['paper_balance']

def update_paper_balance(user_id: int, amount_change: float):
    """Updates a user's paper balance by adding or subtracting an amount."""
    conn = get_db_connection()
    conn.execute("UPDATE users SET paper_balance = paper_balance + ? WHERE user_id = ?", (amount_change, user_id))
    conn.commit()

def reset_paper_account(user_id: int):
    """Resets a user's paper balance to the default and closes all paper trades."""
    conn = get_db_connection()
    # Reset balance
    conn.execute("UPDATE users SET paper_balance = ? WHERE user_id = ?", (config.PAPER_STARTING_BALANCE, user_id))
    # Close all open paper trades for that user
    conn.execute("UPDATE trades SET status = 'closed', sell_price = buy_price, close_reason = 'Reset' WHERE user_id = ? AND mode = 'PAPER' AND status = 'open'", (user_id,))
    conn.commit()

def get_all_watchlist_items():
    """Retrieves all items from the watchlist for all users."""
    conn = get_db_connection()
    items = conn.execute("SELECT id, user_id, coin_symbol, add_timestamp FROM watchlist").fetchall()
    return items

def remove_from_watchlist(item_id: int):
    """Removes an item from the watchlist by its ID."""
    conn = get_db_connection()
    conn.execute("DELETE FROM watchlist WHERE id = ?", (item_id,))
    conn.commit()

def get_watched_items_by_user(user_id: int):
    """Retrieves all watched symbols for a specific user."""
    conn = get_db_connection()
    items = conn.execute(
        "SELECT coin_symbol, add_timestamp FROM watchlist WHERE user_id = ?", (user_id,)
    ).fetchall()
    return items

# --- User API Key and Subscription Functions ---

def store_user_api_keys(user_id: int, api_key: str, secret_key: str):
    """Encrypts and stores a user's Binance API keys."""
    get_or_create_user(user_id) # Ensure user exists
    encrypted_api_key = encrypt_data(api_key)
    encrypted_secret_key = encrypt_data(secret_key)
    conn = get_db_connection()
    conn.execute(
        "UPDATE users SET api_key = ?, secret_key = ? WHERE user_id = ?",
        (encrypted_api_key, encrypted_secret_key, user_id)
    )
    conn.commit()

def get_user_api_keys(user_id: int) -> tuple[str | None, str | None]:
    """
    Retrieves and decrypts a user's Binance API keys.
    For the admin user, it returns the keys directly from the .env configuration.
    """
    # As the father of the bot, you get your keys directly from the sacred .env scroll.
    if user_id == config.ADMIN_USER_ID:
        return config.BINANCE_API_KEY, config.BINANCE_SECRET_KEY

    conn = get_db_connection()
    row = conn.execute("SELECT api_key, secret_key FROM users WHERE user_id = ?", (user_id,)).fetchone()

    if not row or not row['api_key'] or not row['secret_key']:
        return None, None

    api_key = decrypt_data(row['api_key'])
    secret_key = decrypt_data(row['secret_key'])
    return api_key, secret_key

def get_user_tier(user_id: int) -> str:
    """Retrieves a user's subscription tier."""
    # As the father of the bot, you are always granted Premium status.
    if user_id == config.ADMIN_USER_ID:
        return 'PREMIUM'

    user = get_or_create_user(user_id)
    # Future logic: check if subscription_expires is in the past and downgrade if so.
    return user['subscription_tier']

def update_user_tier(user_id: int, tier: str, expiration_date=None):
    """Updates a user's subscription tier and optional expiration date."""
    get_or_create_user(user_id) # Ensure user exists
    conn = get_db_connection()
    conn.execute(
        "UPDATE users SET subscription_tier = ?, subscription_expires = ? WHERE user_id = ?",
        (tier.upper(), expiration_date, user_id)
    )
    conn.commit()

def get_all_user_ids() -> list[int]:
    """Retrieves a list of all user IDs from the database."""
    conn = get_db_connection()
    user_ids = [row['user_id'] for row in conn.execute("SELECT user_id FROM users").fetchall()]
    return user_ids

def get_autotrade_status(user_id: int) -> bool:
    """Return True if autotrade is enabled for the user, else False. Uses users table."""
    conn = get_db_connection()
    row = conn.execute("SELECT autotrade_enabled FROM users WHERE user_id = ?", (user_id,)).fetchone()
    if row is not None and row['autotrade_enabled'] is not None:
        return bool(row['autotrade_enabled'])
    # Default: enabled for admin, disabled for others
    if user_id == getattr(config, 'ADMIN_USER_ID', None):
        return True
    return False

def set_autotrade_status(user_id: int, enabled: bool):
    """Set autotrade status for a user in the users table."""
    get_or_create_user(user_id)
    conn = get_db_connection()
    conn.execute("UPDATE users SET autotrade_enabled = ? WHERE user_id = ?", (int(enabled), user_id))
    conn.commit()

def get_premium_users() -> list[int]:
    """Retrieves a list of all premium user IDs from the database."""
    conn = get_db_connection()
    user_ids = [row['user_id'] for row in conn.execute("SELECT user_id FROM premium_users").fetchall()]
    return user_ids

def get_coin_performance(coin_symbol: str):
    """Retrieves performance data for a specific coin."""
    conn = get_db_connection()
    return conn.execute("SELECT * FROM coin_performance WHERE coin_symbol = ?", (coin_symbol,)).fetchone()

def get_all_coin_performance():
    """Retrieves performance data for all coins."""
    conn = get_db_connection()
    return conn.execute("SELECT * FROM coin_performance").fetchall()