import os, json, requests
from datetime import datetime
from zoneinfo import ZoneInfo
from urllib.parse import quote
from bs4 import BeautifulSoup

TOKEN = os.environ["TG_TOKEN"]
CHAT_ID = os.environ["TG_CHAT_ID"]
SCAN_CLAUSE = os.environ["SCAN_CLAUSE"]
FORCE = os.environ.get("FORCE", "no") == "yes"
LABEL = "Intraday 5min"
STATE = "state/seen.json"

now = datetime.now(ZoneInfo("Asia/Kolkata"))
mins = now.hour * 60 + now.minute
in_hours = now.weekday() < 5 and (9 * 60 + 20) <= mins <= (15 * 60 + 25)
if not in_hours and not FORCE:
    raise SystemExit

def run_scan():
    s = requests.Session()
    s.headers["User-Agent"] = "Mozilla/5.0"
    page = s.get("https://chartink.com/screener/")
    token = BeautifulSoup(page.text, "html.parser").select_one(
        "meta[name=csrf-token]")["content"]
    r = s.post("https://chartink.com/screener/process",
               data={"scan_clause": SCAN_CLAUSE},
               headers={"x-csrf-token": token})
    return r.json().get("data", [])

def send(msg):
    requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage",
                  data={"chat_id": CHAT_ID, "text": msg,
                        "disable_web_page_preview": True})

today = now.strftime("%Y-%m-%d")
seen = set()
if os.path.exists(STATE):
    try:
        st = json.load(open(STATE))
        if st.get("date") == today:
            seen = set(st.get("seen", []))
    except Exception:
        pass

rows = run_scan()
new = [r for r in rows if r["nsecode"] not in seen]

if new:
    blocks = []
    for r in new:
        code = r["nsecode"]
        tv = f"https://in.tradingview.com/chart/?symbol=NSE:{quote(code)}"
        blocks.append(
            f"{code}: ₹{r.get('close')} ({r.get('per_chg')}%) vol {r.get('volume')}\n"
            f"TradingView: {tv}")
        seen.add(code)
    send(f"⚡ {LABEL} {now.strftime('%H:%M')}\n\n" + "\n\n".join(blocks))
    os.makedirs("state", exist_ok=True)
    json.dump({"date": today, "seen": sorted(seen)}, open(STATE, "w"))
elif FORCE:
    send(f"⚡ {LABEL}: test OK, abhi koi naya stock nahi hai")
