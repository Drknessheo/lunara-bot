# Database access functions for Lunara Bot
import sqlite3

def get_db_connection():
    conn = sqlite3.connect('lunara_bot.db')
    conn.row_factory = sqlite3.Row
    return conn

def initialize_database():
    """Creates the tables if they don't exist."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            coin_symbol TEXT NOT NULL,
            buy_price REAL NOT NULL,
            buy_timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            status TEXT NOT NULL,
            sell_price REAL,
            stop_loss_price REAL,
            take_profit_price REAL,
            peak_price REAL,
            mode TEXT DEFAULT 'LIVE',
            trade_size_usdt REAL,
            quantity REAL,
            close_reason TEXT,
            win_loss TEXT,
            pnl_percentage REAL,
            rsi_at_buy REAL
        );
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS coin_performance (
            coin_symbol TEXT PRIMARY KEY,
            wins INTEGER DEFAULT 0,
            losses INTEGER DEFAULT 0,
            total_pnl_percentage REAL DEFAULT 0.0
        );
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS watchlist (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            coin_symbol TEXT NOT NULL,
            add_timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, coin_symbol)
        );
    """)
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
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS premium_users (
            user_id INTEGER PRIMARY KEY
        );
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS autotrades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            symbol TEXT NOT NULL,
            buy_price REAL NOT NULL,
            sell_price REAL,
            status TEXT NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            closed_at DATETIME
        );
    """)
    conn.commit()

def migrate_schema():
    """
    Checks the database schema and applies any necessary migrations,
    such as adding new columns to existing tables.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    changes_made = False

    cursor.execute("PRAGMA table_info(trades)")
    trade_columns = [info[1] for info in cursor.fetchall()]

    if 'peak_price' not in trade_columns:
        cursor.execute("ALTER TABLE trades ADD COLUMN peak_price REAL")
        changes_made = True
    if 'mode' not in trade_columns:
        cursor.execute("ALTER TABLE trades ADD COLUMN mode TEXT DEFAULT 'LIVE'")
        cursor.execute("ALTER TABLE trades ADD COLUMN trade_size_usdt REAL")
        changes_made = True
    if 'quantity' not in trade_columns:
        cursor.execute("ALTER TABLE trades ADD COLUMN quantity REAL")
        changes_made = True
    if 'close_reason' not in trade_columns:
        cursor.execute("ALTER TABLE trades ADD COLUMN close_reason TEXT")
        changes_made = True
    if 'win_loss' not in trade_columns:
        cursor.execute("ALTER TABLE trades ADD COLUMN win_loss TEXT")
        cursor.execute("ALTER TABLE trades ADD COLUMN pnl_percentage REAL")
        changes_made = True
    if 'dsl_mode' not in trade_columns:
        cursor.execute("ALTER TABLE trades ADD COLUMN dsl_mode TEXT")
        cursor.execute("ALTER TABLE trades ADD COLUMN current_dsl_stage INTEGER DEFAULT 0")
        changes_made = True

    cursor.execute("PRAGMA table_info(users)")
    user_columns = [info[1] for info in cursor.fetchall()]

    if 'trading_mode' not in user_columns:
        cursor.execute("ALTER TABLE users ADD COLUMN trading_mode TEXT DEFAULT 'LIVE'")
        cursor.execute("ALTER TABLE users ADD COLUMN paper_balance REAL DEFAULT 10000.0")
        changes_made = True
    if 'custom_stop_loss' not in user_columns:
        cursor.execute("ALTER TABLE users ADD COLUMN custom_rsi_buy REAL")
        cursor.execute("ALTER TABLE users ADD COLUMN custom_rsi_sell REAL")
        cursor.execute("ALTER TABLE users ADD COLUMN custom_stop_loss REAL")
        cursor.execute("ALTER TABLE users ADD COLUMN custom_trailing_activation REAL")
        cursor.execute("ALTER TABLE users ADD COLUMN custom_trailing_drop REAL")
        changes_made = True

    if changes_made:
        conn.commit()

