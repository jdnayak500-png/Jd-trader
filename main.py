import time
import logging
from data import get_ohlcv
from strategy import get_signal
from exchange import exchange
from config import LIVE_TRADING

logging.basicConfig(level=logging.INFO)

SYMBOL = "BTC/USDT"

def place_trade(signal, price):
    if not LIVE_TRADING:
        logging.info(f"[PAPER TRADE] {signal} @ {price}")
        return None

    try:
        if signal == "BUY":
            exchange.create_order(
                SYMBOL,
                "market",
                "buy",
                None,
                None,
                {"cost": 5}
            )

            entry_price = price
            take_profit = entry_price * 1.02
            stop_loss = entry_price * 0.99

            logging.info(f"BUY at {entry_price}")
            logging.info(f"TP: {take_profit}, SL: {stop_loss}")

            return entry_price, take_profit, stop_loss

        elif signal == "SELL":
    balance = exchange.fetch_balance()
    btc_amount = balance['BTC']['free']

    if btc_amount and btc_amount > 0.00001:
        exchange.create_market_sell_order(SYMBOL, btc_amount)
        logging.info(f"Sold {btc_amount} BTC")
    else:
        logging.info("No BTC to sell")
    except Exception as e:
        logging.error(f"Trade error: {e}")
        return None


def run_bot():
    logging.info("Bot started")

    in_trade = False
    entry_price = 0
    take_profit = 0
    stop_loss = 0

    while True:
        try:
            df = get_ohlcv(SYMBOL)
            price = df['close'].iloc[-1]

            if not in_trade:
                signal = get_signal(df)

                if signal == "BUY":
                    result = place_trade(signal, price)

                    if result:
                        entry_price, take_profit, stop_loss = result
                        in_trade = True

            else:
                if price >= take_profit:
                    exchange.create_market_sell_order(SYMBOL, 0.0005)
                    logging.info("Take Profit HIT")
                    in_trade = False

                elif price <= stop_loss:
                    exchange.create_market_sell_order(SYMBOL, 0.0005)
                    logging.info("Stop Loss HIT")
                    in_trade = False

            time.sleep(20)

        except Exception as e:
            logging.error(f"Error: {e}")
            time.sleep(5)


if __name__ == "__main__":
    run_bot()
