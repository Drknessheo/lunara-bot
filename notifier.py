import json
import os
from datetime import datetime, timedelta, timezone
import logging
import requests
from dotenv import load_dotenv

# Load environment variables from .env file at the module level
dotenv_path = os.path.join(os.path.dirname(__file__), '.env')
load_dotenv(dotenv_path=dotenv_path)

BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
CREATOR_ID = os.getenv('TELEGRAM_CREATOR_ID')

def send_telegram_message(bot_token: str, chat_id: str, text: str):
    """Sends a message to a specific Telegram chat."""
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {
        'chat_id': chat_id,
        'text': text,
        'parse_mode': 'Markdown'
    }
    try:
        response = requests.post(url, json=payload)
        response.raise_for_status()  # Raises an HTTPError for bad responses (4xx or 5xx)
        logging.info("Successfully sent daily report to Telegram.")
    except requests.exceptions.RequestException as e:
        logging.error(f"Error sending Telegram message: {e}")

def generate_daily_summary():
    """Generates and sends the daily summary report."""
    if not BOT_TOKEN or not CREATOR_ID:
        logging.error("TELEGRAM_BOT_TOKEN or TELEGRAM_CREATOR_ID not found in .env file.")
        return

    # Load analytics data
    analytics_file = os.path.join(os.path.dirname(__file__), 'analytics.json')
    try:
        with open(analytics_file, 'r') as f:
            data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        send_telegram_message(BOT_TOKEN, CREATOR_ID, "Lunessa Report: Analytics file not found or is empty.")
        return

    yesterday_str = (datetime.now(timezone.utc) - timedelta(days=1)).strftime('%Y-%m-%d')
    yesterday_stats = data.get('daily_stats', {}).get(yesterday_str, {'interactions': 0, 'earnings': 0.0})

    message = (
        f"*Lunessa Shi'ra Gork - Daily Report*\n\n"
        f"📊 *Analytics for {yesterday_str}:*\n"
        f"  - Interactions: `{yesterday_stats['interactions']}`\n"
        f"  - Earnings: `${yesterday_stats['earnings']:.2f}`\n\n"
        f"👤 *Total Unique Users:* `{len(data.get('unique_visitors', []))}`\n\n"
        f"🔄 Nightly backup script was scheduled to run."
    )
    
    send_telegram_message(BOT_TOKEN, CREATOR_ID, message)

if __name__ == "__main__":
    generate_daily_summary()