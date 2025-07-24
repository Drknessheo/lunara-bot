import sqlite3
from .config import DB_NAME

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
            sell_price REAL
        );
    ''')
    conn.commit()
    conn.close()
    print("Database initialized successfully.")

def log_trade(user_id: int, coin_symbol: str, buy_price: float):
    """Logs a new open trade for a user in the database."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO trades (user_id, coin_symbol, buy_price, status) VALUES (?, ?, ?, ?)",
        (user_id, coin_symbol, buy_price, 'open')
    )
    conn.commit()
    conn.close()

def get_open_trades(user_id: int):
    """Retrieves all open trades for a specific user."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, coin_symbol, buy_price, buy_timestamp FROM trades WHERE user_id = ? AND status = 'open'", (user_id,)
    )
    trades = cursor.fetchall()
    conn.close()
    return trades