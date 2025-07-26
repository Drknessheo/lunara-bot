import os
import logging
from cryptography.fernet import Fernet

logger = logging.getLogger(__name__)

# Load the encryption key from environment variables
ENCRYPTION_KEY = os.getenv("ENCRYPTION_KEY")
if not ENCRYPTION_KEY:
    raise ValueError("ENCRYPTION_KEY not found in environment variables. Please generate one and add it to your .env file.")

cipher_suite = Fernet(ENCRYPTION_KEY.encode())

def encrypt_data(data: str) -> bytes:
    """Encrypts a string."""
    if not data:
        return None
    return cipher_suite.encrypt(data.encode())

def decrypt_data(encrypted_data: bytes) -> str:
    """Decrypts a string."""
    if not encrypted_data:
        return None
    try:
        return cipher_suite.decrypt(encrypted_data).decode()
    except Exception as e:
        logger.error(f"Failed to decrypt data: {e}")
        return None
