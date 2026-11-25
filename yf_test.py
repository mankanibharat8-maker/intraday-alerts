import os, requests, yfinance as yf
from datetime import datetime
from zoneinfo import ZoneInfo

TOKEN = os.environ["TG_TOKEN"].strip()
CHAT_ID = os.environ["TG_CHAT_ID"].strip()
syms = ["RELIANCE", "TCS", "INFY", "HDFCBANK", "SBIN"]

now = datetime.now(ZoneInfo("Asia/Kolkata"))
lines = [f"yfinance test, time now (IST): {now:%H:%M:%S}"]
for s in syms:
    try:
        df = yf.Ticker(s + ".NS").history(period="1d", interval="5m")
        if df.empty:
            lines.append(f"{s}: no data")
            continue
        last = df.index[-1].tz_convert("Asia/Kolkata")
        lag = (now - last).total_seconds() / 60
        lines.append(f"{s}: last candle {last:%H:%M}, close {df['Close'].iloc[-1]:.2f}, age {lag:.0f} min")
    except Exception as e:
        lines.append(f"{s}: error {e}")

msg = "\n".join(lines)
print(msg)
requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage",
              data={"chat_id": CHAT_ID, "text": msg})
