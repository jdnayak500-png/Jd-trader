import ccxt
import os
from dotenv import load_dotenv

load_dotenv()

exchange = ccxt.bitget({
    'apiKey': os.getenv("API_KEY"),
    'secret': os.getenv("SECRET"),
    'password': os.getenv("PASSPHRASE"),
    'enableRateLimit': True,
})
