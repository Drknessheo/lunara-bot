
import sqlite3
from security import encrypt_data, decrypt_data

def get_db_connection():
    conn = sqlite3.connect('lunara_bot.db')
    conn.row_factory = sqlite3.Row
    return conn

def initialize_autotrade_database():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS autotrades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            coin_symbol TEXT NOT NULL,
            buy_price REAL NOT NULL,
            quantity REAL NOT NULL,
            status TEXT NOT NULL,
            gemini_analysis BLOB,
            buy_timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            sell_timestamp DATETIME
        );
    """)
    conn.commit()

def save_autotrade(user_id, coin_symbol, buy_price, quantity, gemini_analysis):
    conn = get_db_connection()
    encrypted_analysis = encrypt_data(gemini_analysis)
    conn.execute("""
        INSERT INTO autotrades (user_id, coin_symbol, buy_price, quantity, status, gemini_analysis)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (user_id, coin_symbol, buy_price, quantity, 'open', encrypted_analysis))
    conn.commit()

def get_open_autotrades():
    conn = get_db_connection()
    trades = conn.execute("SELECT * FROM autotrades WHERE status = 'open'").fetchall()
    return trades

def close_autotrade(trade_id, sell_price):
    conn = get_db_connection()
    conn.execute("UPDATE autotrades SET status = 'closed', sell_price = ?, sell_timestamp = CURRENT_TIMESTAMP WHERE id = ?", (sell_price, trade_id))
    conn.commit()
