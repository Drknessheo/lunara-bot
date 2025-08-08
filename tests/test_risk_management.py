from risk_management import is_market_crash_or_big_buyer

def test_market_crash_shield():
    prices = {'BTCUSDT': 9000, 'BTCUSDT_15min_ago': 10000}
    assert is_market_crash_or_big_buyer(prices) is True
    prices = {'BTCUSDT': 10500, 'BTCUSDT_15min_ago': 10000}
    assert is_market_crash_or_big_buyer(prices) is True
    prices = {'BTCUSDT': 10000, 'BTCUSDT_15min_ago': 10000}
    assert is_market_crash_or_big_buyer(prices) is False
