import pytest
from trade import TradeError, get_rsi

def test_rsi_returns_float():
    # Should return float or None
    result = get_rsi("BTCUSDT")
    assert isinstance(result, (float, type(None)))

def test_trade_error():
    with pytest.raises(TradeError):
        raise TradeError("Test error")