# --- Lunara Bot: Modular DB Access ---
def get_or_create_user(user_id: int):
    """Gets a user from the DB or creates a new one with default settings."""
    conn = get_db_connection()
    user = conn.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)).fetchone()
    if not user:
        conn.execute("INSERT INTO users (user_id) VALUES (?)", (user_id,))
        conn.commit()
        user = conn.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)).fetchone()
    return user

def get_autotrade_status(user_id: int):
    conn = get_db_connection()
    row = conn.execute("SELECT autotrade_enabled FROM users WHERE user_id = ?", (user_id,)).fetchone()
    return bool(row['autotrade_enabled']) if row and row['autotrade_enabled'] is not None else False

def set_autotrade_status(user_id: int, enabled: bool):
    """Set autotrade status for a user in the users table."""
    get_or_create_user(user_id)
    conn = get_db_connection()
    conn.execute("UPDATE users SET autotrade_enabled = ? WHERE user_id = ?", (int(enabled), user_id))
    conn.commit()

def get_open_trades(user_id: int):
    """Retrieves all open trades for a specific user."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, user_id, coin_symbol, buy_price, buy_timestamp, stop_loss_price, take_profit_price FROM trades WHERE user_id = ? AND status = 'open'", (user_id,)
    )
    return cursor.fetchall()

def get_user_trading_mode_and_balance(user_id: int):
    """Gets the user's trading mode and paper balance."""
    user = get_or_create_user(user_id)
    return user['trading_mode'], user['paper_balance']


def get_watched_items_by_user(user_id: int):
    """Retrieves all watched symbols for a specific user."""
    conn = get_db_connection()
    items = conn.execute(
        "SELECT coin_symbol, add_timestamp FROM watchlist WHERE user_id = ?", (user_id,)
    ).fetchall()
    return items

def get_user_api_keys(user_id: int):
    """
    Retrieves and decrypts a user's Binance API keys.
    """
    from security import decrypt_data
    conn = get_db_connection()
    row = conn.execute("SELECT api_key, secret_key FROM users WHERE user_id = ?", (user_id,)).fetchone()
    if not row or not row['api_key'] or not row['secret_key']:
        return None, None
    api_key = decrypt_data(row['api_key'])
    secret_key = decrypt_data(row['secret_key'])
    return api_key, secret_key

def get_user_tier(user_id: int) -> str:
    """
    Retrieves a user's subscription tier.
    Treats the admin/creator as 'PREMIUM' for all commands.
    """
    import config
    if user_id == getattr(config, 'ADMIN_USER_ID', None):
        return 'PREMIUM'
    user = get_or_create_user(user_id)
    return user['subscription_tier']

def get_user_effective_settings(user_id: int) -> dict:
    """
    Returns the effective settings for a user by layering their custom
    settings over their subscription tier's defaults.
    """
    import config
    tier = get_user_tier(user_id)
    settings = config.get_active_settings(tier).copy()  # Start with a copy of tier defaults
    conn = get_db_connection()
    user_data = conn.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)).fetchone()
    if not user_data:
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

def is_trade_open(user_id: int, coin_symbol: str):
    """Checks if a user already has an open trade for a specific symbol."""
    conn = get_db_connection()
    trade = conn.execute(
        "SELECT id FROM trades WHERE user_id = ? AND coin_symbol = ? AND status = 'open'",
        (user_id, coin_symbol)
    ).fetchone()
    return trade is not None


def get_closed_trades(user_id: int):
    """Retrieves all closed trades for a specific user."""
    conn = get_db_connection()
    return conn.execute(
        "SELECT coin_symbol, buy_price, sell_price FROM trades WHERE user_id = ? AND status = 'closed' AND sell_price IS NOT NULL",
        (user_id,)
    ).fetchall()


def get_global_top_trades(limit: int = 3):
    """Retrieves the top N most profitable closed trades across all users."""
    conn = get_db_connection()
    query = '''
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
    '''
    return conn.execute(query, (limit,)).fetchall()

def is_on_watchlist(user_id: int, coin_symbol: str):
    """Checks if a user is already watching a specific symbol."""
    conn = get_db_connection()
    item = conn.execute(
        "SELECT id FROM watchlist WHERE user_id = ? AND coin_symbol = ?",
        (user_id, coin_symbol)
    ).fetchone()
    return item is not None
