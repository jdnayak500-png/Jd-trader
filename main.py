"""
╔══════════════════════════════════════════════════════════════╗
║ JD TRADER — INSTITUTIONAL QUANT ENGINE ║
║ All 8 Layers | Single File | Bitget RSA API ║
║ Paste this ONE file into Replit ║
╚══════════════════════════════════════════════════════════════╝
"""
import os, time, json, random, math, asyncio, base64, hashlib
from dataclasses import dataclass, field, asdict
from typing import Optional, Dict, List
from enum import Enum
# ── Auto-install dependencies ──────────────────────────────────
import subprocess, sys
def install(pkg):
subprocess.check_call([sys.executable, "-m", "pip", "install", pkg, "-q"])
for pkg in ["fastapi", "uvicorn", "aiohttp", "websockets", "numpy", "cryptography"]:
try:
__import__(pkg.replace("-","_").split("[")[0])
except ImportError:
print(f"Installing {pkg}...")
install(pkg)
import numpy as np
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
import aiohttp
# ══════════════════════════════════════════════════════════════
# CONFIG — Edit these with your Bitget details
# ══════════════════════════════════════════════════════════════
API_KEY = os.getenv("BITGET_API_KEY", "")
PASSPHRASE = os.getenv("BITGET_PASSPHRASE", "")
PRIVATE_KEY = os.getenv("BITGET_PRIVATE_KEY", "").replace("\\n", "\n")
CAPITAL = float(os.getenv("INITIAL_CAPITAL", "500"))
SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
CYCLE_SECS = 20
DEMO_MODE = not bool(API_KEY)
# ══════════════════════════════════════════════════════════════
# LAYER 1 — MARKET ANALYSIS
# ══════════════════════════════════════════════════════════════
class Regime(Enum):
TRENDING_BULL = "TRENDING_BULL"
TRENDING_BEAR = "TRENDING_BEAR"
RANGING = "RANGING"
HIGH_VOLATILITY = "HIGH_VOLATILITY"
@dataclass
class MarketState:
regime: Regime
adx: float
atr: float
atr_pct: float
vol_surge:float
sentiment:str
def _ema(prices, period):
if len(prices) < period: return float(prices[-1])
k = 2.0 / (period + 1)
v = prices[0]
for p in prices[1:]: v = p * k + v * (1 - k)
return v
def _ema_arr(prices, period):
k = 2.0 / (period + 1)
out = [prices[0]]
for p in prices[1:]: out.append(p * k + out[-1] * (1 - k))
return out
def _rsi(closes, period=14):
if len(closes) < period + 1: return 50.0
d = np.diff(closes[-(period+1):])
g, l = np.where(d>0,d,0), np.where(d<0,-d,0)
al = l.mean()
return round(100 - 100/(1 + g.mean()/al), 2) if al > 0 else 100.0
def _macd(closes):
if len(closes) < 26: return {"macd":0,"signal":0,"histogram":0}
arr = np.array(_ema_arr(closes,12)) - np.array(_ema_arr(closes,26))
sig = _ema(arr, 9)
macd_ = arr[-1]
return {"macd":round(float(macd_),6),"signal":round(sig,6),"histogram":round(float(macd_-
def _bb(closes, period=20):
sl = closes[-period:] if len(closes) >= period else closes
sma = sl.mean(); std = sl.std()
up, lo = sma+2*std, sma-2*std
cur = closes[-1]
pb = ((cur-lo)/(up-lo)*100) if (up-lo)>0 else 50
return {"upper":round(float(up),6),"mid":round(float(sma),6),
"lower":round(float(lo),6),"pct_b":round(float(pb),2),
"bandwidth":round(float((up-lo)/sma*100),2) if sma>0 else 0}
def _atr(candles, period=14):
if len(candles) < period+1: return 0.0
trs = [max(c["high"]-c["low"], abs(c["high"]-candles[i-1]["close"]),
abs(c["low"]-candles[i-1]["close"]))
for i,c in enumerate(candles) if i > 0]
return float(np.mean(trs[-period:]))
def _adx(candles, period=14):
if len(candles) < period*2: return 20.0
trs, pdm, mdm = [], [], []
for i in range(1, len(candles)):
c,p = candles[i], candles[i-1]
tr = max(c["high"]-c["low"], abs(c["high"]-p["close"]), abs(c["low"]-p["close"]))
up = c["high"]-p["high"]; dn = p["low"]-c["low"]
trs.append(tr)
pdm.append(up if up>dn and up>0 else 0)
mdm.append(dn if dn>up and dn>0 else 0)
ta = np.mean(trs[-period:])
if ta == 0: return 20.0
pdi = np.mean(pdm[-period:])/ta*100
mdi = np.mean(mdm[-period:])/ta*100
dx = abs(pdi-mdi)/(pdi+mdi)*100 if (pdi+mdi)>0 else 0
return round(float(dx), 2)
def _vol_surge(candles, period=20):
if len(candles) < period: return 1.0
vols = [c["vol"] for c in candles[-period:]]
avg = np.mean(vols[:-1]) if len(vols)>1 else vols[0]
return round(float(vols[-1]/avg), 3) if avg>0 else 1.0
def detect_regime(candles) -> MarketState:
closes = np.array([c["close"] for c in candles])
cur = closes[-1]
e20 = _ema(closes, 20)
e50 = _ema(closes, 50)
e200 = _ema(closes, min(200, len(closes)//2))
adx_v = _adx(candles)
atr_v = _atr(candles)
atr_p = atr_v/cur*100 if cur>0 else 0
vol = _vol_surge(candles)
rsi_v = _rsi(closes)
if adx_v > 28 and e20 > e50 > e200 and cur > e20: regime = Regime.TRENDING_BULL
elif adx_v > 28 and e20 < e50 < e200 and cur < e20: regime = Regime.TRENDING_BEAR
elif atr_p > 4.0: regime = Regime.HIGH_VOLATILITY
else: regime = Regime.RANGING
sent = ("UNCERTAIN" if rsi_v>72 and atr_p>3 else
"BULLISH" if regime==Regime.TRENDING_BULL else
"BEARISH" if regime==Regime.TRENDING_BEAR else "NEUTRAL")
return MarketState(regime=regime, adx=adx_v, atr=atr_v,
atr_pct=round(atr_p,4), vol_surge=vol, sentiment=sent)
# ══════════════════════════════════════════════════════════════
# LAYER 2 — MULTI-STRATEGY ENGINE
# ══════════════════════════════════════════════════════════════
@dataclass
class Signal:
strategy: str
side: str
confidence: float
reasoning: str
indicators: Dict = field(default_factory=dict)
weight_key: str = ""
def strat_trend(candles, ms: MarketState, w=1.0) -> Optional[Signal]:
if ms.regime not in (Regime.TRENDING_BULL, Regime.TRENDING_BEAR): return None
closes = np.array([c["close"] for c in candles])
cur = closes[-1]
e20 = _ema(closes,20); e50 = _ema(closes,50)
e200 = _ema(closes, min(200,len(closes)//2))
m = _macd(closes); r = _rsi(closes); adx = ms.adx
else 0
if ms.regime == Regime.TRENDING_BULL:
if e20>e50>e200 and cur>e20*0.997 and m["histogram"]>0 and 44<r<68 and adx>24:
conf = round(min(96, 50+adx*0.7+(10 if m["histogram"]>0 else 0)+(5 if r>52 return Signal("TREND_FOLLOW","buy",conf,
f"Bull EMA stack EMA20={e20:.2f}>EMA50={e50:.2f}>EMA200={e200:.2f}. "
f"ADX={adx:.1f} strong trend. MACD histogram={m['histogram']:.5f} positive. R
{"ema20":e20,"ema50":e50,"rsi":r,"adx":adx,"macd":m["macd"]}, "trend")
if ms.regime == Regime.TRENDING_BEAR:
if e20<e50<e200 and cur<e20*1.003 and m["histogram"]<0 and 32<r<56 and adx>24:
conf = round(min(94, 50+adx*0.6+10)*w, 1)
return Signal("TREND_FOLLOW","sell",conf,
f"Bear EMA stack EMA20={e20:.2f}<EMA50={e50:.2f}. ADX={adx:.1f}. MACD bearish
{"ema20":e20,"ema50":e50,"rsi":r,"adx":adx}, "trend")
return None
def strat_mean_rev(candles, ms: MarketState, w=1.0) -> Optional[Signal]:
if ms.regime != Regime.RANGING: return None
closes = np.array([c["close"] for c in candles])
cur = closes[-1]; r = _rsi(closes); bb = _bb(closes)
if r < 32 and cur <= bb["lower"]*1.006:
conf = round(min(91, 55+(30-r)+(15 if cur<bb["lower"] else 0))*w, 1)
return Signal("MEAN_REVERSION","buy",conf,
f"Oversold in ranging market. RSI={r} (<32). Price at lower BB={bb['lower']:.4f}.
f"Target mid BB={bb['mid']:.4f}. BB%={bb['pct_b']:.1f}%.",
{"rsi":r,"bb_lower":bb["lower"],"bb_mid":bb["mid"],"pct_b":bb["pct_b"]}, "mean_re
if r > 68 and cur >= bb["upper"]*0.994:
conf = round(min(89, 55+(r-70)+(15 if cur>bb["upper"] else 0))*w, 1)
return Signal("MEAN_REVERSION","sell",conf,
f"Overbought in ranging market. RSI={r} (>68). Price at upper BB={bb['upper']:.4f
{"rsi":r,"bb_upper":bb["upper"],"bb_mid":bb["mid"]}, "mean_rev")
return None
def strat_breakout(candles, ms: MarketState, w=1.0) -> Optional[Signal]:
if len(candles) < 30: return None
lookback = candles[-22:-2]
resistance = max(c["high"] for c in lookback)
support = min(c["low"] for c in lookback)
cur = candles[-1]["close"]
vol = ms.vol_surge; atr = ms.atr
tight = (resistance-support) < atr*13
if cur > resistance*1.001 and vol > 1.4 and tight:
conf = round(min(90, 55+min(20,(vol-1.4)*20)+min(20,(cur/resistance-1)*5000))*w, 1)
return Signal("BREAKOUT","buy",conf,
f"Bullish breakout above {resistance:.4f} resistance. "
f"Volume {vol:.2f}x surge confirms buyers. Consolidation zone tight.",
{"resistance":resistance,"support":support,"vol_surge":vol}, "breakout")
if cur < support*0.999 and vol > 1.4 and tight:
conf = round(min(87, 52+min(20,(vol-1.4)*18))*w, 1)
return Signal("BREAKOUT","sell",conf,
f"Bearish breakdown below {support:.4f} support. Volume {vol:.2f}x confirms selle
{"resistance":resistance,"support":support,"vol_surge":vol}, "breakout")
return None
def select_signal(candles, ms: MarketState, weights: dict) -> Optional[Signal]:
if ms.sentiment == "UNCERTAIN" or ms.atr_pct > 5.5: return None
candidates = [
strat_trend(candles, ms, weights.get("trend", 1.0)),
strat_mean_rev(candles, ms, weights.get("mean_rev",1.0)),
strat_breakout(candles, ms, weights.get("breakout",1.0)),
]
valid = [s for s in candidates if s is not None]
return max(valid, key=lambda s: s.confidence) if valid else None
# ══════════════════════════════════════════════════════════════
# LAYER 3 — RISK MANAGEMENT (CANNOT BE OVERRIDDEN)
# ══════════════════════════════════════════════════════════════
MAX_RISK = 0.05 # 5% per trade
MAX_DD = 0.05 # 5% daily drawdown → halt
MIN_RR = 2.0 # 1:2 minimum reward/risk
MIN_CONF = 70.0 # minimum confidence
MAX_POSITIONS= 3
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
def __init__(self, capital):
self.capital = capital
self.daily_pnl = 0.0
self.halted = False
def reset(self): self.daily_pnl=0.0; self.halted=False
def add_pnl(self, pnl):
self.daily_pnl += pnl
if self.daily_pnl < -self.capital*MAX_DD:
self.halted = True
def evaluate(self, conf, side, price, atr, balance, n_open) -> RiskResult:
def reject(r): return RiskResult(False,r,0,0,0,0,0)
if self.halted: return reject(" if self.daily_pnl < -self.capital*MAX_DD:
HALTED — daily drawdown limit hit")
self.halted=True; return reject(" Max daily drawdown exceeded")
if conf < MIN_CONF: return reject(f"Confidence {conf:.0f}% < {MIN_CONF}% minimum
if n_open >= MAX_POSITIONS: return reject(f"Max {MAX_POSITIONS} positions open")
sl = round(price - atr*SL_MULT, 8) if side=="buy" else round(price + atr*SL_MULT, 8)
tp = round(price + atr*TP_MULT, 8) if side=="buy" else round(price - atr*TP_MULT, 8)
risk = abs(price - sl)
reward = abs(tp - price)
rr = reward/risk if risk>0 else 0
if rr < MIN_RR: return reject(f"R:R={rr:.2f} below minimum {MIN_RR}:1")
risk_amt = balance * MAX_RISK
qty = round(risk_amt/risk, 6) if risk>0 else 0
if qty<=0 or qty*price > balance*0.9: return reject("Insufficient balance")
return RiskResult(True," Approved",qty,round(MAX_RISK*100,2),sl,tp,round(rr,2))
# ══════════════════════════════════════════════════════════════
# LAYER 4+6 — DECISION ENGINE + SELF-IMPROVEMENT
# ══════════════════════════════════════════════════════════════
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
timestamp: str = ""
status: str = "PENDING"
exit_price: float = 0.0
pnl: float = 0.0
exit_reason: str = ""
order_id: str = ""
class SelfLearn:
STEP=0.05; MAX_W=1.7; MIN_W=0.4
def __init__(self): self.weights={"trend":1.0,"mean_rev":1.0,"breakout":1.0}
def update(self, trade: Trade):
k = trade.strategy
wk= {"TREND_FOLLOW":"trend","MEAN_REVERSION":"mean_rev","BREAKOUT":"breakout"}.get(k)
if not wk: return
step = self.STEP + (0.04 if trade.confidence>=85 else 0)
w = self.weights[wk]
self.weights[wk] = round(min(self.MAX_W, w+step) if trade.pnl>0
else max(self.MIN_W, w-step), 3)
class TradeLog:
def __init__(self): self._trades=[]; self._log=[]
def add(self, t: Trade): self._trades.insert(0,t)
def sys(self, msg):
e={"t":time.strftime("%H:%M:%S"),"msg":msg}
self._log.insert(0,e)
if len(self._log)>300: self._log.pop()
print(f"[{e['t']}] {msg}")
@property
def closed(self): return [t for t in self._trades if t.status=="CLOSED"]
@property
def win_rate(self):
c=self.closed; return round(sum(1 for t in c if t.pnl>0)/len(c)*100,1) if c else 0.0
@property
def avg_pnl(self):
c=self.closed; return round(sum(t.pnl for t in c)/len(c),4) if c else 0.0
def get_trades(self, n=50): return [asdict(t) for t in self._trades[:n]]
def get_log(self, n=80): return self._log[:n]
_ID = int(time.time())
def next_id():
global _ID; _ID+=1; return _ID
def make_decision(symbol, signal: Signal, ms: MarketState,
risk: RiskResult, price) -> Trade:
return Trade(
id=next_id(), symbol=symbol, condition=ms.regime.value,
strategy=signal.strategy, side=signal.side.upper(),
entry=round(price,8), sl=risk.sl, tp=risk.tp,
qty=risk.qty, risk_pct=risk.risk_pct, rr=risk.rr,
confidence=signal.confidence, reasoning=signal.reasoning,
indicators=signal.indicators,
timestamp=time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime()),
status="PENDING",
)
# ══════════════════════════════════════════════════════════════
# LAYER 5 — BITGET API CLIENT
# ══════════════════════════════════════════════════════════════
class BitgetClient:
BASE = "https://api.bitget.com"
def __init__(self, api_key, passphrase, private_key_pem):
self.api_key = api_key
self.passphrase = passphrase
self._pkey = None
if private_key_pem.strip():
try:
from cryptography.hazmat.primitives import serialization
self._pkey = serialization.load_pem_private_key(
private_key_pem.encode(), password=None)
except Exception as e:
print(f"Key load warning: {e}")
self._session = None
def _sign(self, ts, method, path, body=""):
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding as apad
msg = f"{ts}{method.upper()}{path}{body}".encode()
sig = self._pkey.sign(msg, apad.PKCS1v15(), hashes.SHA256())
return base64.b64encode(sig).decode()
def _headers(self, method, path, body=""):
ts = str(int(time.time()*1000))
return {
"Content-Type": "application/json",
"ACCESS-KEY": self.api_key,
"ACCESS-SIGN": self._sign(ts, method, path, body) if self._pkey else "ACCESS-TIMESTAMP": ts,
"ACCESS-PASSPHRASE": self.passphrase,
"locale": "en-US",
"demo"
}
async def _get_session(self):
if not self._session or self._session.closed:
self._session = aiohttp.ClientSession()
return self._session
async def get(self, path):
s = await self._get_session()
async with s.get(self.BASE+path, headers=self._headers("GET",path),
timeout=aiohttp.ClientTimeout(total=5)) as r:
return await r.json()
async def post(self, path, body):
s = await self._get_session()
b = json.dumps(body)
hdrs= self._headers("POST", path, b)
async with s.post(self.BASE+path, headers=hdrs, data=b,
timeout=aiohttp.ClientTimeout(total=5)) as r:
return await r.json()
async def get_balance(self):
try:
r = await self.get("/api/v2/spot/account/assets?coin=USDT")
if r.get("code")=="00000" and r.get("data"):
return float(r["data"][0].get("available",0))
except: pass
return 0.0
async def get_candles(self, symbol, limit=200):
try:
path = f"/api/v2/spot/market/candles?symbol={symbol}&granularity=1min&limit={limi
r = await self.get(path)
if r.get("code")=="00000" and r.get("data"):
out = []
for c in reversed(r["data"]):
out.append({"t":int(c[0]),"open":float(c[1]),"high":float(c[2]),
"low":float(c[3]),"close":float(c[4]),"vol":float(c[5])})
return out
except: pass
return []
async def get_price(self, symbol):
try:
r = await self.get(f"/api/v2/spot/market/tickers?symbol={symbol}")
if r.get("code")=="00000" and r.get("data"):
d = r["data"][0]
bid = float(d.get("bidPr",0)); ask = float(d.get("askPr",0))
p = float(d.get("lastPr",0))
return {"price":p,"bid":bid,"ask":ask,
"spread_pct":(ask-bid)/p if p>0 else 0}
except: pass
return {}
async def place_limit_order(self, symbol, side, price, qty):
body = {"symbol":symbol,"side":side,"orderType":"limit",
"force":"gtc","price":str(round(price,8)),"size":str(qty)}
try:
r = await self.post("/api/v2/spot/trade/place-order", body)
if r.get("code")=="00000":
return r.get("data",{}).get("orderId","")
except: pass
return None
async def place_market_order(self, symbol, side, qty):
body = {"symbol":symbol,"side":side,"orderType":"market","force":"gtc","size":str(qty
try:
r = await self.post("/api/v2/spot/trade/place-order", body)
return r.get("code")=="00000"
except: pass
return False
# ══════════════════════════════════════════════════════════════
# DEMO DATA GENERATOR
# ══════════════════════════════════════════════════════════════
BASE_PRICES = {"BTCUSDT":67800.0,"ETHUSDT":3540.0,"SOLUSDT":172.0}
VOL_MAP = {"BTCUSDT":0.006, "ETHUSDT":0.008, "SOLUSDT":0.012}
def gen_candles(symbol, n=200):
p = BASE_PRICES[symbol]; v = VOL_MAP[symbol]; out = []
for _ in range(n):
o = p; p = p*(1+v*random.gauss(0,1)*0.4)
c = p; h = max(o,c)*(1+abs(random.gauss(0,1))*0.001)
l = min(o,c)*(1-abs(random.gauss(0,1))*0.001)
out.append({"t":int(time.time()*1000),"open":o,"high":h,"low":l,"close":c,"vol":50000
return out
def update_candles(candles, symbol):
last = candles[-1]["close"]; v = VOL_MAP[symbol]
new = last*(1+v*random.gauss(0,1)*0.3)
h = max(last,new)*1.0004; l = min(last,new)*0.9996
candles.append({"t":int(time.time()*1000),"open":last,"high":h,"low":l,"close":new,"vol":
if len(candles)>300: candles.pop(0)
return new
# ══════════════════════════════════════════════════════════════
# GLOBAL STATE
# ══════════════════════════════════════════════════════════════
class State:
def __init__(self):
self.running = False
self.balance = CAPITAL
self.positions: List[Trade] = []
self.candles: self.prices: self.regimes: Dict = {}
Dict = {s: gen_candles(s) for s in SYMBOLS}
Dict = {s: {"price": BASE_PRICES[s], "bid":0,"ask":0,"spread_pct":0}
S = State()
risk_mgr = RiskManager(CAPITAL)
learner = SelfLearn()
trade_log = TradeLog()
client = BitgetClient(API_KEY, PASSPHRASE, PRIVATE_KEY) if not DEMO_MODE else None
# ══════════════════════════════════════════════════════════════
# MAIN AGENT LOOP
# ══════════════════════════════════════════════════════════════
async def tick_demo():
"""Update simulated prices in demo mode."""
while S.running:
for sym in SYMBOLS:
new_p = update_candles(S.candles[sym], sym)
spread = new_p * 0.0002
S.prices[sym] = {"price":new_p, "bid":new_p-spread,
"ask":new_p+spread, "spread_pct":0.0002}
await asyncio.sleep(2)
async def check_positions():
"""Monitor open positions for SL/TP."""
for pos in list(S.positions):
cur = S.prices.get(pos.symbol,{}).get("price", pos.entry)
if cur == 0: continue
hit_sl = (pos.side=="BUY" and cur<=pos.sl) or (pos.side=="SELL" and cur>=pos.sl)
hit_tp = (pos.side=="BUY" and cur>=pos.tp) or (pos.side=="SELL" and cur<=pos.tp)
if hit_sl or hit_tp:
reason = "TAKE_PROFIT" if hit_tp else "STOP_LOSS"
pnl = (cur-pos.entry)*pos.qty if pos.side=="BUY" else (pos.entry-cur)*pos.qty
pos.pnl=round(pnl,4); pos.exit_price=cur; pos.exit_reason=reason; pos.status="CLO
risk_mgr.add_pnl(pnl)
learner.update(pos)
S.balance += pos.qty*cur
S.positions = [p for p in S.positions if p.id!=pos.id]
emoji = " " if pnl>0 else " "
trade_log.sys(f"{emoji} CLOSED {pos.symbol} {pos.side} @ {cur:.4f} | "
f"PnL=${pnl:+.2f} | {reason} | Strategy={pos.strategy}")
# Real close order
if client:
close_side = "sell" if pos.side=="BUY" else "buy"
await client.place_market_order(pos.symbol, close_side, pos.qty)
async def run_analysis():
"""Core strategy cycle."""
for sym in SYMBOLS:
if not S.running or risk_mgr.halted: break
if len(S.positions) >= MAX_POSITIONS: break
candles = S.candles.get(sym,[])
if len(candles) < 50: continue
# Live data
if client:
live = await client.get_candles(sym)
if live: S.candles[sym] = live; candles = live
tick = await client.get_price(sym)
if tick: S.prices[sym] = tick
cur = S.prices[sym].get("price", candles[-1]["close"])
ms = detect_regime(candles)
S.regimes[sym] = ms
sig = select_signal(candles, ms, learner.weights)
if not sig: continue
rp = risk_mgr.evaluate(sig.confidence, sig.side, cur,
ms.atr, S.balance, len(S.positions))
if not rp.approved:
trade_log.sys(f"[REJECT] {sym}: {rp.reason}"); continue
trade = make_decision(sym, sig, ms, rp, cur)
trade_log.sys(f" SIGNAL: {sym} {trade.side} @ {cur:.4f} | "
f"SL={rp.sl:.4f} TP={rp.tp:.4f} | "
f"Conf={sig.confidence:.0f}% | {sig.strategy}")
# Execute
order_id = None
if client:
order_id = await client.place_limit_order(sym, sig.side, cur, rp.qty)
if not order_id:
trade_log.sys(f"[EXEC FAIL] {sym} order rejected"); continue
trade.order_id = order_id or "DEMO"
trade.status = "OPEN"
S.balance -= rp.qty * cur
S.positions.append(trade)
trade_log.add(trade)
break # one new trade per cycle
async def agent_loop():
trade_log.sys(" JD TRADER STARTED" + (" [DEMO MODE]" if DEMO_MODE else " [LIVE]"))
demo_task = asyncio.create_task(tick_demo()) if DEMO_MODE else None
while S.running:
try:
await check_positions()
await run_analysis()
except Exception as e:
trade_log.sys(f"Loop error: {e}")
await asyncio.sleep(CYCLE_SECS)
if demo_task: demo_task.cancel()
# ══════════════════════════════════════════════════════════════
# FASTAPI — REST API + FULL DASHBOARD UI
# ══════════════════════════════════════════════════════════════
app = FastAPI(title="JD Trader")
app.add_middleware(CORSMiddleware, allow_origins=["*"],
allow_methods=["*"], allow_headers=["*"])
loop_task = None
@app.post("/agent/start")
async def start():
global loop_task
if S.running: return {"ok":True,"msg":"Already running"}
S.running = True; risk_mgr.reset()
loop_task = asyncio.create_task(agent_loop())
return {"ok":True}
@app.post("/agent/stop")
async def stop():
S.running = False
if loop_task: loop_task.cancel()
trade_log.sys(" Agent stopped"); return {"ok":True}
@app.post("/agent/reset")
async def reset():
risk_mgr.reset(); trade_log.sys(" Reset — daily limits cleared"); return {"ok":True}
@app.get("/state")
async def state():
if client:
bal = await client.get_balance()
if bal>0: S.balance = bal
closed = trade_log.closed
wins = sum(1 for t in closed if t.pnl>0)
return {
"balance": round(S.balance,4),
"initialCapital": CAPITAL,
"running": S.running,
"halted": risk_mgr.halted,
"dailyPnl": round(risk_mgr.daily_pnl,4),
"demo": DEMO_MODE,
"openPositions": [asdict(p) for p in S.positions],
"trades": trade_log.get_trades(50),
"log": trade_log.get_log(80),
"weights": learner.weights,
"regime": {s:(ms.regime.value if ms else "RANGING")
for s,ms in S.regimes.items()},
"stats":{"total":len(closed),"wins":wins,"losses":len(closed)-wins,
"winRate":trade_log.win_rate,"avgPnl":trade_log.avg_pnl},
"prices":{s:{"price":round(d.get("price",0),4)} for s,d in S.prices.items()},
}
@app.get("/health")
async def health(): return {"ok":True,"mode":"DEMO" if DEMO_MODE else "LIVE"}
# ══════════════════════════════════════════════════════════════
# BUILT-IN DASHBOARD (opens at your Replit URL)
# ══════════════════════════════════════════════════════════════
DASHBOARD_HTML = """<!DOCTYPE html>
<html><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>JD TRADER</title>
<link href="https://fonts.googleapis.com/css2?family=Rajdhani:wght@600;700&family=JetBrains+M
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{background:#060a0f;color:#8899aa;font-family:'Rajdhani',sans-serif;font-size:15px}
.mono{font-family:'JetBrains Mono',monospace}
header{display:flex;align-items:center;justify-content:space-between;
padding:14px 20px;border-bottom:1px solid #0f1822}
.logo{font-size:22px;font-weight:700;color:#ccd5de}
.logo span{color:#39ff90}
.badge{font-size:10px;background:#0a0e14;border:1px solid #1a2535;
border-radius:4px;padding:2px 8px;color:#3a4a5c;font-family:'JetBrains Mono',monospace}
.regime-badge{padding:4px 12px;border-radius:20px;font-size:11px;font-weight:700;letter-spaci
.btn{border:none;cursor:pointer;border-radius:6px;padding:9px 22px;
font-family:'Rajdhani',sans-serif;font-weight:700;font-size:13px;letter-spacing:.06em}
.btn-live{background:#39ff9015;border:1px solid #39ff9050;color:#39ff90}
.btn-halt{background:#ff3b5c15;border:1px solid #ff3b5c50;color:#ff3b5c}
.btn-reset{background:#f0c04015;border:1px solid #f0c04050;color:#f0c040}
.grid6{display:grid;grid-template-columns:repeat(6,1fr);gap:10px;padding:16px 20px}
.grid2{display:grid;grid-template-columns:1fr 320px;gap:14px;padding:0 20px 20px}
@media(max-width:700px){.grid6{grid-template-columns:repeat(2,1fr)}.grid2{grid-template-colum
.card{background:#0a0e14;border:1px solid #1a2535;border-radius:8px;padding:14px 16px}
.card-label{font-size:10px;color:#3a4a5c;letter-spacing:.12em;font-weight:700;
text-transform:uppercase;margin-bottom:5px}
.card-value{font-family:'JetBrains Mono',monospace;font-size:20px;font-weight:700}
.card-sub{font-size:11px;color:#3a4a5c;margin-top:2px}
.section-title{font-size:11px;color:#3a4a5c;font-weight:700;letter-spacing:.12em;margin-botto
.pos{padding:9px 0;border-bottom:1px solid #0f1822}
.pos-sym{font-weight:700;color:#ccd5de}
.pos-side-buy{color:#39ff90}.pos-side-sell{color:#ff3b5c}
.pos-details{font-family:'JetBrains Mono',monospace;font-size:11px;color:#4a5a6a;margin-top:3
.sig{background:#060a0f;border-radius:7px;padding:12px;margin-bottom:8px;
animation:slideUp .25s ease}
.sig-head{display:flex;justify-content:space-between;align-items:center;margin-bottom:8px}
.sig-strat{font-weight:700;font-size:13px}
.sig-conf{font-family:'JetBrains Mono',monospace;font-size:13px;font-weight:700;
border-radius:4px;padding:2px 8px}
.sig-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:6px;margin-bottom:8px}
.sig-cell{background:#0a0e14;border-radius:5px;padding:5px 8px}
.sig-cell-label{font-size:9px;color:#2d3d50;letter-spacing:.1em;font-weight:700}
.sig-cell-val{font-family:'JetBrains Mono',monospace;font-size:12px;font-weight:700}
.sig-reason{font-size:11px;color:#4a5a6a;line-height:1.5;
border-top:1px solid #0f1822;padding-top:7px}
.trade-row{display:grid;grid-template-columns:60px 80px 50px 85px 70px 1fr;
gap:8px;padding:7px 0;border-bottom:1px solid #0a0e14;font-size:12px;align-items:center;
animation:slideUp .25s ease}
.log-row{font-family:'JetBrains Mono',monospace;font-size:11px;color:#4a5a6a;
padding:4px 0;border-bottom:1px solid #0a0e14}
.log-time{color:#2d3d50;margin-right:8px}
.tabs{display:flex;border-bottom:1px solid #0f1822;padding:0 16px}
.tab{background:none;border:none;cursor:pointer;padding:8px 14px;
font-family:'Rajdhani',sans-serif;font-weight:700;font-size:12px;
letter-spacing:.1em;text-transform:uppercase;border-bottom:2px solid transparent;color:#2d3
.tab.on{color:#39ff90;border-bottom-color:#39ff90}
.scroll{max-height:320px;overflow-y:auto;padding:12px 16px}
.empty{color:#1a2535;text-align:center;padding:28px 0;font-size:13px}
.wbar{height:3px;background:#0f1822;border-radius:2px;margin-top:5px}
.wbar-fill{height:100%;border-radius:2px;opacity:.75;transition:width .5s ease}
.price-row{display:flex;justify-content:space-between;padding:6px 0;
border-bottom:1px solid #0f1822;font-size:12px}
.pnl-bar{height:4px;background:#0f1822;border-radius:2px;margin-top:10px}
.pnl-fill{height:100%;border-radius:2px;transition:width .5s ease}
.dot{display:inline-block;width:7px;height:7px;border-radius:50%;margin-right:6px;
animation:pulse 1.2s ease-in-out infinite}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.3}}
@keyframes slideUp{from{opacity:0;transform:translateY(5px)}to{opacity:1;transform:translateY
::-webkit-scrollbar{width:3px}
::-webkit-scrollbar-thumb{background:#1a2535;border-radius:2px}
.demo-banner{background:#f0c04010;border-bottom:1px solid #f0c04030;
padding:8px 20px;font-size:12px;color:#f0c040;text-align:center}
</style>
</head>
<body>
<div id="demo-banner" style="display:none" class="demo-banner">
⚠ DEMO MODE — No API keys set. All trades are simulated. Add your Bitget keys in Replit Sec
</div>
<header>
<div style="display:flex;align-items:center;gap:12px">
<div style="width:38px;height:38px;border-radius:8px;background:#39ff9012;
border:1px solid #39ff9030;display:flex;align-items:center;justify-content:center;font-
<div>
<div class="logo">JD <span>TRADER</span> <span class="badge">QUANT v3</span></div>
<div style="font-size:10px;color:#2d3d50;letter-spacing:.15em">INSTITUTIONAL · BITGET A
</div>
</div>
<div style="display:flex;gap:10px;align-items:center">
<div id="regime-badge" class="regime-badge" style="background:#f0c04010;border:1px <button class="btn btn-reset" onclick="agentAction('reset')">↺ RESET</button>
<button id="main-btn" class="btn btn-live" onclick="toggleAgent()">▶ GO LIVE</button>
</div>
</header>
solid
<!-- Stats -->
<div class="grid6" id="stats-row">
<div class="card"><div class="card-label">Equity</div><div class="card-value" id="s-eq" sty
<div class="card"><div class="card-label">Total P&L</div><div class="card-value" id="s-pnl"
<div class="card"><div class="card-label">Daily P&L</div><div class="card-value" id="s-dail
<div class="card"><div class="card-label">Win Rate</div><div class="card-value" id="s-wr" s
<div class="card"><div class="card-label">Avg P&L</div><div class="card-value" id="s-avg">—
<div class="card"><div class="card-label">Trades</div><div class="card-value" id="s-cnt" st
</div>
<!-- Body -->
<div class="grid2">
<!-- Left -->
<div style="display:flex;flex-direction:column;gap:14px">
<!-- Prices -->
<div style="display:grid;grid-template-columns:repeat(3,1fr);gap:10px">
<div class="card" id="p-BTCUSDT"><div class="card-label">BTC/USDT</div><div class="card
<div class="card" id="p-ETHUSDT"><div class="card-label">ETH/USDT</div><div class="card
<div class="card" id="p-SOLUSDT"><div class="card-label">SOL/USDT</div><div class="card
</div>
<!-- Tabs -->
<div class="card" style="padding:0;overflow:hidden">
<div class="tabs">
<button class="tab on" onclick="setTab('signals',this)">Signals</button>
<button class="tab" onclick="setTab('trades',this)">Trades</button>
<button class="tab" onclick="setTab('log',this)">Log</button>
</div>
<div class="scroll" id="tab-signals"></div>
<div class="scroll" id="tab-trades" style="display:none"></div>
<div class="scroll" id="tab-log" style="display:none"></div>
</div>
</div>
<!-- Right -->
<div style="display:flex;flex-direction:column;gap:14px">
<!-- Open Positions -->
<div class="card">
<div class="section-title">OPEN POSITIONS (<span id="pos-count">0</span>/3)</div>
<div id="positions-list"><div class="empty">No open positions</div></div>
</div>
<!-- Strategy Weights -->
<div class="card">
<div class="section-title">SELF-LEARNING WEIGHTS</div>
<div id="weights-panel"></div>
<div style="font-size:10px;color:#2d3d50;margin-top:8px">Auto-adjusts ±0.05× after each
</div>
<!-- Risk -->
<div class="card">
<div class="section-title">RISK PARAMETERS</div>
<div class="price-row"><span style="color:#4a5a6a">Risk per trade</span><span class="mo
<div class="price-row"><span style="color:#4a5a6a">Min R:R ratio</span><span class="mon
<div class="price-row"><span style="color:#4a5a6a">Min confidence</span><span class="mo
<div class="price-row"><span style="color:#4a5a6a">Max daily loss</span><span class="mo
<div class="price-row"><span style="color:#4a5a6a">Max positions</span><span class="mon
<div class="price-row"><span style="color:#4a5a6a">Order type</span><span class="mono"
</div>
<!-- Capital -->
<div class="card">
<div class="section-title">CAPITAL</div>
<div class="price-row"><span style="color:#4a5a6a">Initial</span><span class="mono" id=
<div class="price-row"><span style="color:#4a5a6a">Available</span><span class="mono" i
<div class="price-row"><span style="color:#4a5a6a">In Trades</span><span class="mono" i
<div class="price-row"><span style="color:#4a5a6a">Daily P&L</span><span class="mono" i
<div class="pnl-bar"><div id="pnl-fill" class="pnl-fill" style="width:50%;background:li
</div>
</div>
</div>
<div style="padding:8px 20px 20px">
<div style="background:#0a0e1480;border:1px solid #1a2535;border-radius:6px;
font-family:'JetBrains Mono',monospace;font-size:10px;color:#2d3d50;padding:8px 14px">
⚠ LIVE TRADING RISK — Crypto involves substantial risk of loss. Never trade more than you
</div>
</div>
<script>
let isRunning=false, activeTab='signals', st={};
const REGIME_COLORS={TRENDING_BULL:'#39ff90',TRENDING_BEAR:'#ff3b5c',RANGING:'#f0c040',HIGH_V
const STRAT_COLORS ={TREND_FOLLOW:'#39ff90',MEAN_REVERSION:'#7b61ff',BREAKOUT:'#ff8c42'};
function clr(n){return n>=0?'#39ff90':'#ff3b5c'}
function sign(n){return(n>=0?'+':'')+Number(n).toFixed(2)}
function fmt(n,d=2){return Number(n).toFixed(d)}
function fmtK(n){return n>=1000?'$'+(n/1000).toFixed(2)+'k':'$'+fmt(n)}
async function poll(){
try{
const r=await fetch('/state'); st=await r.json();
render();
}catch(e){}
}
function render(){
// Demo banner
document.getElementById('demo-banner').style.display=st.demo?'block':'none';
// Stats
const bal=st.balance||0, cap=st.initialCapital||500;
const pnl=bal-cap, pct=pnl/cap*100;
document.getElementById('s-eq').textContent=fmtK(bal);
const pnlEl=document.getElementById('s-pnl'); pnlEl.textContent=sign(pnl)+'';
pnlEl.style.color=clr(pnl);
const pctEl=document.getElementById('s-pnl-pct'); pctEl.textContent=(pct>=0?'+':'')+fmt(pct
const dp=st.dailyPnl||0; const dEl=document.getElementById('s-daily');
dEl.textContent=sign(dp); dEl.style.color=clr(dp);
const stats=st.stats||{};
const wrEl=document.getElementById('s-wr');
wrEl.textContent=stats.total?stats.winRate+'%':'—';
wrEl.style.color=stats.winRate>=50?'#39ff90':'#ff3b5c';
const avgEl=document.getElementById('s-avg');
avgEl.textContent=stats.total?'$'+fmt(stats.avgPnl):'—';
avgEl.style.color=stats.avgPnl>=0?'#39ff90':'#ff3b5c';
document.getElementById('s-cnt').textContent=stats.total||0;
// Prices
for(const[sym,d] of Object.entries(st.prices||{})){
const el=document.getElementById('p-'+sym);
if(el) el.querySelector('.card-value').textContent=
d.price>0?d.price.toLocaleString(undefined,{minimumFractionDigits:2,maximumFractionDigi
}
// Regime
const regimes=st.regime||{};
const mainRegime=Object.values(regimes)[0]||'RANGING';
const rb=document.getElementById('regime-badge');
const rc=REGIME_COLORS[mainRegime]||'#f0c040';
rb.textContent=mainRegime.replace('_',' ');
rb.style.color=rc; rb.style.borderColor=rc+'40'; rb.style.background=rc+'10';
// Button
const btn=document.getElementById('main-btn');
isRunning=st.running||false;
if(st.halted){
btn.className='btn btn-reset'; btn.textContent=' HALTED';
}else if(isRunning){
btn.className='btn btn-halt'; btn.innerHTML='<span class="dot" style="background:#ff3b5c;
}else{
btn.className='btn btn-live'; btn.textContent='▶ GO LIVE';
}
// Positions
const posEl=document.getElementById('positions-list');
const positions=st.openPositions||[];
document.getElementById('pos-count').textContent=positions.length;
if(!positions.length){posEl.innerHTML='<div class="empty">No open positions</div>';}
else posEl.innerHTML=positions.map(p=>`
<div class="pos">
<div style="display:flex;justify-content:space-between">
<span class="pos-sym">${p.symbol}</span>
<span class="pos-side-${p.side.toLowerCase()}" style="font-weight:700">${p.side}</spa
</div>
<div class="pos-details">
Entry: ${fmt(p.entry,4)} &nbsp;|&nbsp;
SL: <span style="color:#ff3b5c">${fmt(p.sl,4)}</span> &nbsp;|&nbsp;
TP: <span style="color:#39ff90">${fmt(p.tp,4)}</span>
</div>
<div class="pos-details" style="margin-top:2px">
Conf: ${p.confidence}% &nbsp;|&nbsp; ${p.strategy}
</div>
</div>`).join('');
// Weights
const w=st.weights||{trend:1,mean_rev:1,breakout:1};
const wLabels={trend:'TREND FOLLOW',mean_rev:'MEAN REVERSION',breakout:'BREAKOUT'};
const wColors={trend:'#39ff90',mean_rev:'#7b61ff',breakout:'#ff8c42'};
document.getElementById('weights-panel').innerHTML=
Object.entries(w).map(([k,v])=>`
<div style="margin-bottom:10px">
<div style="display:flex;justify-content:space-between;font-size:12px;margin-bottom:5
<span style="color:#4a5a6a">${wLabels[k]||k}</span>
<span class="mono" style="color:${wColors[k]};font-weight:700">${Number(v).toFixed(
</div>
<div class="wbar"><div class="wbar-fill" style="width:${Math.min(100,v/1.7*100)}%;bac
</div>`).join('');
// Capital
document.getElementById('c-init').textContent=fmtK(cap);
document.getElementById('c-avail').textContent=fmtK(bal);
document.getElementById('c-locked').textContent=fmtK(
positions.reduce((s,p)=>(s+p.qty*(p.entry||0)),0));
const cdEl=document.getElementById('c-daily'); cdEl.textContent=sign(dp); cdEl.style.color=
document.getElementById('pnl-fill').style.width=Math.min(100,Math.max(0,50+pct))+'%';
document.getElementById('pnl-fill').style.background=
pnl>=0?'linear-gradient(90deg,#39ff90,#7b61ff)':'linear-gradient(90deg,#ff3b5c,#ff8c42)';
// Tabs
renderSignals(); renderTrades(); renderLog();
}
function renderSignals(){
const el=document.getElementById('tab-signals');
const trades=st.trades||[];
const open=st.openPositions||[];
const sigs=[...open.filter(p=>p.status==='OPEN'), ...trades.filter(t=>t.status==='PENDING')
if(!sigs.length){el.innerHTML='<div class="empty">No signals yet — press GO LIVE</div>';ret
el.innerHTML=sigs.map(s=>{
const sc=STRAT_COLORS[s.strategy]||'#39ff90';
const side_c=s.side==='BUY'?'#39ff90':'#ff3b5c';
const conf_c=s.confidence>=85?'#39ff90':s.confidence>=70?'#f0c040':'#ff3b5c';
return`<div class="sig" style="border:1px solid ${sc}25">
<div class="sig-head">
<div style="display:flex;gap:8px;align-items:center">
<span class="sig-strat" style="color:${sc}">${s.strategy.replace('_',' ')}</span>
<span class="mono" style="color:${side_c};font-size:11px;font-weight:700">${s.side}
<span class="mono" style="color:#4a5a6a;font-size:11px">${s.symbol}</span>
</div>
<div class="sig-conf" style="color:${conf_c};background:${conf_c}15;border:1px </div>
<div class="sig-grid">
${[['Entry',fmt(s.entry,4),'#ccd5de'],['Stop Loss',fmt(s.sl,4),'#ff3b5c'],
['Take Profit',fmt(s.tp,4),'#39ff90'],['Risk %',s.risk_pct+'%','#f0c040'],
['R:R','1:'+s.rr,'#7b61ff'],['Strategy',s.strategy.split('_')[0],'#4a5a6a']]
.map(([l,v,c])=>`<div class="sig-cell">
<div class="sig-cell-label">${l}</div>
<div class="sig-cell-val" style="color:${c}">${v}</div>
</div>`).join('')}
</div>
<div class="sig-reason">${s.reasoning||''}</div>
</div>`;}).join('');
solid
}
function renderTrades(){
const el=document.getElementById('tab-trades');
const trades=(st.trades||[]).filter(t=>t.status==='CLOSED');
if(!trades.length){el.innerHTML='<div class="empty">No closed trades yet</div>';return;}
el.innerHTML=trades.map(t=>`
<div class="trade-row">
<span class="mono" style="color:#2d3d50;font-size:10px">${t.timestamp?t.timestamp.subst
<span class="mono" style="color:#4a5a6a;font-size:11px">${t.symbol}</span>
<span style="color:${t.side==='BUY'?'#39ff90':'#ff3b5c'};font-weight:700;font-size:11px
<span style="font-size:10px;color:#4a5a6a">${t.strategy.split('_')[0]}</span>
<span class="mono" style="color:${clr(t.pnl)};font-weight:700">${t.pnl>=0?'+':''}$${fmt
<span style="font-size:10px;font-weight:700;color:${t.pnl>0?'#39ff9060':'#ff3b5c60'}">$
</div>`).join('');
}
function renderLog(){
const el=document.getElementById('tab-log');
const logs=st.log||[];
if(!logs.length){el.innerHTML='<div class="empty">Log empty</div>';return;}
el.innerHTML=logs.map(l=>`<div class="log-row"><span class="log-time">${l.t}</span>${l.msg}
}
function setTab(name, btn){
activeTab=name;
['signals','trades','log'].forEach(t=>{
document.getElementById('tab-'+t).style.display=t===name?'block':'none';
});
document.querySelectorAll('.tab').forEach(b=>b.classList.remove('on'));
btn.classList.add('on');
}
async function toggleAgent(){
if(st.halted){await agentAction('reset');return;}
await agentAction(isRunning?'stop':'start');
}
async function agentAction(action){
await fetch('/agent/'+action,{method:'POST'});
setTimeout(poll,500);
}
poll();
setInterval(poll,3000);
</script>
</body></html>"""
@app.get("/", response_class=HTMLResponse)
async def dashboard(): return DASHBOARD_HTML
# ══════════════════════════════════════════════════════════════
# START
# ══════════════════════════════════════════════════════════════
if __name__ == "__main__":
import uvicorn
port = int(os.getenv("PORT", 8000))
print(f"""
╔══════════════════════════════════════════════╗
║ JD TRADER — STARTING UP ║
║ Mode: {'DEMO (no API keys)' if DEMO_MODE else 'LIVE (Bitget connected)'}
║ Open your Replit URL to see dashboard ║
╚══════════════════════════════════════════════╝
""")
uvicorn.run(app, host="0.0.0.0", port=port)
