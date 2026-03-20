import time
import logging
from data import get_ohlcv
from strategy import get_signal
from exchange import exchange
from config import LIVE_TRADING

logging.basicConfig(level=logging.INFO)

SYMBOL = "BTC/USDT"
TRADE_SIZE = 0.001

def place_trade(signal):
    if not LIVE_TRADING:
        logging.info(f"[PAPER TRADE] {signal}")
        return

    try:
        if signal == "BUY":
            exchange.create_market_buy_order(SYMBOL, TRADE_SIZE)
        elif signal == "SELL":
            exchange.create_market_sell_order(SYMBOL, TRADE_SIZE)

        logging.info(f"Executed {signal}")

    except Exception as e:
        logging.error(f"Trade error: {e}")

def run_bot():
    logging.info("Bot started")

    while True:
        try:
            df = get_ohlcv(SYMBOL)
            signal = get_signal(df)

            if signal:
                logging.info(f"Signal: {signal}")
                place_trade(signal)

            time.sleep(30)

        except Exception as e:
            logging.error(f"Main error: {e}")
            time.sleep(5)

if __name__ == "__main__":
    run_bot()
