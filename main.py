import os
import sys
import time
import json
import random
import base64
import asyncio
import hashlib
from dataclasses import dataclass, field, asdict
from typing import Optional, Dict, List
from enum import Enum

import subprocess

def install_pkg(pkg):
subprocess.check_call([sys.executable, “-m”, “pip”, “install”, pkg, “-q”])

try:
import numpy as np
except ImportError:
install_pkg(“numpy”)
import numpy as np

try:
import fastapi
except ImportError:
install_pkg(“fastapi”)

try:
import uvicorn
except ImportError:
install_pkg(“uvicorn[standard]”)

try:
import aiohttp
except ImportError:
install_pkg(“aiohttp”)

try:
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding as apad
except ImportError:
install_pkg(“cryptography”)
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding as apad

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse

# CONFIG

API_KEY = os.getenv(“BITGET_API_KEY”, “”)
PASSPHRASE = os.getenv(“BITGET_PASSPHRASE”, “”)
PRIVATE_KEY = os.getenv(“BITGET_PRIVATE_KEY”, “”).replace(”\n”, “\n”)
CAPITAL = float(os.getenv(“INITIAL_CAPITAL”, “50”))
SYMBOLS = [“BTCUSDT”, “ETHUSDT”, “SOLUSDT”]
CYCLE_SECS = 20
DEMO_MODE = not bool(API_KEY)

# LAYER 1 - MARKET ANALYSIS

class Regime(Enum):
TRENDING_BULL = “TRENDING_BULL”
TRENDING_BEAR = “TRENDING_BEAR”
RANGING = “RANGING”
HIGH_VOLATILITY = “HIGH_VOLATILITY”

@dataclass
class MarketState:
regime: Regime
adx: float
atr: float
atr_pct: float
vol_surge: float
sentiment: str

def calc_ema(prices, period):
if len(prices) < period:
return float(prices[-1])
k = 2.0 / (period + 1)
v = prices[0]
for p in prices[1:]:
v = p * k + v * (1 - k)
return v

def calc_ema_arr(prices, period):
k = 2.0 / (period + 1)
out = [prices[0]]
for p in prices[1:]:
out.append(p * k + out[-1] * (1 - k))
return out

def calc_rsi(closes, period=14):
if len(closes) < period + 1:
return 50.0
d = np.diff(closes[-(period + 1):])
g = np.where(d > 0, d, 0)
l = np.where(d < 0, -d, 0)
al = l.mean()
if al == 0:
return 100.0
return round(100 - 100 / (1 + g.mean() / al), 2)

def calc_macd(closes):
if len(closes) < 26:
return {“macd”: 0, “signal”: 0, “histogram”: 0}
arr = np.array(calc_ema_arr(closes, 12)) - np.array(calc_ema_arr(closes, 26))
sig = calc_ema(arr, 9)
macd_val = arr[-1]
return {
“macd”: round(float(macd_val), 6),
“signal”: round(sig, 6),
“histogram”: round(float(macd_val - sig), 6)
}

def calc_bb(closes, period=20):
sl = closes[-period:] if len(closes) >= period else closes
sma = sl.mean()
std = sl.std()
upper = sma + 2 * std
lower = sma - 2 * std
cur = closes[-1]
pb = ((cur - lower) / (upper - lower) * 100) if (upper - lower) > 0 else 50
bw = ((upper - lower) / sma * 100) if sma > 0 else 0
return {
“upper”: round(float(upper), 6),
“mid”: round(float(sma), 6),
“lower”: round(float(lower), 6),
“pct_b”: round(float(pb), 2),
“bandwidth”: round(float(bw), 2)
}

def calc_atr(candles, period=14):
if len(candles) < period + 1:
return 0.0
trs = []
for i in range(1, len(candles)):
c = candles[i]
p = candles[i - 1]
tr = max(c[“high”] - c[“low”], abs(c[“high”] - p[“close”]), abs(c[“low”] - p[“close”]))
trs.append(tr)
return float(np.mean(trs[-period:]))

def calc_adx(candles, period=14):
if len(candles) < period * 2:
return 20.0
trs = []
pdm = []
mdm = []
for i in range(1, len(candles)):
c = candles[i]
p = candles[i - 1]
tr = max(c[“high”] - c[“low”], abs(c[“high”] - p[“close”]), abs(c[“low”] - p[“close”]))
up = c[“high”] - p[“high”]
dn = p[“low”] - c[“low”]
trs.append(tr)
pdm.append(up if up > dn and up > 0 else 0)
mdm.append(dn if dn > up and dn > 0 else 0)
ta = np.mean(trs[-period:])
if ta == 0:
return 20.0
pdi = np.mean(pdm[-period:]) / ta * 100
mdi = np.mean(mdm[-period:]) / ta * 100
denom = pdi + mdi
dx = abs(pdi - mdi) / denom * 100 if denom > 0 else 0
return round(float(dx), 2)

def calc_vol_surge(candles, period=20):
if len(candles) < period:
return 1.0
vols = [c[“vol”] for c in candles[-period:]]
avg = np.mean(vols[:-1]) if len(vols) > 1 else vols[0]
return round(float(vols[-1] / avg), 3) if avg > 0 else 1.0

