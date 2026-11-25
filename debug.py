import os, requests, numpy as np, pandas as pd, yfinance as yf
from datetime import datetime
from zoneinfo import ZoneInfo

TOKEN = os.environ["TG_TOKEN"].strip()
CHAT_ID = os.environ["TG_CHAT_ID"].strip()
SYMS = os.environ["SYMBOLS"].replace(",", " ").split()
now = datetime.now(ZoneInfo("Asia/Kolkata"))

def rma(s, n):
    return s.ewm(alpha=1.0 / n, adjust=False).mean()

def supertrend(df, period, mult):
    h, l, c = df["High"].values, df["Low"].values, df["Close"].values
    n = len(df)
    pc = np.roll(c, 1); pc[0] = c[0]
    tr = np.maximum(h - l, np.maximum(abs(h - pc), abs(l - pc)))
    atr = rma(pd.Series(tr), period).values
    up = np.zeros(n); lo = np.zeros(n); d = np.ones(n)
    for i in range(n):
        hl2 = (h[i] + l[i]) / 2
        bu = hl2 + mult * atr[i]; bl = hl2 - mult * atr[i]
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

def evaluate(df):
    dates = np.array(df.index.date)
    prev = sorted(set(dates[dates < dates[-1]]))[-1]
    p = df[dates == prev]
    ph, pl, pcl = p["High"].max(), p["Low"].min(), p["Close"].iloc[-1]
    r1 = 2 * ((ph + pl + pcl) / 3) - pl
    c = df["Close"]
    upper = (c.rolling(20).mean() + 2 * c.rolling(20).std(ddof=0)).iloc[-1]
    last = float(c.iloc[-1])
    rs = float(rsi(c).iloc[-1])
    st_up, st_lvl = supertrend(df, 20, 2.0)
    return dict(t=df.index[-1].strftime("%H:%M"), close=last,
                st=st_up, st_lvl=st_lvl, rsi=rs, upper=float(upper), r1=float(r1),
                ok=bool(st_up and rs > 70 and last > upper and last > r1))

def m(b):
    return "✅" if b else "❌"

out = [f"DEBUG {now:%H:%M:%S} IST (last 4 completed candles; time = candle start)"]
for s in SYMS:
    try:
        df = yf.Ticker(s + ".NS").history(period="5d", interval="5m", auto_adjust=False)
        df = df.dropna(subset=["Close", "High", "Low"])
        if now < df.index[-1] + pd.Timedelta(minutes=5):
            df = df.iloc[:-1]
        out.append(f"\n{s}")
        for k in range(4, 0, -1):
            sub = df.iloc[:len(df) - (k - 1)]
            e = evaluate(sub)
            out.append(
                f"{e['t']} close {e['close']:.2f} | ST{m(e['st'] and e['close'] > e['st_lvl'])} "
                f"RSI {e['rsi']:.1f}{m(e['rsi'] > 70)} "
                f"BB {e['upper']:.2f}{m(e['close'] > e['upper'])} "
                f"R1 {e['r1']:.2f}{m(e['close'] > e['r1'])} "
                f"=> {'MATCH' if e['ok'] else 'no'}")
    except Exception as e:
        out.append(f"\n{s}: error {e}")

msg = "\n".join(out)
print(msg)
requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage",
              data={"chat_id": CHAT_ID, "text": msg})
