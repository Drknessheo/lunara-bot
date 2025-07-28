import json
import os
from datetime import datetime, timezone
import logging
from filelock import FileLock, Timeout

logger = logging.getLogger(__name__)

DATA_FILE = os.path.join(os.path.dirname(__file__), 'analytics.json')
LOCK_FILE = DATA_FILE + ".lock"

def _load_data():
    """Loads analytics data from the JSON file."""
    if not os.path.exists(DATA_FILE):
        return {"unique_visitors": [], "daily_stats": {}}
    try:
        with open(DATA_FILE, 'r', encoding='utf-8') as f:
            # Return empty dict if file is empty to avoid JSONDecodeError
            content = f.read()
            if not content:
                return {"unique_visitors": [], "daily_stats": {}}
            return json.loads(content)
    except (json.JSONDecodeError, IOError) as e:
        logger.error(f"Error loading analytics data: {e}. Returning empty structure.")
        return {"unique_visitors": [], "daily_stats": {}}

def _save_data(data):
    """Saves analytics data to the JSON file."""
    try:
        with open(DATA_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2)
    except IOError as e:
        logger.error(f"Error saving analytics data: {e}")

def _get_or_initialize_today_stats(data: dict) -> dict:
    """
    Gets today's stats from the data object, initializing if not present.
    """
    today_str = datetime.now(timezone.utc).strftime('%Y-%m-%d')
    if today_str not in data['daily_stats']:
        data['daily_stats'][today_str] = {'interactions': 0, 'earnings': 0.0}
    return data['daily_stats'][today_str]

def log_interaction(user_id: int):
    """
    Logs a user interaction. Tracks unique users and daily interaction counts.
    This operation is thread-safe using a file lock.
    """
    lock = FileLock(LOCK_FILE, timeout=5)
    try:
        with lock:
            data = _load_data()

            # Use a set for efficient checking of unique visitors
            unique_visitors = set(data.get('unique_visitors', []))
            if user_id not in unique_visitors:
                unique_visitors.add(user_id)
                data['unique_visitors'] = sorted(list(unique_visitors)) # Save as sorted list

            # Get or create today's stats and increment
            today_stats = _get_or_initialize_today_stats(data)
            today_stats['interactions'] += 1

            _save_data(data)
            logger.info(f"Logged interaction for user {user_id}")
    except Timeout:
        logger.warning("Could not acquire lock to log analytics interaction. Skipping.")
    except Exception as e:
        logger.error(f"An unexpected error occurred in log_interaction: {e}")

def log_earning(amount: float):
    """
    Logs an earning event (e.g., a new subscription).
    This operation is thread-safe using a file lock.
    """
    if not isinstance(amount, (int, float)) or amount <= 0:
        return

    lock = FileLock(LOCK_FILE, timeout=5)
    try:
        with lock:
            data = _load_data()

            # Get or create today's stats and increment
            today_stats = _get_or_initialize_today_stats(data)
            today_stats['earnings'] += amount

            _save_data(data)
            logger.info(f"Logged earning of ${amount:.2f}")
    except Timeout:
        logger.warning("Could not acquire lock to log analytics earning. Skipping.")
    except Exception as e:
        logger.error(f"An unexpected error occurred in log_earning: {e}")