def detect_regime(candles):
closes = np.array([c[“close”] for c in candles])
cur = closes[-1]
e20 = calc_ema(closes, 20)
e50 = calc_ema(closes, 50)
n = min(200, len(closes) // 2)
e200 = calc_ema(closes, n)
adx_v = calc_adx(candles)
atr_v = calc_atr(candles)
atr_p = atr_v / cur * 100 if cur > 0 else 0
vol = calc_vol_surge(candles)
rsi_v = calc_rsi(closes)

```
if adx_v > 28 and e20 > e50 > e200 and cur > e20:
    regime = Regime.TRENDING_BULL
elif adx_v > 28 and e20 < e50 < e200 and cur < e20:
    regime = Regime.TRENDING_BEAR
elif atr_p > 4.0:
    regime = Regime.HIGH_VOLATILITY
else:
    regime = Regime.RANGING

if rsi_v > 72 and atr_p > 3:
    sent = "UNCERTAIN"
elif regime == Regime.TRENDING_BULL:
    sent = "BULLISH"
elif regime == Regime.TRENDING_BEAR:
    sent = "BEARISH"
else:
    sent = "NEUTRAL"

return MarketState(
    regime=regime,
    adx=adx_v,
    atr=atr_v,
    atr_pct=round(atr_p, 4),
    vol_surge=vol,
    sentiment=sent
)
```

# LAYER 2 - STRATEGIES

@dataclass
class Signal:
strategy: str
side: str
confidence: float
reasoning: str
indicators: Dict = field(default_factory=dict)
weight_key: str = “”

def strat_trend(candles, ms, w=1.0):
if ms.regime not in (Regime.TRENDING_BULL, Regime.TRENDING_BEAR):
return None
closes = np.array([c[“close”] for c in candles])
cur = closes[-1]
e20 = calc_ema(closes, 20)
e50 = calc_ema(closes, 50)
n = min(200, len(closes) // 2)
e200 = calc_ema(closes, n)
m = calc_macd(closes)
r = calc_rsi(closes)
adx = ms.adx

```
if ms.regime == Regime.TRENDING_BULL:
    if e20 > e50 > e200 and cur > e20 * 0.997 and m["histogram"] > 0 and 44 < r < 68 and adx > 24:
        conf = round(min(96, 50 + adx * 0.7 + 10 + (5 if r > 52 else 0)) * w, 1)
        return Signal(
            strategy="TREND_FOLLOW",
            side="buy",
            confidence=conf,
            reasoning=f"Bull EMA stack. EMA20={e20:.2f} EMA50={e50:.2f}. ADX={adx:.1f}. MACD positive. RSI={r}.",
            indicators={"ema20": e20, "ema50": e50, "rsi": r, "adx": adx},
            weight_key="trend"
        )

if ms.regime == Regime.TRENDING_BEAR:
    if e20 < e50 < e200 and cur < e20 * 1.003 and m["histogram"] < 0 and 32 < r < 56 and adx > 24:
        conf = round(min(94, 50 + adx * 0.6 + 10) * w, 1)
        return Signal(
            strategy="TREND_FOLLOW",
            side="sell",
            confidence=conf,
            reasoning=f"Bear EMA stack. ADX={adx:.1f}. MACD negative. RSI={r}.",
            indicators={"ema20": e20, "ema50": e50, "rsi": r, "adx": adx},
            weight_key="trend"
        )
return None
```

def strat_mean_rev(candles, ms, w=1.0):
if ms.regime != Regime.RANGING:
return None
closes = np.array([c[“close”] for c in candles])
cur = closes[-1]
r = calc_rsi(closes)
bb = calc_bb(closes)

```
if r < 32 and cur <= bb["lower"] * 1.006:
    conf = round(min(91, 55 + (30 - r) + (15 if cur < bb["lower"] else 0)) * w, 1)
    return Signal(
        strategy="MEAN_REVERSION",
        side="buy",
        confidence=conf,
        reasoning=f"Oversold in ranging market. RSI={r}. Price at lower BB={bb['lower']:.4f}. Target mid={bb['mid']:.4f}.",
        indicators={"rsi": r, "bb_lower": bb["lower"], "bb_mid": bb["mid"]},
        weight_key="mean_rev"
    )

if r > 68 and cur >= bb["upper"] * 0.994:
    conf = round(min(89, 55 + (r - 70) + (15 if cur > bb["upper"] else 0)) * w, 1)
    return Signal(
        strategy="MEAN_REVERSION",
        side="sell",
        confidence=conf,
        reasoning=f"Overbought in ranging market. RSI={r}. Price at upper BB={bb['upper']:.4f}.",
        indicators={"rsi": r, "bb_upper": bb["upper"], "bb_mid": bb["mid"]},
        weight_key="mean_rev"
    )
return None
```

def strat_breakout(candles, ms, w=1.0):
if len(candles) < 30:
return None
lookback = candles[-22:-2]
resistance = max(c[“high”] for c in lookback)
support = min(c[“low”] for c in lookback)
cur = candles[-1][“close”]
vol = ms.vol_surge
atr = ms.atr
tight = (resistance - support) < atr * 13

```
if cur > resistance * 1.001 and vol > 1.4 and tight:
    conf = round(min(90, 55 + min(20, (vol - 1.4) * 20)) * w, 1)
    return Signal(
        strategy="BREAKOUT",
        side="buy",
        confidence=conf,
        reasoning=f"Bullish breakout above {resistance:.4f}. Volume {vol:.2f}x surge confirms buyers.",
        indicators={"resistance": resistance, "support": support, "vol_surge": vol},
        weight_key="breakout"
    )

if cur < support * 0.999 and vol > 1.4 and tight:
    conf = round(min(87, 52 + min(20, (vol - 1.4) * 18)) * w, 1)
    return Signal(
        strategy="BREAKOUT",
        side="sell",
        confidence=conf,
        reasoning=f"Bearish breakdown below {support:.4f}. Volume {vol:.2f}x confirms sellers.",
        indicators={"resistance": resistance, "support": support, "vol_surge": vol},
        weight_key="breakout"
    )
return None
```

def select_signal(candles, ms, weights):
if ms.sentiment == “UNCERTAIN” or ms.atr_pct > 5.5:
return None
candidates = [
strat_trend(candles, ms, weights.get(“trend”, 1.0)),
strat_mean_rev(candles, ms, weights.get(“mean_rev”, 1.0)),
strat_breakout(candles, ms, weights.get(“breakout”, 1.0))
]
valid = [s for s in candidates if s is not None]
if not valid:
return None
return max(valid, key=lambda s: s.confidence)

# LAYER 3 - RISK MANAGEMENT

MAX_RISK = 0.05
MAX_DD = 0.05
MIN_RR = 2.0
MIN_CONF = 70.0
MAX_POSITIONS = 3
SL_MULT = 1.8
TP_MULT = 3.6

@dataclass
class RiskResult:
approved: bool
reason: str
qty: float
risk_pct: float
sl: float
tp: float
rr: float

class RiskManager:
def **init**(self, capital):
self.capital = capital
self.daily_pnl = 0.0
self.halted = False

```
def reset(self):
    self.daily_pnl = 0.0
    self.halted = False

def add_pnl(self, pnl):
    self.daily_pnl += pnl
    if self.daily_pnl < -self.capital * MAX_DD:
        self.halted = True

def evaluate(self, conf, side, price, atr, balance, n_open):
    def reject(r):
        return RiskResult(False, r, 0, 0, 0, 0, 0)

    if self.halted:
        return reject("HALTED - daily drawdown limit hit")
    if self.daily_pnl < -self.capital * MAX_DD:
        self.halted = True
        return reject("Max daily drawdown exceeded")
    if conf < MIN_CONF:
        return reject(f"Confidence {conf:.0f}% below {MIN_CONF}% minimum")
    if n_open >= MAX_POSITIONS:
        return reject(f"Max {MAX_POSITIONS} positions open")

    if side == "buy":
        sl = round(price - atr * SL_MULT, 8)
        tp = round(price + atr * TP_MULT, 8)
    else:
        sl = round(price + atr * SL_MULT, 8)
        tp = round(price - atr * TP_MULT, 8)

    risk = abs(price - sl)
    reward = abs(tp - price)
    rr = reward / risk if risk > 0 else 0

    if rr < MIN_RR:
        return reject(f"R:R={rr:.2f} below minimum {MIN_RR}:1")

    risk_amt = balance * MAX_RISK
    qty = round(risk_amt / risk, 6) if risk > 0 else 0

    if qty <= 0 or qty * price > balance * 0.9:
        return reject("Insufficient balance")

    return RiskResult(True, "Approved", qty, round(MAX_RISK * 100, 2), sl, tp, round(rr, 2))
```

# LAYER 4 - TRADE DECISION

@dataclass
class Trade:
id: int
symbol: str
condition: str
strategy: str
side: str
entry: float
sl: float
tp: float
qty: float
risk_pct: float
rr: float
confidence: float
reasoning: str
indicators: Dict = field(default_factory=dict)
timestamp: str = “”
status: str = “PENDING”
exit_price: float = 0.0
pnl: float = 0.0
exit_reason: str = “”
order_id: str = “”

class SelfLearn:
def **init**(self):
self.weights = {“trend”: 1.0, “mean_rev”: 1.0, “breakout”: 1.0}

```
def update(self, trade):
    key_map = {"TREND_FOLLOW": "trend", "MEAN_REVERSION": "mean_rev", "BREAKOUT": "breakout"}
    wk = key_map.get(trade.strategy)
    if not wk:
        return
    step = 0.05 + (0.04 if trade.confidence >= 85 else 0)
    w = self.weights[wk]
    if trade.pnl > 0:
        self.weights[wk] = round(min(1.7, w + step), 3)
    else:
        self.weights[wk] = round(max(0.4, w - step), 3)
```

class TradeLog:
def **init**(self):
self._trades = []
self._log = []

```
def add(self, t):
    self._trades.insert(0, t)

def sys(self, msg):
    e = {"t": time.strftime("%H:%M:%S"), "msg": msg}
    self._log.insert(0, e)
    if len(self._log) > 300:
        self._log.pop()
    print(f"[{e['t']}] {msg}")

@property
def closed(self):
    return [t for t in self._trades if t.status == "CLOSED"]

@property
def win_rate(self):
    c = self.closed
    return round(sum(1 for t in c if t.pnl > 0) / len(c) * 100, 1) if c else 0.0

@property
def avg_pnl(self):
    c = self.closed
    return round(sum(t.pnl for t in c) / len(c), 4) if c else 0.0

def get_trades(self, n=50):
    return [asdict(t) for t in self._trades[:n]]

def get_log(self, n=80):
    return self._log[:n]
```

_ID_COUNTER = int(time.time())

def next_id():
global _ID_COUNTER
_ID_COUNTER += 1
return _ID_COUNTER

def make_decision(symbol, signal, ms, risk, price):
return Trade(
id=next_id(),
symbol=symbol,
condition=ms.regime.value,
strategy=signal.strategy,
side=signal.side.upper(),
entry=round(price, 8),
sl=risk.sl,
tp=risk.tp,
qty=risk.qty,
risk_pct=risk.risk_pct,
rr=risk.rr,
confidence=signal.confidence,
reasoning=signal.reasoning,
indicators=signal.indicators,
timestamp=time.strftime(”%Y-%m-%dT%H:%M:%SZ”, time.gmtime()),
status=“PENDING”
)

# LAYER 5 - BITGET CLIENT

class BitgetClient:
BASE = “https://api.bitget.com”

```
def __init__(self, api_key, passphrase, private_key_pem):
    self.api_key = api_key
    self.passphrase = passphrase
    self._pkey = None
    if private_key_pem.strip():
        try:
            self._pkey = serialization.load_pem_private_key(private_key_pem.encode(), password=None)
        except Exception as e:
            print(f"Key warning: {e}")
    self._session = None

def _sign(self, ts, method, path, body=""):
    msg = f"{ts}{method.upper()}{path}{body}".encode()
    sig = self._pkey.sign(msg, apad.PKCS1v15(), hashes.SHA256())
    return base64.b64encode(sig).decode()

def _headers(self, method, path, body=""):
    ts = str(int(time.time() * 1000))
    sign = self._sign(ts, method, path, body) if self._pkey else "demo"
    return {
        "Content-Type": "application/json",
        "ACCESS-KEY": self.api_key,
        "ACCESS-SIGN": sign,
        "ACCESS-TIMESTAMP": ts,
        "ACCESS-PASSPHRASE": self.passphrase,
        "locale": "en-US"
    }

async def _get_session(self):
    if not self._session or self._session.closed:
        self._session = aiohttp.ClientSession()
    return self._session

async def get(self, path):
    s = await self._get_session()
    async with s.get(self.BASE + path, headers=self._headers("GET", path), timeout=aiohttp.ClientTimeout(total=5)) as r:
        return await r.json()

async def post(self, path, body):
    s = await self._get_session()
    b = json.dumps(body)
    async with s.post(self.BASE + path, headers=self._headers("POST", path, b), data=b, timeout=aiohttp.ClientTimeout(total=5)) as r:
        return await r.json()

async def get_balance(self):
    try:
        r = await self.get("/api/v2/spot/account/assets?coin=USDT")
        if r.get("code") == "00000" and r.get("data"):
            return float(r["data"][0].get("available", 0))
    except Exception:
        pass
    return 0.0

async def get_candles(self, symbol, limit=200):
    try:
        path = f"/api/v2/spot/market/candles?symbol={symbol}&granularity=1min&limit={limit}"
        r = await self.get(path)
        if r.get("code") == "00000" and r.get("data"):
            out = []
            for c in reversed(r["data"]):
                out.append({"t": int(c[0]), "open": float(c[1]), "high": float(c[2]), "low": float(c[3]), "close": float(c[4]), "vol": float(c[5])})
            return out
    except Exception:
        pass
    return []

async def get_price(self, symbol):
    try:
        r = await self.get(f"/api/v2/spot/market/tickers?symbol={symbol}")
        if r.get("code") == "00000" and r.get("data"):
            d = r["data"][0]
            bid = float(d.get("bidPr", 0))
            ask = float(d.get("askPr", 0))
            p = float(d.get("lastPr", 0))
            return {"price": p, "bid": bid, "ask": ask, "spread_pct": (ask - bid) / p if p > 0 else 0}
    except Exception:
        pass
    return {}

async def place_limit_order(self, symbol, side, price, qty):
    body = {"symbol": symbol, "side": side, "orderType": "limit", "force": "gtc", "price": str(round(price, 8)), "size": str(qty)}
    try:
        r = await self.post("/api/v2/spot/trade/place-order", body)
        if r.get("code") == "00000":
            return r.get("data", {}).get("orderId", "")
    except Exception:
        pass
    return None

async def place_market_order(self, symbol, side, qty):
    body = {"symbol": symbol, "side": side, "orderType": "market", "force": "gtc", "size": str(qty)}
    try:
        r = await self.post("/api/v2/spot/trade/place-order", body)
        return r.get("code") == "00000"
    except Exception:
        pass
    return False
```

# DEMO DATA

BASE_PRICES = {“BTCUSDT”: 67800.0, “ETHUSDT”: 3540.0, “SOLUSDT”: 172.0}
VOL_MAP = {“BTCUSDT”: 0.006, “ETHUSDT”: 0.008, “SOLUSDT”: 0.012}

def gen_candles(symbol, n=200):
p = BASE_PRICES[symbol]
v = VOL_MAP[symbol]
out = []
for _ in range(n):
o = p
p = p * (1 + v * random.gauss(0, 1) * 0.4)
c = p
h = max(o, c) * (1 + abs(random.gauss(0, 1)) * 0.001)
l = min(o, c) * (1 - abs(random.gauss(0, 1)) * 0.001)
out.append({“t”: int(time.time() * 1000), “open”: o, “high”: h, “low”: l, “close”: c, “vol”: 500000.0})
return out

def update_candles(candles, symbol):
last = candles[-1][“close”]
v = VOL_MAP[symbol]
new = last * (1 + v * random.gauss(0, 1) * 0.3)
h = max(last, new) * 1.0004
l = min(last, new) * 0.9996
candles.append({“t”: int(time.time() * 1000), “open”: last, “high”: h, “low”: l, “close”: new, “vol”: 500000.0})
if len(candles) > 300:
candles.pop(0)
return new

# GLOBAL STATE

class State:
def **init**(self):
self.running = False
self.balance = CAPITAL
self.positions = []
self.candles = {s: gen_candles(s) for s in SYMBOLS}
self.prices = {s: {“price”: BASE_PRICES[s], “bid”: 0, “ask”: 0, “spread_pct”: 0} for s in SYMBOLS}
self.regimes = {}

S = State()
risk_mgr = RiskManager(CAPITAL)
learner = SelfLearn()
trade_log = TradeLog()
client = BitgetClient(API_KEY, PASSPHRASE, PRIVATE_KEY) if not DEMO_MODE else None

# AGENT LOOPS

async def tick_demo():
while S.running:
for sym in SYMBOLS:
new_p = update_candles(S.candles[sym], sym)
spread = new_p * 0.0002
S.prices[sym] = {“price”: new_p, “bid”: new_p - spread, “ask”: new_p + spread, “spread_pct”: 0.0002}
await asyncio.sleep(2)

async def check_positions():
for pos in list(S.positions):
cur = S.prices.get(pos.symbol, {}).get(“price”, pos.entry)
if cur == 0:
continue
hit_sl = (pos.side == “BUY” and cur <= pos.sl) or (pos.side == “SELL” and cur >= pos.sl)
hit_tp = (pos.side == “BUY” and cur >= pos.tp) or (pos.side == “SELL” and cur <= pos.tp)
if hit_sl or hit_tp:
reason = “TAKE_PROFIT” if hit_tp else “STOP_LOSS”
if pos.side == “BUY”:
pnl = (cur - pos.entry) * pos.qty
else:
pnl = (pos.entry - cur) * pos.qty
pos.pnl = round(pnl, 4)
pos.exit_price = cur
pos.exit_reason = reason
pos.status = “CLOSED”
risk_mgr.add_pnl(pnl)
learner.update(pos)
S.balance += pos.qty * cur
S.positions = [p for p in S.positions if p.id != pos.id]
emoji = “WIN” if pnl > 0 else “LOSS”
trade_log.sys(f”{emoji} CLOSED {pos.symbol} {pos.side} PnL=${pnl:+.2f} | {reason}”)
if client:
close_side = “sell” if pos.side == “BUY” else “buy”
await client.place_market_order(pos.symbol, close_side, pos.qty)

async def run_analysis():
for sym in SYMBOLS:
if not S.running or risk_mgr.halted:
break
if len(S.positions) >= MAX_POSITIONS:
break
candles = S.candles.get(sym, [])
if len(candles) < 50:
continue
if client:
live = await client.get_candles(sym)
if live:
S.candles[sym] = live
candles = live
tick = await client.get_price(sym)
if tick:
S.prices[sym] = tick
cur = S.prices[sym].get(“price”, candles[-1][“close”])
ms = detect_regime(candles)
S.regimes[sym] = ms
sig = select_signal(candles, ms, learner.weights)
if not sig:
continue
rp = risk_mgr.evaluate(sig.confidence, sig.side, cur, ms.atr, S.balance, len(S.positions))
if not rp.approved:
trade_log.sys(f”REJECT {sym}: {rp.reason}”)
continue
trade = make_decision(sym, sig, ms, rp, cur)
trade_log.sys(f”SIGNAL {sym} {trade.side} @ {cur:.4f} | SL={rp.sl:.4f} TP={rp.tp:.4f} | Conf={sig.confidence:.0f}% | {sig.strategy}”)
order_id = None
if client:
order_id = await client.place_limit_order(sym, sig.side, cur, rp.qty)
if not order_id:
trade_log.sys(f”EXEC FAIL {sym}”)
continue
trade.order_id = order_id or “DEMO”
trade.status = “OPEN”
S.balance -= rp.qty * cur
S.positions.append(trade)
trade_log.add(trade)
break

async def agent_loop():
mode = “DEMO” if DEMO_MODE else “LIVE”
trade_log.sys(f”JD TRADER STARTED [{mode}]”)
demo_task = asyncio.create_task(tick_demo()) if DEMO_MODE else None
while S.running:
try:
await check_positions()
await run_analysis()
except Exception as e:
trade_log.sys(f”Loop error: {e}”)
await asyncio.sleep(CYCLE_SECS)
if demo_task:
demo_task.cancel()

# FASTAPI APP

app = FastAPI(title=“JD Trader”)
app.add_middleware(CORSMiddleware, allow_origins=[”*”], allow_methods=[”*”], allow_headers=[”*”])

loop_task = None

@app.post(”/agent/start”)
async def start():
global loop_task
if S.running:
return {“ok”: True, “msg”: “Already running”}
S.running = True
risk_mgr.reset()
loop_task = asyncio.create_task(agent_loop())
return {“ok”: True}

@app.post(”/agent/stop”)
async def stop():
S.running = False
if loop_task:
loop_task.cancel()
trade_log.sys(“Agent stopped”)
return {“ok”: True}

@app.post(”/agent/reset”)
async def reset():
risk_mgr.reset()
trade_log.sys(“Reset - daily limits cleared”)
return {“ok”: True}

@app.get(”/state”)
async def state():
if client:
bal = await client.get_balance()
if bal > 0:
S.balance = bal
closed = trade_log.closed
wins = sum(1 for t in closed if t.pnl > 0)
return {
“balance”: round(S.balance, 4),
“initialCapital”: CAPITAL,
“running”: S.running,
“halted”: risk_mgr.halted,
“dailyPnl”: round(risk_mgr.daily_pnl, 4),
“demo”: DEMO_MODE,
“openPositions”: [asdict(p) for p in S.positions],
“trades”: trade_log.get_trades(50),
“log”: trade_log.get_log(80),
“weights”: learner.weights,
“regime”: {s: (ms.regime.value if ms else “RANGING”) for s, ms in S.regimes.items()},
“stats”: {
“total”: len(closed),
“wins”: wins,
“losses”: len(closed) - wins,
“winRate”: trade_log.win_rate,
“avgPnl”: trade_log.avg_pnl
},
“prices”: {s: {“price”: round(d.get(“price”, 0), 4)} for s, d in S.prices.items()}
}

@app.get(”/health”)
async def health():
return {“ok”: True, “mode”: “DEMO” if DEMO_MODE else “LIVE”}

DASHBOARD = “””<!DOCTYPE html>

<html><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>JD TRADER</title>
<link href="https://fonts.googleapis.com/css2?family=Rajdhani:wght@600;700&family=JetBrains+Mono:wght@400;700&display=swap" rel="stylesheet">
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{background:#060a0f;color:#8899aa;font-family:'Rajdhani',sans-serif}
.mono{font-family:'JetBrains Mono',monospace}
header{display:flex;align-items:center;justify-content:space-between;padding:14px 20px;border-bottom:1px solid #0f1822}
.logo{font-size:22px;font-weight:700;color:#ccd5de}.logo span{color:#39ff90}
.btn{border:none;cursor:pointer;border-radius:6px;padding:9px 22px;font-family:'Rajdhani',sans-serif;font-weight:700;font-size:13px}
.btn-live{background:#39ff9015;border:1px solid #39ff9050;color:#39ff90}
.btn-halt{background:#ff3b5c15;border:1px solid #ff3b5c50;color:#ff3b5c}
.grid6{display:grid;grid-template-columns:repeat(3,1fr);gap:10px;padding:16px 20px}
@media(min-width:600px){.grid6{grid-template-columns:repeat(6,1fr)}}
.grid2{display:grid;grid-template-columns:1fr;gap:14px;padding:0 20px 20px}
@media(min-width:800px){.grid2{grid-template-columns:1fr 300px}}
.card{background:#0a0e14;border:1px solid #1a2535;border-radius:8px;padding:14px 16px}
.cl{font-size:10px;color:#3a4a5c;letter-spacing:.12em;font-weight:700;text-transform:uppercase;margin-bottom:5px}
.cv{font-family:'JetBrains Mono',monospace;font-size:18px;font-weight:700}
.st{font-size:11px;color:#3a4a5c;font-weight:700;letter-spacing:.12em;margin-bottom:10px}
.tabs{display:flex;border-bottom:1px solid #0f1822;padding:0 16px}
.tab{background:none;border:none;cursor:pointer;padding:8px 14px;font-family:'Rajdhani',sans-serif;font-weight:700;font-size:12px;letter-spacing:.1em;text-transform:uppercase;border-bottom:2px solid transparent;color:#2d3d50}
.tab.on{color:#39ff90;border-bottom-color:#39ff90}
.scroll{max-height:300px;overflow-y:auto;padding:12px 16px}
.sig{background:#060a0f;border-radius:7px;padding:12px;margin-bottom:8px}
.sg{display:grid;grid-template-columns:repeat(3,1fr);gap:6px;margin:8px 0}
.sc{background:#0a0e14;border-radius:5px;padding:5px 8px}
.scl{font-size:9px;color:#2d3d50;font-weight:700;letter-spacing:.1em}
.scv{font-family:'JetBrains Mono',monospace;font-size:12px;font-weight:700}
.tr{display:grid;grid-template-columns:60px 75px 50px 80px 65px 1fr;gap:6px;padding:7px 0;border-bottom:1px solid #0a0e14;font-size:11px;align-items:center}
.lr{font-family:'JetBrains Mono',monospace;font-size:11px;color:#4a5a6a;padding:4px 0;border-bottom:1px solid #0a0e14}
.pr{display:flex;justify-content:space-between;padding:6px 0;border-bottom:1px solid #0f1822;font-size:12px}
.wb{height:3px;background:#0f1822;border-radius:2px;margin-top:5px}
.wf{height:100%;border-radius:2px;opacity:.75;transition:width .5s ease}
.dot{display:inline-block;width:7px;height:7px;border-radius:50%;margin-right:6px;animation:pulse 1.2s ease-in-out infinite}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.3}}
@keyframes su{from{opacity:0;transform:translateY(5px)}to{opacity:1;transform:translateY(0)}}
.demo{background:#f0c04010;border-bottom:1px solid #f0c04030;padding:8px 20px;font-size:12px;color:#f0c040;text-align:center}
</style></head><body>
<div id="db" style="display:none" class="demo">DEMO MODE - Add Bitget API keys to trade live</div>
<header>
<div style="display:flex;align-items:center;gap:12px">
<div style="width:38px;height:38px;border-radius:8px;background:#39ff9012;border:1px solid #39ff9030;display:flex;align-items:center;justify-content:center;font-size:20px">⚡</div>
<div><div class="logo">JD <span>TRADER</span></div><div style="font-size:10px;color:#2d3d50;letter-spacing:.15em">INSTITUTIONAL QUANT</div></div>
</div>
<div style="display:flex;gap:10px;align-items:center">
<div id="rb" style="padding:4px 12px;border-radius:20px;font-size:11px;font-weight:700;background:#f0c04010;border:1px solid #f0c04030;color:#f0c040">RANGING</div>
<button id="mb" class="btn btn-live" onclick="toggle()">GO LIVE</button>
</div>
</header>
<div class="grid6">
<div class="card"><div class="cl">Equity</div><div class="cv" id="eq" style="color:#ccd5de">$50</div></div>
<div class="card"><div class="cl">Total P&L</div><div class="cv" id="pnl">$0</div><div id="pp" style="font-size:11px;color:#3a4a5c">+0%</div></div>
<div class="card"><div class="cl">Daily P&L</div><div class="cv" id="dp">$0</div></div>
<div class="card"><div class="cl">Win Rate</div><div class="cv" id="wr" style="color:#39ff90">-</div></div>
<div class="card"><div class="cl">Avg P&L</div><div class="cv" id="ap">-</div></div>
<div class="card"><div class="cl">Trades</div><div class="cv" id="tc" style="color:#7b61ff">0</div></div>
</div>
<div style="display:grid;grid-template-columns:repeat(3,1fr);gap:10px;padding:0 20px 14px">
<div class="card" id="pBTCUSDT"><div class="cl">BTC/USDT</div><div class="cv" style="color:#ccd5de;font-size:16px">-</div></div>
<div class="card" id="pETHUSDT"><div class="cl">ETH/USDT</div><div class="cv" style="color:#ccd5de;font-size:16px">-</div></div>
<div class="card" id="pSOLUSDT"><div class="cl">SOL/USDT</div><div class="cv" style="color:#ccd5de;font-size:16px">-</div></div>
</div>
<div class="grid2">
<div style="display:flex;flex-direction:column;gap:14px">
<div class="card" style="padding:0;overflow:hidden">
<div class="tabs">
<button class="tab on" onclick="setTab('s',this)">Signals</button>
<button class="tab" onclick="setTab('t',this)">Trades</button>
<button class="tab" onclick="setTab('l',this)">Log</button>
</div>
<div class="scroll" id="ts"></div>
<div class="scroll" id="tt" style="display:none"></div>
<div class="scroll" id="tl" style="display:none"></div>
</div>
</div>
<div style="display:flex;flex-direction:column;gap:14px">
<div class="card"><div class="st">OPEN POSITIONS (<span id="pc">0</span>/3)</div><div id="pl"><div style="color:#1a2535;text-align:center;padding:16px 0;font-size:13px">No open positions</div></div></div>
<div class="card"><div class="st">SELF-LEARNING WEIGHTS</div><div id="wp"></div></div>
<div class="card"><div class="st">RISK RULES</div>
<div class="pr"><span style="color:#4a5a6a">Risk per trade</span><span class="mono" style="color:#f0c040;font-weight:700">5%</span></div>
<div class="pr"><span style="color:#4a5a6a">Min R:R</span><span class="mono" style="color:#39ff90;font-weight:700">1:2</span></div>
<div class="pr"><span style="color:#4a5a6a">Min confidence</span><span class="mono" style="color:#7b61ff;font-weight:700">70%</span></div>
<div class="pr"><span style="color:#4a5a6a">Daily loss limit</span><span class="mono" style="color:#ff3b5c;font-weight:700">5% HALT</span></div>
</div>
</div>
</div>
<script>
let st={},tab='s';
const RC={TRENDING_BULL:'#39ff90',TRENDING_BEAR:'#ff3b5c',RANGING:'#f0c040',HIGH_VOLATILITY:'#ff8c42'};
const SC={TREND_FOLLOW:'#39ff90',MEAN_REVERSION:'#7b61ff',BREAKOUT:'#ff8c42'};
function clr(n){return n>=0?'#39ff90':'#ff3b5c'}
function sgn(n){return(n>=0?'+':'')+Number(n).toFixed(2)}
function fmt(n,d=2){return Number(n).toFixed(d)}
function fk(n){return n>=1000?'$'+(n/1000).toFixed(2)+'k':'$'+fmt(n)}
async function poll(){
try{const r=await fetch('/state');st=await r.json();render();}catch(e){}
}
function render(){
document.getElementById('db').style.display=st.demo?'block':'none';
const b=st.balance||0,c=st.initialCapital||50;
const pnl=b-c,pct=pnl/c*100;
document.getElementById('eq').textContent=fk(b);
const pe=document.getElementById('pnl');pe.textContent=sgn(pnl);pe.style.color=clr(pnl);
document.getElementById('pp').textContent=(pct>=0?'+':'')+fmt(pct)+'%';
const de=document.getElementById('dp');const dp=st.dailyPnl||0;de.textContent=sgn(dp);de.style.color=clr(dp);
const s=st.stats||{};
const we=document.getElementById('wr');we.textContent=s.total?s.winRate+'%':'-';we.style.color=s.winRate>=50?'#39ff90':'#ff3b5c';
const ae=document.getElementById('ap');ae.textContent=s.total?'$'+fmt(s.avgPnl):'-';ae.style.color=(s.avgPnl||0)>=0?'#39ff90':'#ff3b5c';
document.getElementById('tc').textContent=s.total||0;
for(const[sym,d] of Object.entries(st.prices||{})){
const el=document.getElementById('p'+sym);
if(el)el.querySelector('.cv').textContent=d.price>0?d.price.toLocaleString(undefined,{minimumFractionDigits:2,maximumFractionDigits:4}):'-';
}
const reg=Object.values(st.regime||{})[0]||'RANGING';
const rb=document.getElementById('rb');const rc=RC[reg]||'#f0c040';
rb.textContent=reg.replace('_',' ');rb.style.color=rc;rb.style.borderColor=rc+'40';rb.style.background=rc+'10';
const mb=document.getElementById('mb');
if(st.halted){mb.className='btn btn-halt';mb.textContent='HALTED';}
else if(st.running){mb.className='btn btn-halt';mb.innerHTML='<span class="dot" style="background:#ff3b5c;box-shadow:0 0 8px #ff3b5c"></span>HALT';}
else{mb.className='btn btn-live';mb.textContent='GO LIVE';}
const pos=st.openPositions||[];
document.getElementById('pc').textContent=pos.length;
document.getElementById('pl').innerHTML=pos.length?pos.map(p=>`<div style="padding:8px 0;border-bottom:1px solid #0f1822"><div style="display:flex;justify-content:space-between"><span style="font-weight:700;color:#ccd5de">${p.symbol}</span><span style="color:${p.side==='BUY'?'#39ff90':'#ff3b5c'};font-weight:700">${p.side}</span></div><div class="mono" style="font-size:11px;color:#4a5a6a;margin-top:3px">@ ${fmt(p.entry,4)} | SL <span style="color:#ff3b5c">${fmt(p.sl,4)}</span> | TP <span style="color:#39ff90">${fmt(p.tp,4)}</span></div></div>`).join(''):'<div style="color:#1a2535;text-align:center;padding:16px 0;font-size:13px">No open positions</div>';
const w=st.weights||{};
const wl={trend:'TREND',mean_rev:'MEAN REV',breakout:'BREAKOUT'};
const wc={trend:'#39ff90',mean_rev:'#7b61ff',breakout:'#ff8c42'};
document.getElementById('wp').innerHTML=Object.entries(w).map(([k,v])=>`<div style="margin-bottom:10px"><div style="display:flex;justify-content:space-between;font-size:12px;margin-bottom:4px"><span style="color:#4a5a6a">${wl[k]||k}</span><span class="mono" style="color:${wc[k]};font-weight:700">${Number(v).toFixed(2)}x</span></div><div class="wb"><div class="wf" style="width:${Math.min(100,v/1.7*100)}%;background:${wc[k]}"></div></div></div>`).join('');
renderSigs();renderTrades();renderLog();
}
function renderSigs(){
const el=document.getElementById('ts');
const items=[...(st.openPositions||[]).filter(p=>p.status==='OPEN'),...(st.trades||[]).filter(t=>t.status==='PENDING')].slice(0,15);
if(!items.length){el.innerHTML='<div style="color:#1a2535;text-align:center;padding:24px 0;font-size:13px">No signals yet - tap GO LIVE</div>';return;}
el.innerHTML=items.map(s=>{
const sc=SC[s.strategy]||'#39ff90';const cc=s.confidence>=85?'#39ff90':s.confidence>=70?'#f0c040':'#ff3b5c';
return`<div class="sig" style="border:1px solid ${sc}25;animation:su .25s ease"><div style="display:flex;justify-content:space-between;margin-bottom:8px"><div style="display:flex;gap:8px;align-items:center"><span style="color:${sc};font-weight:700;font-size:13px">${s.strategy.replace('_',' ')}</span><span class="mono" style="color:${s.side==='BUY'?'#39ff90':'#ff3b5c'};font-size:11px;font-weight:700">${s.side}</span><span class="mono" style="color:#4a5a6a;font-size:11px">${s.symbol}</span></div><div class="mono" style="font-size:13px;font-weight:700;color:${cc};background:${cc}15;border:1px solid ${cc}40;border-radius:4px;padding:2px 8px">${s.confidence}%</div></div><div class="sg">${[['Entry',fmt(s.entry,4),'#ccd5de'],['Stop Loss',fmt(s.sl,4),'#ff3b5c'],['Take Profit',fmt(s.tp,4),'#39ff90'],['Risk%',s.risk_pct+'%','#f0c040'],['R:R','1:'+s.rr,'#7b61ff'],['Strategy',s.strategy.split('_')[0],'#4a5a6a']].map(([l,v,c])=>`<div class="sc"><div class="scl">${l}</div><div class="scv" style="color:${c}">${v}</div></div>`).join('')}</div><div style="font-size:11px;color:#4a5a6a;line-height:1.5;border-top:1px solid #0f1822;padding-top:7px">${s.reasoning}</div></div>`;}).join('');
}
function renderTrades(){
const el=document.getElementById('tt');
const trades=(st.trades||[]).filter(t=>t.status==='CLOSED');
if(!trades.length){el.innerHTML='<div style="color:#1a2535;text-align:center;padding:24px 0;font-size:13px">No closed trades yet</div>';return;}
el.innerHTML=trades.map(t=>`<div class="tr" style="animation:su .25s ease"><span class="mono" style="color:#2d3d50;font-size:10px">${(t.timestamp||'').substr(11,8)}</span><span class="mono" style="color:#4a5a6a;font-size:11px">${t.symbol}</span><span style="color:${t.side==='BUY'?'#39ff90':'#ff3b5c'};font-weight:700">${t.side}</span><span style="font-size:10px;color:#4a5a6a">${t.strategy.split('_')[0]}</span><span class="mono" style="color:${clr(t.pnl)};font-weight:700">${t.pnl>=0?'+':''}$${fmt(t.pnl)}</span><span style="font-size:10px;font-weight:700;color:${t.pnl>0?'#39ff9060':'#ff3b5c60'}">${t.exit_reason}</span></div>`).join('');
}
function renderLog(){
const el=document.getElementById('tl');
const logs=st.log||[];
if(!logs.length){el.innerHTML='<div style="color:#1a2535;text-align:center;padding:24px 0;font-size:13px">Log empty</div>';return;}
el.innerHTML=logs.map(l=>`<div class="lr"><span style="color:#2d3d50;margin-right:8px">${l.t}</span>${l.msg}</div>`).join('');
}
function setTab(n,btn){
tab=n;
['s','t','l'].forEach(t=>document.getElementById('t'+t).style.display=t===n?'block':'none');
document.querySelectorAll('.tab').forEach(b=>b.classList.remove('on'));
btn.classList.add('on');
}
async function toggle(){
if(st.halted){await fetch('/agent/reset',{method:'POST'});setTimeout(poll,500);return;}
await fetch('/agent/'+(st.running?'stop':'start'),{method:'POST'});
setTimeout(poll,500);
}
poll();setInterval(poll,3000);
</script>
</body></html>"""

@app.get(”/”, response_class=HTMLResponse)
async def dashboard():
return DASHBOARD

if **name** == “**main**”:
import uvicorn
port = int(os.getenv(“PORT”, 8000))
print(f”JD TRADER starting on port {port} | Mode: {‘DEMO’ if DEMO_MODE else ‘LIVE’}”)
uvicorn.run(app, host=“0.0.0.0”, port=port)
