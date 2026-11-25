import os
import io
import json
import requests
import numpy as np
import pandas as pd
import yfinance as yf
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
GAP = pd.Timedelta(minutes=5)

now = datetime.now(ZoneInfo("Asia/Kolkata"))
mins = now.hour * 60 + now.minute
in_hours = now.weekday() < 5 and mins >= 560 and mins <= 925
if not in_hours and not FORCE:
    raise SystemExit


def send(msg):
    url = "https://api.telegram.org/bot" + TOKEN + "/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": msg, "disable_web_page_preview": True}
    r = requests.post(url, data=payload)
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
        if not
