import json
import logging
from datetime import datetime

logger = logging.getLogger(__name__)
MEMORY_FILE = "memory.json"

def load_memory():
    """Loads the bot's memory from a JSON file."""
    try:
        with open(MEMORY_FILE, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        return {}
    except json.JSONDecodeError:
        logger.error("Could not decode memory.json. Starting fresh.")
        return {}

def save_memory(data):
    """Saves the bot's memory to a JSON file."""
    try:
        with open(MEMORY_FILE, 'w') as f:
            json.dump(data, f, indent=4)
    except Exception as e:
        logger.error(f"Could not save memory to {MEMORY_FILE}: {e}")

def record_trade(symbol, pnl_percent, win_loss, rsi_at_sell, hold_duration_hours):
    """
    Records the result of a trade to learn from it.
    """
    memory = load_memory()
    if symbol not in memory:
        memory[symbol] = {
            "trades": 0,
            "wins": 0,
            "losses": 0,
            "total_pnl_percent": 0,
            "avg_pnl_percent": 0,
            "win_rate": 0,
            "history": []
        }

    # Update stats
    stats = memory[symbol]
    stats["trades"] += 1
    stats["total_pnl_percent"] += pnl_percent
    if win_loss == 'win':
        stats["wins"] += 1
    else:
        stats["losses"] += 1

    stats["avg_pnl_percent"] = stats["total_pnl_percent"] / stats["trades"]
    stats["win_rate"] = (stats["wins"] / stats["trades"]) * 100

    # Add to history
    stats["history"].append({
        "timestamp": datetime.now().isoformat(),
        "pnl_percent": pnl_percent,
        "win_loss": win_loss,
        "rsi_at_sell": rsi_at_sell,
        "hold_duration_hours": hold_duration_hours
    })

    # Keep history to a reasonable size
    stats["history"] = stats["history"][-20:]

    save_memory(memory)
    logger.info(f"Recorded trade for {symbol}: P/L {pnl_percent:.2f}%, Win/Loss: {win_loss}")

def get_insights(symbol=None):
    """
    Retrieves learning insights for a specific symbol or all symbols.
    """
    memory = load_memory()
    if symbol:
        return memory.get(symbol)
    return memory