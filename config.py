import os
from dotenv import load_dotenv

load_dotenv()

LIVE_TRADING = os.getenv("LIVE_TRADING") == "true"
