import os, json, requests
import numpy as np, pandas as pd, yfinance as yf
from datetime import datetime
from zoneinfo import ZoneInfo
from urllib.parse import quote

TOKEN = os.environ["TG_TOKEN"].strip()
CHAT_ID = os.environ["TG_CHAT_ID"].strip()
FORCE = os.environ.get("FORCE", "no") == "yes"
LABEL = "Intraday 5min"
STATE = "state/seen.json"

SYMBOLS = """RELIANCE TCS INFY HDFCBANK ICICIBANK SBIN AXISBANK KOTAKBANK LT ITC
HINDUNILVR BHARTIARTL MARUTI SUNPHARMA TITAN ULTRACEMCO ASIANPAINT BAJFINANCE
BAJAJFINSV NTPC POWERGRID ONGC COALINDIA TATASTEEL JSWSTEEL HINDALCO VEDL
ADANIENT ADANIPORTS WIPRO HCLTECH TECHM LTIM NESTLEIND BRITANNIA DIVISLAB
DRREDDY CIPLA APOLLOHOSP EICHERMOT HEROMOTOCO BAJAJ-AUTO M&M GRASIM INDUSINDBK
BPCL IOC GAIL TATAPOWER DLF SIEMENS HAL BEL BHEL PNB BANKBARODA CANBK
FEDERALBNK IDFCFIRSTB AUBANK SBILIFE HDFCLIFE ICICIGI ICICIPRULI CHOLAFIN
MUTHOOTFIN PFC RECLTD IRCTC INDIGO TRENT PIDILITIND GODREJCP DABUR MARICO
COLPAL HAVELLS VOLTAS CUMMINSIND ABB AMBUJACEM SHREECEM BIOCON FORTIS
JUBLFOOD LUPIN AUROPHARMA ZYDUSLIFE TORNTPHARM ALKEM GLENMARK PERSISTENT
COFORGE MPHASIS OFSS NAUKRI TVSMOTOR ASHOKLEY BALKRISHIND MRF BOSCHLTD
MOTHERSON APOLLOTYRE TATACONSUM UPL PIIND SRF DEEPAKNTR NAVINFLUOR TATACHEM
PETRONET IGL MGL LICHSGFIN MANAPPURAM SHRIRAMFIN SAIL NMDC JINDALSTEL
NATIONALUM HINDPETRO OIL CONCOR LAURUSLABS ABCAPITAL DIXON KPITTECH
TATAELXSI CROMPTON BANDHANBNK RBLBANK IEX""".split()

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

def rma(s, n):
    return s.ewm(alpha=1.0 / n, adjust=False).mean()

def supertrend_up(df, period=20, mult=2.0):
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
    return d[-1] == 1

def rsi(close, n=14):
    delta = close.diff()
    gain = rma(delta.clip(lower=0), n)
    loss = rma((-delta).clip(lower=0), n)
    rs = gain / loss.replace(0, np.nan)
    return 100 - 100 / (1 + rs)

def check(df):
    df = df.dropna(subset=["Close", "High", "Low"])
    if len(df) < 60:
        return None
    if now < df.index[-1] + pd.Timedelta(minutes=5):
        df = df.iloc[:-1]  # drop candle still forming
    dates = np.array(df.index.date)
    today_d = dates[-1]
    prev_dates = sorted(set(dates[dates < today_d]))
    if not prev_dates:
        return None
    p = df[dates == prev_dates[-1]]
    ph, pl, pcl = p["High"].max(), p["Low"].min(), p["Close"].iloc[-1]
    pivot = (ph + pl + pcl) / 3
    r1 = 2 * pivot - pl
    c = df["Close"]
    sma = c.rolling(20).mean()
    std = c.rolling(20).std(ddof=0)
    upper = (sma + 2 * std).iloc[-1]
    last = c.iloc[-1]
    rsi_v = rsi(c).iloc[-1]
    ok = (supertrend_up(df) and rsi_v > 70 and last > upper and last > r1)
    return ok, float(last), float(rsi_v)

today = now.strftime("%Y-%m-%d")
seen = set()
if os.path.exists(STATE):
    try:
        st = json.load(open(STATE))
        if st.get("date") == today:
            seen = set(st.get("seen", []))
    except Exception:
        pass

tickers = [s + ".NS" for s in SYMBOLS]
data = yf.download(tickers, period="5d", interval="5m", group_by="ticker",
                   auto_adjust=False, progress=False, threads=True)

hits, failed = [], 0
for s in SYMBOLS:
    try:
        res = check(data[s + ".NS"].copy())
        if res is None:
            failed += 1
        elif res[0]:
            hits.append((s, res[1], res[2]))
    except Exception:
        failed += 1
print(f"scanned {len(SYMBOLS)}, failed {failed}, matched {len(hits)}")

new = [h for h in hits if h[0] not in seen]
if new:
    blocks = []
    for s, price, r in new:
        tv = f"https://in.tradingview.com/chart/?symbol=NSE:{quote(s)}"
        blocks.append(f"{s}: ₹{price:.2f} RSI {r:.0f}\nTradingView: {tv}")
        seen.add(s)
    send(f"⚡ {LABEL} {now.strftime('%H:%M')}\n\n" + "\n\n".join(blocks))
    os.makedirs("state", exist_ok=True)
    json.dump({"date": today, "seen": sorted(seen)}, open(STATE, "w"))
elif FORCE:
    send(f"⚡ {LABEL}: test OK, scanned {len(SYMBOLS)}, failed {failed}, "
         f"matched {len(hits)}, new 0")
