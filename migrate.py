def run_migrations():
    conn = sqlite3.connect("lunara_bot.db")
import sqlite3

def add_highest_price_column():
    try:
        conn = sqlite3.connect('trades.db')
        cursor = conn.cursor()
        # Add the new column to the existing table
        cursor.execute("ALTER TABLE trades ADD COLUMN highest_price REAL DEFAULT 0.0")
        conn.commit()
        conn.close()
        print("Successfully added 'highest_price' column to the 'trades' table.")
    except sqlite3.OperationalError as e:
        if "duplicate column name" in str(e):
            print("'highest_price' column already exists.")
        else:
            print(f"An error occurred: {e}")

if __name__ == '__main__':
    add_highest_price_column()
