import pytest
from modules import db_access

def test_db_connection():
    conn = db_access.get_db_connection()
    assert conn is not None
    assert hasattr(conn, 'execute')
