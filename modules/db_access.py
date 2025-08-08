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

def get_autotrade_status(user_id: int) -> bool:
    """Return True if autotrade is enabled for the user, else False. Uses users table."""
    conn = get_db_connection()
    row = conn.execute("SELECT autotrade_enabled FROM users WHERE user_id = ?", (user_id,)).fetchone()
    if row is not None and row['autotrade_enabled'] is not None:
        return bool(row['autotrade_enabled'])
    return False
