import sqlite3
conn = sqlite3.connect('lunara_bot.db')
conn.execute('''
    CREATE TABLE IF NOT EXISTS premium_users (
        user_id INTEGER PRIMARY KEY
    );
''')
conn.execute('INSERT OR IGNORE INTO premium_users (user_id) VALUES (?)', (6284071528,))
conn.commit()
conn.close()
print('User 6284071528 added to premium_users table.')