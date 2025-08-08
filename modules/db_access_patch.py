from .db_access import get_db_connection

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
