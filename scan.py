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
    st_up, _ = supertrend(df, 20, 2.0)
    ok = bool(st_up and rsi_v > 70 and last > upper and last > r1)
    return ok, float(last), float(rsi_v)

# ---------- state ----------
today = now.strftime("%Y-%m-%d")
active, prev_regime = set(), None
if os.path.exists(STATE):
    try:
        st = json.load(open(STATE))
        if st.get("date") == today:
            active = set(st.get("active", st.get("seen", [])))
            prev_regime = st.get("regime")
    except Exception:
        pass

def save_state(act, regime):
    os.makedirs("state", exist_ok=True)
    json.dump({"date": today, "active": sorted(act), "regime": regime},
              open(STATE, "w"))

# ---------- index filter: Nifty 50 and Nifty 500 above Supertrend(10, 1.5) ----------
n50 = index_status("^NSEI")
n500 = index_status("^CRSLDX")

def fmt(name, s):
    if s is None:
        return f"{name}: data unavailable"
    sign = ">" if s[0] else "<"
    return f"{name} {s[1]:.0f} {sign} Supertrend {s[2]:.0f}"

status_line = fmt("Nifty50", n50) + "\n" + fmt("Nifty500", n500)
known = [s for s in (n50, n500) if s is not None]
any_red = any(not s[0] for s in known)
all_green = len(known) == 2 and all(s[0] for s in known)

if any_red:
    regime = "red"
elif all_green:
    regime = "green"
else:
    regime = "unknown"
print("REGIME:", regime, "| prev:", prev_regime)

if regime == "red":
    if prev_regime != "red" or FORCE:
        send(f"🔴 {LABEL} paused: index below Supertrend(10,1.5), no buy today.\n{status_line}")
    save_state(set(), "red")  # clear so stocks alert fresh when index turns green
    raise SystemExit

if regime == "green" and prev_regime == "red":
    send(f"🟢 {LABEL} resumed: both indexes above Supertrend(10,1.5).\n{status_line}")

if regime == "green":
    regime_line = "🟢 Nifty50 & Nifty500 above Supertrend(10,1.5)\n"
else:
    regime_line = f"⚠️ Index check incomplete, filter not fully applied\n{status_line}\n"

# ---------- stock scan ----------
SYMBOLS = load_symbols()
hits, failed_syms = {}, set()
CH = 100
for i in range(0, len(SYMBOLS), CH):
    chunk = SYMBOLS[i:i + CH]
    try:
        data = yf.download([s + ".NS" for s in chunk], period="5d", interval="5m",
                           group_by="ticker", auto_adjust=False,
                           progress=False, threads=True)
    except Exception as e:
        print("download error:", e)
        failed_syms.update(chunk)
        continue
    for s in chunk:
        try:
            res = check(data[s + ".NS"].copy())
            if res is None:
                failed_syms.add(s)
            elif res[0]:
                hits[s] = (res[1], res[2])
        except Exception:
            failed_syms.add(s)

print(f"scanned {len(SYMBOLS)}, failed {len(failed_syms)}, matching {len(hits)}")

new = [s for s in hits if s not in active]
if new:
    blocks = []
    for s in new:
        price, r = hits[s]
        tv = f"https://in.tradingview.com/chart/?symbol=NSE:{quote(s)}"
        blocks.append(f"{s}: ₹{price:.2f} RSI {r:.0f}\nTradingView: {tv}")
    send(f"⚡ {LABEL} {now.strftime('%H:%M')}\n{regime_line}\n" + "\n\n".join(blocks))
elif FORCE:
    send(f"⚡ {LABEL}: test OK, scanned {len(SYMBOLS)}, failed {len(failed_syms)}, "
         f"matching now {len(hits)}, new 0\n{regime_line}")

# stocks whose data failed keep their old status, so no false repeat alerts
new_active = set(hits) | (active & failed_syms)
save_state(new_active, regime)
