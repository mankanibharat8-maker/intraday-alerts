import os, io, json, requests
import numpy as np, pandas as pd, yfinance as yf
from datetime import datetime
from zoneinfo import ZoneInfo
from urllib.parse import quote

TOKEN = os.environ["TG_TOKEN"].strip()
CHAT_ID = os.environ["TG_CHAT_ID"].strip()
FORCE = os.environ.get("FORCE", "no") == "yes"
LABEL = "Intraday 5min"
STATE = "state/seen.json"
LIST_FILE = "nifty500.csv"
LIST_URL = "https://nsearchives.nseindia.com/content/indices/ind_nifty500list.csv"

now = datetime.now(ZoneInfo("Asia/Kolkata"))
mins = now.hour * 60 + now.minute
in_hours = now.weekday() < 5 and (9 * 60 + 20) <= mins <= (15 * 60 + 25)
if not in_hours and not FORCE:
    raise SystemExit

def send(msg):
    r = requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage",
                      data={"chat_id": CHAT_ID, "text": msg,
                            "disable_web_page_preview": True})
    print("TELEGRAM:", r.status_code)

def load_symbols():
    try:
        r = requests.get(LIST_URL, headers={"User-Agent": "Mozilla/5.0"}, timeout=20)
        r.raise_for_status()
        df = pd.read_csv(io.StringIO(r.text))
        df.to_csv(LIST_FILE, index=False)
        print("Nifty500 list downloaded")
    except Exception as e:
        print("list download failed:", e)
        if not os.path.exists(LIST_FILE):
            send(f"⚠️ {LABEL}: Nifty 500 list not available. Upload nifty500.csv to the repo.")
            raise SystemExit(1)
        df = pd.read_csv(LIST_FILE)
        print("using saved list")
    return [s.strip() for s in df["Symbol"].dropna().tolist()]

def rma(s, n):
    return s.ewm(alpha=1.0 / n, adjust=False).mean()

def supertrend(df, period, mult):
    """returns (is_up, supertrend_level)"""
    h, l, c = df["High"].values, df["Low"].values, df["Close"].values
    n = len(df)
    pc = np.roll(c, 1)
    pc[0] = c[0]
    tr = np.maximum(h - l, np.maximum(abs(h - pc), abs(l - pc)))
    atr = rma(pd.Series(tr), period).values
    up = np.zeros(n); lo = np.zeros(n); d = np.ones(n)
    for i in range(n):
        hl2 = (h[i] + l[i]) / 2
        bu = hl2 + mult * atr[i]
        bl = hl2 - mult * atr[i]
        if i == 0:
            up[i], lo[i] = bu, bl
            continue
        lo[i] = bl if (bl > lo[i-1] or c[i-1] < lo[i-1]) else lo[i-1]
        up[i] = bu if (bu < up[i-1] or c[i-1] > up[i-1]) else up[i-1]
        if d[i-1] == -1:
            d[i] = 1 if c[i] > up[i] else -1
        else:
            d[i] = -1 if c[i] < lo[i] else 1
    is_up = d[-1] == 1
    return bool(is_up), float(lo[-1] if is_up else up[-1])

def rsi(close, n=14):
    delta = close.diff()
    gain = rma(delta.clip(lower=0), n)
    loss = rma((-delta).clip(lower=0), n)
    rs = gain / loss.replace(0, np.nan)
    return 100 - 100 / (1 + rs)

def index_status(sym):
    """daily Supertrend(10, 1.5) of an index. returns (is_green, close, level) or None"""
    try:
        df = yf.Ticker(sym).history(period="1y", auto_adjust=False)
        df = df.dropna(subset=["Close", "High", "Low"])
        if len(df) < 30:
            return None
        up, lvl = supertrend(df, 10, 1.5)
        return up, float(df["Close"].iloc[-1]), lvl
    except Exception as e:
        print("index error", sym, e)
        return None

def check(df):
    df = df.dropna(subset=["Close", "High", "Low"])
    if len(df) < 60:
        return None
    if now < df.index[-1] +
