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

def tick(ok):
    return "✅" if ok else "❌"

out = [f"DEBUG {now:%H:%M:%S} IST"]
for s in SYMS:
    try:
        df = yf.Ticker(s + ".NS").history(period="5d", interval="5m", auto_adjust=False)
        df = df.dropna(subset=["Close", "High", "Low"])
        if now < df.index[-1] + pd.Timedelta(minutes=5):
            df = df.iloc[:-1]
        dates = np.array(df.index.date)
        prev = sorted(set(dates[dates < dates[-1]]))[-1]
        p = df[dates == prev]
        ph, pl, pcl = p["High"].max(), p["Low"].min(), p["Close"].iloc[-1]
        pivot = (ph + pl + pcl) / 3
        r1 = 2 * pivot - pl
        c = df["Close"]
        upper = (c.rolling(20).mean() + 2 * c.rolling(20).std(ddof=0)).iloc[-1]
        last = float(c.iloc[-1])
        rs = float(rsi(c).iloc[-1])
        st_up, st_lvl = supertrend(df, 20, 2.0)
        t = df.index[-1].strftime("%H:%M")
        out.append(
            f"\n{s} | candle {t} | close {last:.2f}\n"
            f"{tick(st_up and last > st_lvl)} Supertrend(20,2): {'up' if st_up else 'down'}, level {st_lvl:.2f}\n"
            f"{tick(rs > 70)} RSI14: {rs:.1f}\n"
            f"{tick(last > upper)} Upper BB(20,2): {upper:.2f}\n"
            f"{tick(last > r1)} Pivot R1: {r1:.2f} (prev day H {ph:.2f} L {pl:.2f} C {pcl:.2f})")
    except Exception as e:
        out.append(f"\n{s}: error {e}")

msg = "\n".join(out)
print(msg)
requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage",
              data={"chat_id": CHAT_ID, "text": msg})
