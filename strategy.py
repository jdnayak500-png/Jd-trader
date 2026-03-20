def get_signal(df):
    close = df['close']

    ma_short = close.rolling(5).mean().iloc[-1]
    ma_long = close.rolling(10).mean().iloc[-1]

    if ma_short > ma_long:
        return "BUY"
    elif ma_short < ma_long:
        return "SELL"

    return None
