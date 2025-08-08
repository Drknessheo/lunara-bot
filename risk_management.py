import datetime

def get_trade_size(account_balance, min_trade=5.0, risk_pct=0.05):
    size = max(account_balance * risk_pct, min_trade)
    return min(size, account_balance)

# --- Market Crash/Big Buyer Shield ---
def is_market_crash_or_big_buyer(prices: dict) -> bool:
    """Detects sudden market crash or big buyer activity."""
    try:
        btc_prices = [prices.get('BTCUSDT')] if 'BTCUSDT' in prices else []
        if not btc_prices:
            return False
        btc_now = prices['BTCUSDT']
        btc_prev = prices.get('BTCUSDT_15min_ago', btc_now)
        if btc_prev and btc_now < btc_prev * 0.95:
            return True
        if btc_prev and btc_now > btc_prev * 1.05:
            return True
    except Exception:
        return False
    return False

def get_atr_stop(entry_price, atr, multiplier=1.5):
    return entry_price - multiplier * atr

def update_daily_pl(trade_result, db):
    today = datetime.date.today().isoformat()
    db.update_daily_pl(today, trade_result)

def should_pause_trading(db, account_balance, max_drawdown_pct=0.10):
    today = datetime.date.today().isoformat()
    daily_pl = db.get_daily_pl(today)
    return daily_pl < -account_balance * max_drawdown_pct
