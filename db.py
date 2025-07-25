import sqlite3
from config import DB_NAME

def get_db_connection():
    """Establishes a connection to the SQLite database."""
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn

def initialize_database():
    """Creates the trades table if it doesn't exist."""
    conn = get_db_connection()
    cursor = conn.cursor()
    # We add user_id to support multiple users
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            coin_symbol TEXT NOT NULL,
            buy_price REAL NOT NULL,
            buy_timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            status TEXT NOT NULL, -- e.g., 'open', 'closed'
            sell_price REAL,
            stop_loss_price REAL,
            take_profit_price REAL
        );
    ''')
    conn.commit()
    conn.close()
    print("Database initialized successfully.")

def log_trade(user_id: int, coin_symbol: str, buy_price: float, stop_loss: float, take_profit: float):
    """Logs a new open trade for a user in the database."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO trades (user_id, coin_symbol, buy_price, status, stop_loss_price, take_profit_price) VALUES (?, ?, ?, ?, ?, ?)",
        (user_id, coin_symbol, buy_price, 'open', stop_loss, take_profit)
    )
    conn.commit()
    conn.close()

def get_open_trades(user_id: int):
    """Retrieves all open trades for a specific user."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, coin_symbol, buy_price, buy_timestamp, stop_loss_price, take_profit_price FROM trades WHERE user_id = ? AND status = 'open'", (user_id,)
    )
    trades = cursor.fetchall()
    conn.close()
    return trades

def get_all_open_trades():
    """Retrieves all open trades for all users, for the market monitor."""
    conn = get_db_connection()
    # Fetch all columns needed by the monitor
    trades = conn.execute("SELECT id, user_id, coin_symbol, buy_price, stop_loss_price, take_profit_price FROM trades WHERE status = 'open'").fetchall()
    conn.close()
    return trades

def get_trade_by_id(trade_id: int, user_id: int):
    """
    Retrieves a specific open trade by its ID for a specific user.
    Used by the /close command to ensure a user can only close their own trade.
    """
    conn = get_db_connection()
    trade = conn.execute("SELECT id, coin_symbol FROM trades WHERE id = ? AND user_id = ? AND status = 'open'", (trade_id, user_id)).fetchone()
    conn.close()
    return trade

def close_trade(trade_id: int, user_id: int, sell_price: float):
    """Updates a trade to 'closed' and records the sell price.

    Returns True on success, False on failure (e.g., trade not found).
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    # We check user_id to ensure a user can only close their own trades
    cursor.execute(
        "UPDATE trades SET status = 'closed', sell_price = ? WHERE id = ? AND user_id = ? AND status = 'open'",
        (sell_price, trade_id, user_id)
    )
    conn.commit()
    # conn.total_changes will be > 0 if a row was updated
    changes = conn.total_changes
    conn.close()
    return changes > 0

def get_closed_trades(user_id: int):
    """Retrieves all closed trades for a specific user."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT buy_price, sell_price FROM trades WHERE user_id = ? AND status = 'closed' AND sell_price IS NOT NULL",
        (user_id,)
    )
    trades = cursor.fetchall()
    conn.close()
    return trades

def get_unique_open_trade_symbols():
    """Retrieves a list of unique symbols for all open trades across all users."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT DISTINCT coin_symbol FROM trades WHERE status = 'open'"
    )
    # fetchall() returns a list of tuples, e.g., [('BTCUSDT',), ('ETHUSDT',)]
    # We convert it to a simple list: ['BTCUSDT', 'ETHUSDT']
    symbols = [row['coin_symbol'] for row in cursor.fetchall()]
    conn.close()
    return symbols

def is_trade_open(user_id: int, coin_symbol: str):
    """Checks if a user already has an open trade for a specific symbol."""
    conn = get_db_connection()
    trade = conn.execute(
        "SELECT id FROM trades WHERE user_id = ? AND coin_symbol = ? AND status = 'open'",
        (user_id, coin_symbol)
    ).fetchone()
    conn.close()
    return trade is not None