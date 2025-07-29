# trading_module.py

from enum import Enum

class TradeAction(Enum):
    """Defines possible trading actions."""
    HOLD = "HOLD"
    CONSERVATIVE_BUY = "CONSERVATIVE_BUY"
    AGGRESSIVE_BUY = "AGGRESSIVE_BUY"
    CONSERVATIVE_SELL = "CONSERVATIVE_SELL"
    AGGRESSIVE_SELL = "AGGRESSIVE_SELL"

def get_trade_suggestion(resonance_level: float) -> TradeAction:
    """
    Generates a trading suggestion based on the resonance level.
    This is a simplified example. A real implementation would incorporate
    this resonance level into a more complex trading algorithm.
    """
    if resonance_level < 0.8:
        return TradeAction.CONSERVATIVE_SELL
    elif resonance_level < 1.2:
        return TradeAction.HOLD
    elif resonance_level < 1.8:
        return TradeAction.CONSERVATIVE_BUY
    else:
        return TradeAction.AGGRESSIVE_BUY