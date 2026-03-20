from exchange import exchange
import pandas as pd

def get_ohlcv(symbol="BTC/USDT", timeframe="5m"):
    bars = exchange.fetch_ohlcv(symbol, timeframe, limit=50)
    df = pd.DataFrame(bars, columns=['time','open','high','low','close','volume'])
    return df
