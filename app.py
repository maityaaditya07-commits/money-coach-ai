"""Money Coach - a friendly personal finance coach (Streamlit + SQLite + Gemini AI guide + Voice).

HOW TO RUN  (keep app.py and demo_data.py in the same folder)
    pip install streamlit pandas google-genai pdfplumber
    streamlit run app.py

AI GUIDE
    Set GEMINI_API_KEY as an environment variable, or put it in .streamlit/secrets.toml:
        GEMINI_API_KEY = "your-key"
"""
import calendar, hashlib, hmac, html, io, json, math, os, re, sqlite3, uuid
from datetime import date, timedelta
from types import SimpleNamespace

import pandas as pd
import streamlit as st

from demo_data import sample, demo_csv_text

st.set_page_config(page_title="Money Coach", page_icon="💸", layout="wide")

MODEL = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")
esc = lambda s: html.escape(str(s))
H = lambda x: st.markdown(x, unsafe_allow_html=True)

# ======================================================================================
# 1. CONSTANTS
# ======================================================================================
CATS = ["Rent", "Food & Dining", "Groceries", "Transport", "Subscriptions", "Bills & Utilities", "Shopping",
        "Health", "Education", "Entertainment", "Other", "Savings Transfer", "Income", "Uncategorized"]
EMOJI = {"Rent": "🏠", "Food & Dining": "🍔", "Groceries": "🛒", "Transport": "🚌", "Subscriptions": "📺",
         "Bills & Utilities": "💡", "Shopping": "🛍️", "Health": "💊", "Education": "📚", "Entertainment": "🎬",
         "Other": "✨", "Savings Transfer": "🐷", "Income": "💰", "Uncategorized": "❓"}
NOT_SPEND = {"Savings Transfer", "Income"}
FIXEDISH = {"Rent", "Bills & Utilities", "Subscriptions", "Education"}
DISC = ["Food & Dining", "Shopping", "Entertainment", "Subscriptions"]
REC_CATS = {"Subscriptions", "Bills & Utilities", "Rent", "Education", "Uncategorized", "Other"}
BILL_CATS = ["Subscriptions", "Bills & Utilities", "Rent", "Education", "Other"]
TOP = ["Rent", "Food & Dining", "Groceries", "Transport", "Shopping", "Subscriptions", "Bills & Utilities",
       "Entertainment", "Health", "Education", "Other"]

DEFAULTS = {"swiggy": "Food & Dining", "zomato": "Food & Dining", "dominos": "Food & Dining", "blinkit": "Groceries",
            "bigbasket": "Groceries", "zepto": "Groceries", "uber": "Transport", "ola": "Transport", "rapido": "Transport",
            "irctc": "Transport", "metro": "Transport", "redbus": "Transport", "netflix": "Subscriptions",
            "spotify": "Subscriptions", "prime": "Subscriptions", "hotstar": "Subscriptions", "gym": "Subscriptions",
            "jio": "Bills & Utilities", "airtel": "Bills & Utilities", "electricity": "Bills & Utilities", "rent": "Rent",
            "amazon": "Shopping", "flipkart": "Shopping", "myntra": "Shopping", "pharmacy": "Health", "apollo": "Health",
            "medplus": "Health", "pvr": "Entertainment", "bookmyshow": "Entertainment", "udemy": "Education",
            "coursera": "Education", "salary": "Income", "stipend": "Income", "allowance": "Income",
            "savings": "Savings Transfer"}
GUESS = {"stationer": "Shopping", "store": "Shopping", "mart": "Groceries", "kirana": "Groceries",
         "supermarket": "Groceries", "medical": "Health", "clinic": "Health", "hospital": "Health",
         "chemist": "Health", "cafe": "Food & Dining", "restaurant": "Food & Dining", "dhaba": "Food & Dining",
         "hotel": "Food & Dining", "bakery": "Food & Dining", "tea": "Food & Dining", "college": "Education",
         "school": "Education", "books": "Education", "tuition": "Education", "petrol": "Transport",
         "fuel": "Transport", "cab": "Transport", "cinema": "Entertainment", "recharge": "Bills & Utilities",
         "broadband": "Bills & Utilities"}

LABEL2CAT = {f"{EMOJI[c]} {c}": c for c in CATS if c != "Uncategorized"}
CAT_LABELS = list(LABEL2CAT)
QA = {f"{EMOJI[c]} {c}": (c, "DR") for c in TOP}
QA["💰 Money in"] = ("Income", "CR")
QA["🐷 Put aside"] = ("Savings Transfer", "DR")
NAV = ["🏠 Home", "➕ Add", "🧾 Activity", "🎯 Plan", "🔁 Bills", "💬 Ask"]

SYSTEM = (
    "You are Money Coach, a warm, friendly money buddy for students and young adults in India. "
    "Use simple words, short sentences, and rupees (₹). Keep answers under 120 words. "
    "Use ONLY the numbers in the FACTS below; never invent numbers. If you do not know, say so. "
    "You EDUCATE and model scenarios. You must NEVER recommend or name specific stocks, mutual funds, ETFs, "
    "crypto, or any other securities. If asked what to invest in, explain the general idea (e.g. why a safety "
    "cushion comes first) and suggest speaking to a SEBI-registered advisor. Never be preachy or scary.")

GREEN, AMBER, RED, INDIGO, SLATE = "#10b981", "#f59e0b", "#ef4444", "#6366f1", "#94a3b8"
STATUS_COLOR = {"green": GREEN, "amber": AMBER, "red": RED, "done": INDIGO}

# ======================================================================================
# 2. DATABASE
# ======================================================================================
@st.cache_resource
def get_conn():
    c = sqlite3.connect("money_coach.db", check_same_thread=False)
    c.executescript("""
    CREATE TABLE IF NOT EXISTS users(username TEXT PRIMARY KEY, password TEXT);
    CREATE TABLE IF NOT EXISTS tx(id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT, date TEXT, merchant TEXT,
        amount REAL, type TEXT, category TEXT, cat_src TEXT, uid TEXT UNIQUE);
    CREATE TABLE IF NOT EXISTS rules(username TEXT, pattern TEXT, category TEXT, PRIMARY KEY(username, pattern));
    CREATE TABLE IF NOT EXISTS budgets(username TEXT, category TEXT, limit_amt REAL, PRIMARY KEY(username, category));
    CREATE TABLE IF NOT EXISTS dismissed(username TEXT, key TEXT, PRIMARY KEY(username, key));
    CREATE TABLE IF NOT EXISTS snoozed(username TEXT, key TEXT, until TEXT, PRIMARY KEY(username, key));
    CREATE TABLE IF NOT EXISTS subs(username TEXT, key TEXT, answer TEXT, PRIMARY KEY(username, key));
    CREATE TABLE IF NOT EXISTS profile(username TEXT PRIMARY KEY, income REAL DEFAULT 15000, fixed REAL DEFAULT 6000,
        ef REAL DEFAULT 0, saved REAL DEFAULT 0, goal TEXT DEFAULT 'My goal', target REAL DEFAULT 10000,
        goal_date TEXT, onboarded INTEGER DEFAULT 0, ai_consent INTEGER DEFAULT 0);
    CREATE TABLE IF NOT EXISTS goals(id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT, name TEXT, target REAL,
        saved REAL DEFAULT 0, goal_date TEXT, is_primary INTEGER DEFAULT 0, created TEXT);
    CREATE TABLE IF NOT EXISTS contribs(id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT, goal_id INTEGER,
        date TEXT, amount REAL);
    CREATE TABLE IF NOT EXISTS bills(id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT, name TEXT, amount REAL,
        day INTEGER, category TEXT);
    CREATE TABLE IF NOT EXISTS scenarios(id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT, name TEXT,
        delta REAL, lump REAL);""")
    c.commit()
    return c

conn = get_conn()

def run(sql, a=()):
    conn.execute(sql, a)
    conn.commit()

def q(sql, a=()):
    return pd.read_sql(sql, conn, params=a)

def me():
    return st.session_state.get("user")

def toast(msg):
    st.session_state["_toast"] = msg

def go(page):
    st.session_state["nav"] = page

PCOLS = "username,income,fixed,ef,saved,goal,target,goal_date,onboarded,ai_consent"

def all_goals(u):
    return q("SELECT id,name,target,saved,goal_date,is_primary FROM goals WHERE username=? ORDER BY goal_date,id", (u,))

def focus_goal(gs):
    open_ = gs[gs.saved < gs.target]
    pin = gs[gs.is_primary == 1]
    if not pin.empty and (pin.iloc[0]["saved"] < pin.iloc[0]["target"] or open_.empty):
        return pin.iloc[0]
    return open_.iloc[0] if not open_.empty else gs.iloc[0]

def get_profile(u):
    r = conn.execute(f"SELECT {PCOLS} FROM profile WHERE username=?", (u,)).fetchone()
    if r is None:
        run("INSERT INTO profile(username, goal_date) VALUES(?,?)", (u, str(date.today() + timedelta(days=365))))
        r = conn.execute(f"SELECT {PCOLS} FROM profile WHERE username=?", (u,)).fetchone()
    p = SimpleNamespace(**dict(zip(PCOLS.split(","), r)))
    if p.onboarded and not conn.execute("SELECT 1 FROM goals WHERE username=?", (u,)).fetchone():
        run("INSERT INTO goals(username,name,target,saved,goal_date,is_primary,created) VALUES(?,?,?,?,?,1,?)",
            (u, p.goal, p.target, p.saved, p.goal_date, str(date.today())))
    gs = all_goals(u)
    p.goals, p.goal_id = gs, None
    if not gs.empty:
        g = focus_goal(gs)
        p.goal_id, p.goal, p.target, p.saved, p.goal_date = int(g["id"]), g["name"], float(g["target"]), float(g["saved"]), g["goal_date"]
    return p

def hpw(pw, salt=None):
    salt = salt or os.urandom(16).hex()
    return salt + "$" + hashlib.pbkdf2_hmac("sha256", pw.encode(), salt.encode(), 100_000).hex()

def check_pw(pw, stored):
    return hmac.compare_digest(hpw(pw, stored.split("$")[0]), stored)

# ======================================================================================
# 3. HELPERS
# ======================================================================================
def inr(x):
    x = int(round(float(x)))
    sign, s = ("-" if x < 0 else ""), str(abs(x))
    if len(s) > 3:
        head, tail, parts = s[:-3], s[-3:], []
        while len(head) > 2:
            parts.insert(0, head[-2:])
            head = head[:-2]
        if head:
            parts.insert(0, head)
        s = ",".join(parts + [tail])
    return f"{sign}₹{s}"

def pretty(d, fmt="%b %Y"):
    return pd.to_datetime(d).strftime(fmt)

def when_txt(days):
    return "today" if days == 0 else "tomorrow" if days == 1 else f"in {days} days"

def display_name(u):
    return "there" if str(u).startswith("guest-") else u

def chips(options, key, default=None):
    if hasattr(st, "pills"):
        return st.pills(key, options, selection_mode="single", default=default, key=key, label_visibility="collapsed")
    return st.radio(key, options, index=(options.index(default) if default in options else None),
                    horizontal=True, key=key, label_visibility="collapsed")

def multi_chips(options, key):
    if hasattr(st, "pills"):
        return st.pills(key, options, selection_mode="multi", key=key, label_visibility="collapsed") or []
    return st.multiselect(key, options, key=key, label_visibility="collapsed")

def pick_value(title, opts, key, default_idx=0, custom_default=None):
    st.markdown(f"**{title}**")
    labels = list(opts) + (["✏️ Other"] if custom_default is not None else [])
    choice = chips(labels, key, labels[default_idx]) or labels[default_idx]
    if choice == "✏️ Other":
        return st.number_input("Type an amount (₹)", min_value=0.0, value=float(custom_default), step=500.0, key=key + "_n")
    return opts[choice]

def bar_chart(df, colors=None):
    try:
        if colors:
            st.bar_chart(df, color=colors)
        else:
            st.bar_chart(df)
    except Exception:
        st.bar_chart(df)

def popover(label):
    return st.popover(label, use_container_width=True) if hasattr(st, "popover") else st.expander(label)

# ======================================================================================
# 4. PARSERS & AI
# ======================================================================================
def norm(s):
    s = re.sub(r"^(upi|pos|imps|neft)[-/ ]", "", str(s).lower())
    return re.sub(r"\s+", " ", re.sub(r"[^a-z ]", " ", s)).strip()

def clean(m):
    s = re.sub(r"\[(?:UPI|CARD|PHONE|ACCT|NUM)\]", " ", str(m))
    s = re.sub(r"(?i)^\s*(upi|pos|imps|neft|rtgs|ach|nach)\b[-/ ]*", "", s)
    s = re.sub(r"[-/_]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    s = s.title() if (s.isupper() or s.islower()) else s
    return s[:60] or "Unknown"

def mask(t):
    t = re.sub(r"[\w.]+@[A-Za-z0-9]+(?:\.[A-Za-z]{2,})?", "[UPI]", t)
    t = re.sub(r"\b(?:\d[ -]?){12,18}\d\b", "[CARD]", t)
    t = re.sub(r"(?:\+91[\-\s]?|\b0)?\b[6-9]\d{4}[\s\-]?\d{5}\b", "[PHONE]", t)
    t = re.sub(r"[Xx*]{2,}\d{3,4}", "[ACCT]", t)
    return re.sub(r"\b\d{9,}\b", "[NUM]", t)

def load_rules(u):
    rows = conn.execute("SELECT pattern, category FROM rules WHERE username=?", (u,)).fetchall()
    return sorted(rows, key=lambda r: -len(r[0]))

def categorize(rules, merchant, typ):
    n = norm(merchant)
    for pat, cat in rules:
        if pat and pat in n:
            return cat, "rule"
    for k, cat in DEFAULTS.items():
        if re.search(rf"\b{k}\b", n):
            return cat, "default"
    return ("Income", "default") if typ == "CR" else ("Uncategorized", "none")

def guess_cat(merchant):
    n = norm(merchant)
    for k, c in GUESS.items():
        if k in n:
            return c
    return None

def find_date(t):
    for pat in (r"\d{4}-\d{2}-\d{2}", r"\d{1,2}[-/]\d{1,2}[-/]\d{2,4}", r"\d{1,2}[- ][A-Za-z]{3}[- ,]*\d{2,4}"):
        m = re.search(pat, t)
        if m:
            iso = bool(re.fullmatch(r"\d{4}-\d{2}-\d{2}", m.group()))
            d = pd.to_datetime(m.group(), dayfirst=not iso, errors="coerce")
            if pd.notna(d):
                return d.date().isoformat()
    return None

def parse_sms(t):
    a = re.search(r"(?:INR|Rs\.?|₹)\s*([\d,]+(?:\.\d{1,2})?)", t, re.I)
    if not a:
        return None
    typ = "CR" if re.search(r"credit|received|deposit", t, re.I) and not re.search(r"debit", t, re.I) else "DR"
    m = re.search(r"(?:\bat|\bto|\bfrom|VPA|info[:\-]?)\s+([A-Za-z0-9&*._ \-]{2,40}?)(?=\s+(?:on|ref|via|upi|avl|bal)\b|[.,;]|$)", t, re.I)
    return (find_date(t), m.group(1).strip() if m else "Unknown", float(a.group(1).replace(",", "")), typ)

def num(x):
    s = re.sub(r"(?i)\b(?:inr|rs|dr|cr)\b\.?|₹|,", "", str(x)).strip()
    v = pd.to_numeric(s, errors="coerce")
    return 0.0 if pd.isna(v) else float(v)

def parse_csv(df):
    cols = {c.lower(): c for c in df.columns}
    pick = lambda *ks: next((cols[c] for k in ks for c in cols if k in c), None)
    dc, mc = pick("date"), pick("desc", "narr", "merchant", "particular", "detail")
    db, cr, am, ty = pick("debit", "withdraw"), pick("credit", "deposit"), pick("amount"), pick("type", "dr/cr")
    rows = []
    for _, r in df.iterrows():
        d = pd.to_datetime(r[dc], dayfirst=True, errors="coerce") if dc else pd.NaT
        if pd.isna(d):
            continue
        if db or cr:
            x, y = (num(r[db]) if db else 0), (num(r[cr]) if cr else 0)
            a, t = (x, "DR") if x else (y, "CR")
        else:
            a = num(r[am]) if am else 0
            t = ("CR" if str(r[ty]).lower().startswith("c") else "DR") if ty else ("DR" if a < 0 else "CR")
        if a:
            rows.append((d.date().isoformat(), mask(str(r[mc])) if mc and pd.notna(r[mc]) else "Unknown", abs(a), t))
    return rows

def parse_pdf(f):
    import pdfplumber
    rows = []
    with pdfplumber.open(f) as pdf:
        for pg in pdf.pages:
            for line in (pg.extract_text() or "").splitlines():
                d, amts = find_date(line), re.findall(r"\d[\d,]*\.\d{2}", line)
                if d and amts:
                    desc = re.sub(r"\d[\d,]*\.\d{2}|\d{1,4}[-/]\d{1,2}[-/]\d{1,4}|\b(dr|cr)\b", " ", line, flags=re.I)
                    typ = "CR" if re.search(r"\bcr\b|credit|salary", line, re.I) else "DR"
                    rows.append((d, mask(desc.strip()) or "Unknown", num(amts[0]), typ))
    return rows

def read_statement_csv(f):
    lines = f.getvalue().decode("utf-8-sig", errors="ignore").splitlines()
    hdr = next((i for i, l in enumerate(lines[:30]) if re.search(r"date", l, re.I) and l.count(",") >= 2), 0)
    return pd.read_csv(io.StringIO("\n".join(lines[hdr:])), on_bad_lines="skip", dtype=str)

def gemini_key():
    try:
        return os.getenv("GEMINI_API_KEY") or st.secrets["GEMINI_API_KEY"]
    except Exception:
        return None

def extract_sms_ai(masked_text):
    key = gemini_key()
    if not key:
        return None
    try:
        from google import genai
        from google.genai import types
        prompt = ("Extract every bank or UPI transaction from the text below (SMS or WhatsApp dump). "
                  "Return ONLY a JSON array. Each item: "
                  '{"date": "YYYY-MM-DD or null", "merchant": "short name", "amount": number, "type": "DR or CR"}. '
                  "DR = money spent/debited/sent. CR = money received/credited. "
                  "Ignore OTPs, balance alerts and promotions. Never output account or phone numbers.\n\nTEXT:\n" + masked_text)
        r = genai.Client(api_key=key).models.generate_content(
            model=MODEL, contents=prompt, config=types.GenerateContentConfig(response_mime_type="application/json"))
        data = json.loads(re.sub(r"```(?:json)?", "", r.text).strip())
        rows = []
        for it in data if isinstance(data, list) else []:
            a, t = num(it.get("amount")), str(it.get("type", "")).upper()
            if a <= 0 or t not in ("DR", "CR"):
                continue
            d = pd.to_datetime(it.get("date"), errors="coerce")
            rows.append((d.date().isoformat() if pd.notna(d) else None, mask(str(it.get("merchant") or "Unknown"))[:60], a, t))
        return rows or None
    except Exception as e:
        st.error(f"Gemini API Error (SMS extraction): {e}")
        return None

def extract_voice_transaction(audio_bytes):
    key = gemini_key()
    if not key:
        st.error("Gemini API key not found in secrets.toml.")
        return None
    try:
        from google import genai
        from google.genai import types
        prompt = ("Listen to this voice note about a financial transaction. "
                  "Return ONLY a JSON object (not markdown, just JSON) with: "
                  '{"date": "YYYY-MM-DD or null", "merchant": "merchant name", "amount": number, "type": "DR or CR"}. '
                  "DR = money spent/debited, CR = money received/credited.")
        client = genai.Client(api_key=key)
        response = client.models.generate_content(
            model=MODEL,
            contents=[prompt, {"mime_type": "audio/webm", "data": audio_bytes}],
            config=types.GenerateContentConfig(response_mime_type="application/json")
        )
        data = json.loads(re.sub(r"```(?:json)?", "", response.text).strip())
        a, t = num(data.get("amount")), str(data.get("type", "")).upper()
        if a <= 0 or t not in ("DR", "CR"):
            return None
        d = pd.to_datetime(data.get("date"), errors="coerce")
        return (d.date().isoformat() if pd.notna(d) else date.today().isoformat(), mask(str(data.get("merchant") or "Unknown"))[:60], a, t)
    except Exception as e:
        st.error(f"Gemini Voice Transaction Error: {e}")
        return None

def add_tx(u, rows):
    rules, seen, n = load_rules(u), {}, 0
    for d, m, a, t in rows:
        m = clean(m)
        base = f"{u}|{d}|{norm(m)}|{a:.2f}|{t}"
        seen[base] = seen.get(base, 0) + 1
        cat, src = categorize(rules, m, t)
        uid = hashlib.md5(f"{base}|{seen[base]}".encode()).hexdigest()
        n += conn.execute("INSERT OR IGNORE INTO tx(username,date,merchant,amount,type,category,cat_src,uid) "
                          "VALUES(?,?,?,?,?,?,?,?)", (u, d, m, float(a), t, cat, src, uid)).rowcount
    conn.commit()
    return n

def add_one(d, merchant, amount, typ, cat):
    run("INSERT INTO tx(username,date,merchant,amount,type,category,cat_src,uid) VALUES(?,?,?,?,?,?,?,?)",
        (me(), d, merchant, float(amount), typ, cat, "user", uuid.uuid4().hex))

# ======================================================================================
# 5. MATHS & PLANNING
# ======================================================================================
def spend_by_cat(df):
    if df.empty:
        return pd.Series(dtype=float)
    return df[(df.type == "DR") & ~df.category.isin(NOT_SPEND)].groupby("category").amount.sum()

def months_left(goal_date):
    gd, td = pd.to_datetime(goal_date), date.today()
    return max((gd.year - td.year) * 12 + gd.month - td.month, 1)

def goal(p, keep):
    need = max(p.target - p.saved, 0)
    eta = 0 if need == 0 else (math.ceil(need / keep) if keep > 0 else None)
    return need, need / months_left(p.goal_date), eta

def goals_plan(gs, keep, focus_id=None):
    out, avail = [], max(float(keep), 0.0)
    for _, g in gs.sort_values(["goal_date", "id"]).iterrows():
        need = max(float(g["target"]) - float(g["saved"]), 0)
        left = months_left(g["goal_date"])
        req = need / left
        alloc = min(req, avail) if need > 0 else 0.0
        avail -= alloc
        eta = 0 if need == 0 else (math.ceil(need / alloc) if alloc > 0 else None)
        status = "done" if need == 0 else "green" if alloc >= req - 0.5 else "amber" if alloc > 0 else "red"
        out.append(dict(id=int(g["id"]), name=g["name"], target=float(g["target"]), saved=float(g["saved"]), need=need,
                        req=req, left=left, alloc=alloc, eta=eta, status=status, date=g["goal_date"],
                        pinned=bool(g["is_primary"])))
    return out

def eta_date(n):
    return (date.today() + timedelta(days=30.4 * n)).strftime("%b %Y")

def next_due(day):
    t = date.today()
    y, m = t.year, t.month
    c = date(y, m, min(day, calendar.monthrange(y, m)[1]))
    if c < t:
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
        c = date(y, m, min(day, calendar.monthrange(y, m)[1]))
    return c

def recurring(tx, u):
    out = []
    if not tx.empty:
        d = tx[(tx.type == "DR") & tx.category.isin(REC_CATS)].copy()
        if not d.empty:
            d["k"], d["dt"] = d.merchant.map(norm), pd.to_datetime(d.date)
            asof = pd.to_datetime(tx.date.max())
            for k, g in d.groupby("k"):
                g = g.sort_values("dt")
                if not k or g["dt"].dt.to_period("M").nunique() < 2:
                    continue
                gap = g["dt"].diff().dt.days.dropna().median()
                if not 25 <= gap <= 35 or g.amount.std(ddof=0) / g.amount.mean() > 0.4:
                    continue
                prev, last = float(g.amount.iloc[-2]), float(g.amount.iloc[-1])
                nxt = g["dt"].iloc[-1] + pd.Timedelta(days=int(gap))
                status = "ok"
                if asof > nxt + pd.Timedelta(days=5):
                    status = "missed"
                elif abs(last - prev) > 0.05 * prev:
                    status = "changed"
                if status != "missed":
                    while nxt.date() < date.today():
                        nxt += pd.Timedelta(days=int(gap))
                out.append(dict(name=g.merchant.iloc[-1], key=k, cat=g.category.iloc[-1], usual=prev, last=last,
                                last_date=g.date.iloc[-1], next=nxt.date(), days=(nxt.date() - date.today()).days,
                                status=status, manual=False))
    seen = {r["key"] for r in out}
    for name, amt, day, cat in conn.execute("SELECT name,amount,day,category FROM bills WHERE username=?", (u,)).fetchall():
        k = norm(name)
        if k in seen:
            continue
        nx = next_due(int(day))
        out.append(dict(name=name, key=k, cat=cat, usual=amt, last=amt, last_date="manual", next=nx,
                        days=(nx - date.today()).days, status="ok", manual=True))
    return out

def snapshot(tx, p, rec):
    today = date.today()
    cur = today.strftime("%Y-%m")
    dim = calendar.monthrange(today.year, today.month)[1]
    ms = sorted(tx.date.str[:7].unique()) if not tx.empty else []
    use = ([m for m in ms if m < cur] or ms)[-3:]
    if use:
        t, k = tx[tx.date.str[:7].isin(use)], len(use)
        cat = spend_by_cat(t) / k
        inc = t[(t.type == "CR") & (t.category == "Income")].amount.sum() / k
        income = inc or p.income
        fixed_added = 0.0 if "Rent" in cat.index else float(p.fixed)
        spend = cat.sum() + fixed_added
    else:
        cat, income, spend = pd.Series(dtype=float), float(p.income), float(p.fixed)
        fixed_added = float(p.fixed)
    keep = income - spend
    need, req, eta = goal(p, keep)
    c = tx[tx.date.str[:7] == cur] if not tx.empty else tx
    m_in = c[(c.type == "CR") & (c.category == "Income")].amount.sum() if not c.empty else 0.0
    cc = spend_by_cat(c) if not c.empty else pd.Series(dtype=float)
    m_out = float(cc.sum())
    days_left = dim - today.day + 1
    bills_left = sum(r["last"] for r in rec if r["status"] != "missed" and 0 <= r["days"] <= days_left - 1)
    save_t = min(req, max(keep, 0)) if need > 0 else 0
    per_day = (max(income, m_in) - m_out - save_t - bills_left) / days_left
    status = "done" if need == 0 else "green" if keep >= req else "amber" if keep > 0 else "red"
    variable = float(cc[~cc.index.isin(FIXEDISH)].sum()) if len(cc) else 0.0
    frac = max(today.day / dim, 0.2)
    proj = m_out + variable * (1 / frac - 1) + bills_left + fixed_added
    cap = max(income - (req if need > 0 else 0), 0)
    return dict(cur=cur, dim=dim, day=today.day, days_left=days_left, cat=cat, income=income, spend=spend, keep=keep,
                need=need, req=req, eta=eta, m_in=m_in, m_out=m_out, m_has=not c.empty, per_day=per_day,
                status=status, fixed_added=fixed_added, proj=proj, cap=cap,
                plan=goals_plan(p.goals, keep) if p.goal_id else [],
                uncat=int((tx.category == "Uncategorized").sum()) if not tx.empty else 0)

def month_table(tx):
    rows = []
    for m in (sorted(tx.date.str[:7].unique()) if not tx.empty else []):
        t = tx[tx.date.str[:7] == m]
        rows.append(dict(month=m, inc=t[(t.type == "CR") & (t.category == "Income")].amount.sum(),
                         spent=spend_by_cat(t).sum(),
                         saved=t[(t.type == "DR") & (t.category == "Savings Transfer")].amount.sum()))
    return pd.DataFrame(rows)

def months_text(e0, e1):
    if e0 is None and e1 is None:
        return "Still not reachable. Try adding another change 🙂"
    if e0 is None:
        return f"Now you'd get there in {e1} months 🎉"
    if e1 is None:
        return "At this pace the goal would not be reachable ⚠️"
    d = e0 - e1
    return f"{d} month{'s' if d != 1 else ''} sooner 🎉" if d > 0 else f"{-d} month{'s' if d != -1 else ''} later" if d < 0 else "No change in timing"

def projection_df(p, keep, req, need, extra_saved=0.0):
    left = months_left(p.goal_date)
    eta = math.ceil(need / keep) if keep > 0 and need > 0 else 0
    n = min(max(left, eta, 6) + 2, 60)
    rows = []
    for m in range(n + 1):
        rows.append({"Months from now": m,
                     "At your pace": min(p.saved + extra_saved + max(keep, 0) * m, p.target),
                     "Needed to hit your date": min(p.saved + req * m, p.target),
                     "Goal": p.target})
    return pd.DataFrame(rows).set_index("Months from now")

# ======================================================================================
# 6. ACTIONS
# ======================================================================================
def learn(rid, merchant, cat, quiet=False):
    u, pat = me(), norm(merchant)
    run("UPDATE tx SET category=?, cat_src='user' WHERE id=?", (cat, rid))
    if pat:
        run("INSERT OR REPLACE INTO rules VALUES(?,?,?)", (u, pat, cat))
        for i, m in conn.execute("SELECT id, merchant FROM tx WHERE username=? AND cat_src!='user'", (u,)).fetchall():
            if pat in norm(m):
                conn.execute("UPDATE tx SET category=?, cat_src='rule' WHERE id=?", (cat, i))
        conn.commit()
    if not quiet:
        toast(f"Got it! {merchant} is now {EMOJI.get(cat, '')} {cat}. I'll remember this 🧠")

def learn_pick(rid, merchant, key):
    label = st.session_state.get(key)
    if not label:
        toast("Tap a category first 👆")
        return
    learn(rid, merchant, LABEL2CAT[label])

def skip(rid):
    st.session_state.setdefault("skipped", set()).add(rid)

def add_rule(pattern, cat):
    pat = norm(pattern)
    if not pat:
        toast("Type a merchant name first 👆")
        return
    u = me()
    run("INSERT OR REPLACE INTO rules VALUES(?,?,?)", (u, pat, cat))
    n = 0
    for i, m in conn.execute("SELECT id, merchant FROM tx WHERE username=? AND cat_src!='user'", (u,)).fetchall():
        if pat in norm(m):
            n += conn.execute("UPDATE tx SET category=?, cat_src='rule' WHERE id=?", (cat, i)).rowcount
    conn.commit()
    toast(f"Rule saved: anything with “{pat}” → {EMOJI.get(cat, '')} {cat} ({n} entries updated)")

def delete_rule(pat):
    run("DELETE FROM rules WHERE username=? AND pattern=?", (me(), pat))
    toast("Rule removed 🗑️")

def relabel_all():
    u, rules, n = me(), load_rules(me()), 0
    for i, m, t in conn.execute("SELECT id, merchant, type FROM tx WHERE username=? AND cat_src!='user'", (u,)).fetchall():
        cat, src = categorize(rules, m, t)
        n += conn.execute("UPDATE tx SET category=?, cat_src=? WHERE id=?", (cat, src, i)).rowcount
    conn.commit()
    toast(f"Re-checked {n} entries with everything I've learned 🧠")

def set_budget(cat, amt):
    run("INSERT OR REPLACE INTO budgets VALUES(?,?,?)", (me(), cat, amt))
    toast(f"Done! I'll tell you before you pass {inr(amt)} on {cat}.")

def set_budget_key(cat, key):
    amt = float(st.session_state.get(key) or 0)
    if amt <= 0:
        toast("Type a limit first 👆")
        return
    set_budget(cat, amt)

def remove_budget(cat):
    run("DELETE FROM budgets WHERE username=? AND category=?", (me(), cat))
    toast(f"Limit for {cat} removed")

def auto_budgets(cat_avg):
    for c, v in cat_avg.items():
        if c in ("Rent",) or v <= 0:
            continue
        run("INSERT OR REPLACE INTO budgets VALUES(?,?,?)", (me(), c, float(math.ceil(v * 1.1 / 100) * 100)))
    toast("Limits set at about 10% above your usual spending 🎯")

def dismiss(key):
    run("INSERT OR REPLACE INTO dismissed VALUES(?,?)", (me(), key))
    toast("Okay, got it 👍")

def snooze(key):
    run("INSERT OR REPLACE INTO snoozed VALUES(?,?,?)", (me(), key, str(date.today() + timedelta(days=7))))
    toast("Snoozed for a week 😴")

def answer_sub(key, name, amt, ans):
    run("INSERT OR REPLACE INTO subs VALUES(?,?,?)", (me(), key, ans))
    toast("Great, keeping it 👍" if ans == "yes" else
          f"Okay! Dropping {name} would free up {inr(amt)} a month. Try it in Plan → What-if.")

def set_consent(v):
    run("UPDATE profile SET ai_consent=? WHERE username=?", (v, me()))
    toast("Thanks! Ask me anything 💬" if v == 1 else "No problem. I'll answer in basic mode 🙂")

def ask_pending(text):
    st.session_state["pending_q"] = text

def add_to_goal_key(gid, key):
    amt = float(st.session_state.get(key) or 0)
    if amt <= 0 or gid is None:
        toast("Type an amount first 👆")
        return
    run("UPDATE goals SET saved=saved+? WHERE id=? AND username=?", (amt, gid, me()))
    run("INSERT INTO contribs(username,goal_id,date,amount) VALUES(?,?,?,?)", (me(), gid, str(date.today()), amt))
    toast(f"Nice! {inr(amt)} added to your goal 🎯")

def focus_set(gid):
    conn.execute("UPDATE goals SET is_primary=0 WHERE username=?", (me(),))
    conn.execute("UPDATE goals SET is_primary=1 WHERE id=? AND username=?", (gid, me()))
    conn.commit()
    toast("That goal now shows first on Home ⭐")

def delete_goal(gid):
    run("DELETE FROM goals WHERE id=? AND username=?", (gid, me()))
    run("DELETE FROM contribs WHERE goal_id=? AND username=?", (gid, me()))
    toast("Goal deleted 🗑️")

def add_ef_key(key):
    amt = float(st.session_state.get(key) or 0)
    if amt <= 0:
        toast("Type an amount first 👆")
        return
    run("UPDATE profile SET ef=ef+? WHERE username=?", (amt, me()))
    toast(f"{inr(amt)} added to your safety cushion 🛟")

def add_bill(name, amt, day, cat):
    if not name.strip() or amt <= 0:
        toast("Add a name and an amount first 👆")
        return
    run("INSERT INTO bills(username,name,amount,day,category) VALUES(?,?,?,?,?)", (me(), name.strip(), amt, int(day), cat))
    toast(f"Tracking {name.strip()} every month 🔁")

def delete_bill(bid):
    run("DELETE FROM bills WHERE id=? AND username=?", (bid, me()))
    toast("Bill removed")

def save_scenario(name, delta, lump):
    run("INSERT INTO scenarios(username,name,delta,lump) VALUES(?,?,?,?)", (me(), name.strip() or "My scenario", delta, lump))
    toast("Scenario saved 💾")

def delete_scenario(sid):
    run("DELETE FROM scenarios WHERE id=? AND username=?", (sid, me()))

def start_guest():
    u = "guest-" + uuid.uuid4().hex[:5]
    conn.execute("INSERT INTO users VALUES(?,?)", (u, hpw(uuid.uuid4().hex)))
    conn.execute(f"INSERT INTO profile({PCOLS}) VALUES(?,?,?,?,?,?,?,?,?,?)",
                 (u, 15000, 6000, 3000, 0, "Phone", 15000, str(date.today() + timedelta(days=183)), 1, 0))
    for name, tgt, sv, days, prim in (("Phone", 15000, 4000, 183, 1), ("Laptop", 40000, 10000, 730, 0),
                                      ("Goa trip", 20000, 2500, 365, 0)):
        conn.execute("INSERT INTO goals(username,name,target,saved,goal_date,is_primary,created) VALUES(?,?,?,?,?,?,?)",
                     (u, name, tgt, sv, str(date.today() + timedelta(days=days)), prim, str(date.today())))
    conn.commit()
    add_tx(u, sample())
    st.session_state["user"] = u
    toast("Welcome! This is demo data. Explore freely 🎈")

def add_demo():
    n = add_tx(me(), sample())
    toast(f"Added {n} demo transactions 🎬")

def sign_out():
    st.session_state["user"] = None
    st.session_state["nav"] = NAV[0]

def reset_data():
    u = me()
    for t in ("tx", "rules", "budgets", "dismissed", "snoozed", "subs", "contribs", "bills", "scenarios"):
        conn.execute(f"DELETE FROM {t} WHERE username=?", (u,))
    conn.commit()
    st.session_state["skipped"] = set()
    toast("All your transactions and labels were deleted 🗑️")

def undo_last():
    run("DELETE FROM tx WHERE id=(SELECT MAX(id) FROM tx WHERE username=?)", (me(),))
    toast("Removed your last entry ↩️")

def stage_import(rows, note):
    st.session_state["preview"] = {"rows": rows, "note": note}

def confirm_import():
    pv = st.session_state.pop("preview", None)
    if pv:
        n = add_tx(me(), pv["rows"])
        toast(f"Imported {n} new transaction(s) {pv['note']}. Repeats were skipped 📥")

def cancel_import():
    st.session_state.pop("preview", None)

# ======================================================================================
# 7. AI GUIDE
# ======================================================================================
def ai_context(p, s, rec):
    top = ", ".join(f"{c}: {inr(v)}" for c, v in s["cat"].sort_values(ascending=False).head(6).items()) or "no spending data yet"
    subs = ", ".join(f"{r['name']} {inr(r['last'])}/month" for r in rec if r["cat"] == "Subscriptions") or "none found"
    soon = ", ".join(f"{r['name']} {inr(r['last'])} {when_txt(r['days'])}" for r in rec if r["status"] != "missed" and 0 <= r["days"] <= 14) or "none"
    goals = "; ".join(f"{g['name']}: needs {inr(g['need'])} by {g['date']} ({inr(g['req'])}/month)" for g in s["plan"]) or "none"
    eta = "not reachable at this pace" if s["eta"] is None else f"{s['eta']} months"
    return (f"Typical monthly income: {inr(s['income'])}\nTypical monthly spending: {inr(s['spend'])}\n"
            f"Money kept per month: {inr(s['keep'])}\nBiggest spending areas per month: {top}\nSubscriptions: {subs}\n"
            f"Bills coming in 2 weeks: {soon}\nAll goals: {goals}\n"
            f"Main goal: {p.goal}, target {inr(p.target)}, saved so far {inr(p.saved)}, by {p.goal_date}\n"
            f"Needs to keep {inr(s['req'])} per month to hit the date; time to goal at current pace: {eta}\n"
            f"Safety cushion saved: {inr(p.ef)} (3 months of spending would be {inr(3 * s['spend'])})\n"
            f"Spent so far this month: {inr(s['m_out'])}; this month is heading to about {inr(s['proj'])} (plan allows {inr(s['cap'])}); "
            f"safe spending left per day: {inr(max(s['per_day'], 0))}")

def local_answer(question, p, s, rec):
    t = question.lower()
    m = re.search(r"(\d[\d,]*)", t)
    amt = float(m.group(1).replace(",", "")) if m else None
    cats = s["cat"].sort_values(ascending=False)
    if re.search(r"invest|stock|share|mutual|crypto|fund|sip", t):
        return ("I can't tell you which stocks or funds to buy; I only teach and model. 🙂 "
                f"A good first step is a safety cushion of 3 months of spending (about {inr(3 * s['spend'])}); you have {inr(p.ef)}. "
                "For specific investments, talk to a SEBI-registered advisor.")
    if amt and re.search(r"afford|buy|purchase|phone|laptop|get a|spend", t):
        days = amt / s["per_day"] if s["per_day"] > 0 else None
        slip = math.ceil(amt / s["keep"]) if s["keep"] > 0 else None
        a = f"{inr(amt)} is "
        a += f"about {days:.0f} days of your safe daily spending. " if days else "more than your safe spending right now. "
        a += (f"It would push your {p.goal} goal back by roughly {slip} month(s). " if slip and s["need"] > 0 else "")
        a += ("If it's a want, waiting a month or saving up for it first usually feels better 🙂" if s["status"] != "green"
              else "You're on track, so it's your call. A small treat won't derail you 🙂")
        return a
    if re.search(r"bill|due|upcoming|coming up", t):
        soon = sorted([r for r in rec if r["status"] != "missed" and 0 <= r["days"] <= 14], key=lambda r: r["days"])
        return ("Coming up: " + ", ".join(f"{r['name']} {inr(r['last'])} ({when_txt(r['days'])})" for r in soon) + "." if soon
                else "No bills are due in the next 2 weeks 🎉")
    if re.search(r"today|daily|per day|safe", t):
        return (f"You can spend about {inr(max(s['per_day'], 0))} a day for the rest of this month and still stay on plan."
                if s["per_day"] > 0 else "This month's safe spending is used up, so keep it light until your next income.")
    if re.search(r"limit|budget", t):
        return (f"This month is heading to about {inr(s['proj'])} and your plan allows about {inr(s['cap'])}. "
                "Set per-category limits in Plan → Limits and I'll warn you before you pass them.")
    if re.search(r"overspend|where|most|biggest|spending", t):
        if cats.empty:
            return "I need a few transactions first. Add some in the ➕ Add tab, or load the demo data from ⚙️."
        top = ", ".join(f"{EMOJI.get(c, '')} {c} ({inr(v)})" for c, v in cats.head(3).items())
        d = [c for c in cats.index if c in DISC]
        tip = f" Easiest to trim: {d[0]}, since a 20% cut saves {inr(cats[d[0]] * .2)} a month." if d else ""
        return f"Your biggest spends per month are {top}.{tip}"
    if re.search(r"goal|faster|reach|save|saving", t):
        d = [c for c in cats.index if c in DISC]
        extra = f" Trimming {d[0]} by 20% would add {inr(cats[d[0]] * .2)} a month." if d else ""
        eta = "not reachable at this pace" if s["eta"] is None else f"about {s['eta']} months ({eta_date(s['eta'])})"
        return (f"For {p.goal} you need {inr(s['req'])} a month to hit {pretty(p.goal_date)}. "
                f"You keep about {inr(s['keep'])}, so it takes {eta}.{extra} Try the presets in Plan → What-if.")
    if re.search(r"cushion|emergency", t):
        mo = p.ef / s["spend"] if s["spend"] else 0
        return (f"A safety cushion is money set aside for surprises (a phone repair, a medical bill). Aim for 3 months of spending "
                f"(≈{inr(3 * s['spend'])}). You have {inr(p.ef)}, about {mo:.1f} months.")
    if re.search(r"subscri|netflix|spotify|gym", t):
        subs = [r for r in rec if r["cat"] == "Subscriptions"]
        return ("Your subscriptions: " + ", ".join(f"{r['name']} {inr(r['last'])}" for r in subs) +
                f". Total {inr(sum(r['last'] for r in subs))}/month. Use the 'Cancel one subscription' preset in Plan to see the effect."
                if subs else "I haven't found any monthly subscriptions yet. Add a few months of transactions and I'll spot them.")
    return (f"Quick snapshot: about {inr(s['income'])} comes in, {inr(s['spend'])} goes out, and you keep {inr(s['keep'])} a month. "
            f"Your goal ({p.goal}) needs {inr(s['req'])} a month. Ask me about spending, bills, your goal, or buying something!")

def ask_ai(question, history, ctx, allow_cloud, p, s, rec):
    key = gemini_key()
    if allow_cloud and key:
        try:
            from google import genai
            from google.genai import types
            client = genai.Client(api_key=key)
            convo = "\n".join(f"{m['role'].capitalize()}: {m['content']}" for m in history[-6:])
            r = client.models.generate_content(
                model=MODEL, contents=f"{convo}\nUser: {question}",
                config=types.GenerateContentConfig(system_instruction=SYSTEM + "\n\nFACTS:\n" + ctx))
            if r.text:
                return r.text.strip(), "gemini"
        except Exception as e:
            st.warning(f"Gemini API note: {e}. Using basic mode.")
    return local_answer(question, p, s, rec), "basic"
def ask_ai_voice(audio_bytes, history, ctx, allow_cloud, p, s, rec):
    key = gemini_key()
    if allow_cloud and key:
        try:
            from google import genai
            from google.genai import types
            client = genai.Client(api_key=key)
            convo = "\n".join(f"{m['role'].capitalize()}: {m['content']}" for m in history[-6:])
            
            # Use audio/webm since Streamlit st.audio_input records in webm/wav browser format
            r = client.models.generate_content(
                model=MODEL,
                contents=[
                    f"Conversation history:\n{convo}\nListen to this voice question and reply as Money Coach:", 
                    {"mime_type": "audio/webm", "data": audio_bytes}
                ],
                config=types.GenerateContentConfig(system_instruction=SYSTEM + "\n\nFACTS:\n" + ctx)
            )
            if r.text:
                return r.text.strip(), "gemini"
        except Exception as e:
            # Show the exact error so it's never a mystery
            return f"⚠️ Gemini Voice Error: {e}", "basic"
    return "I couldn't process your voice note with Gemini right now. Please type your question below or check your API key.", "basic"

# ======================================================================================
# 8. ENHANCED UI & PSYCHOLOGY STYLING
# ======================================================================================
CSS = """
.block-container{padding-top:1.2rem;max-width:880px}
footer{visibility:hidden}
.stButton>button,.stFormSubmitButton>button{min-height:48px;border-radius:16px;font-weight:600;box-shadow:0 4px 14px rgba(0,0,0,0.06);transition:all 0.2s ease;}
.stButton>button:hover{transform:translateY(-1px);box-shadow:0 6px 20px rgba(99,102,241,0.25);}
.hero{border-radius:28px;padding:1.6rem 1.8rem;color:#fff;display:flex;gap:1.5rem;align-items:center;
 background:var(--hg);box-shadow:0 16px 40px rgba(0,0,0,.22);margin-bottom:1rem;border:1px solid rgba(255,255,255,0.15);}
.hero .lbl{font-size:.72rem;letter-spacing:.14em;font-weight:800;opacity:.85}
.hero h2{margin:.15rem 0 0;color:#fff;font-size:1.8rem;line-height:1.15}
.hero .big{font-size:1.2rem;font-weight:700;margin-top:.1rem}
.hero .meta{display:flex;flex-wrap:wrap;gap:.5rem;margin-top:.8rem}
.chip{background:rgba(255,255,255,0.22);backdrop-filter:blur(8px);border-radius:99px;padding:.25rem .85rem;font-size:.78rem;font-weight:600;white-space:nowrap}
.hero .tip{margin-top:.8rem;font-size:.95rem;opacity:.96;line-height:1.4}
.verdict{border-radius:20px;padding:1.1rem 1.4rem;font-size:1.08rem;line-height:1.6;font-weight:600;
 background:rgba(128,128,128,.06);border-left:6px solid var(--vc);border:1px solid rgba(128,128,128,.12);box-shadow:0 4px 20px rgba(0,0,0,0.03);margin:0.8rem 0;}
.cards{display:grid;grid-template-columns:repeat(3,1fr);gap:.8rem;margin:1rem 0}
.cards.c2{grid-template-columns:repeat(2,1fr)}
.card{border-radius:20px;padding:1.1rem 1.2rem;background:rgba(128,128,128,.04);border:1px solid rgba(128,128,128,.15);box-shadow:0 8px 24px rgba(0,0,0,0.02);transition:transform 0.2s ease;}
.card:hover{transform:translateY(-2px);box-shadow:0 12px 30px rgba(0,0,0,0.06);}
.card .l{font-size:.7rem;opacity:.7;text-transform:uppercase;letter-spacing:.08em;font-weight:700;}
.card .v{font-size:1.4rem;font-weight:800;margin-top:.2rem;letter-spacing:-0.01em;}
.card .s{font-size:.75rem;opacity:.65;margin-top:.1rem;}
.row{display:flex;align-items:center;gap:.8rem;margin:.6rem 0}
.row .n{width:42%;font-size:.9rem;font-weight:500;}
.row .b{flex:1;height:14px;background:rgba(128,128,128,.12);border-radius:99px;overflow:hidden}
.row .b>span{display:block;height:100%;border-radius:99px}
.row .a{width:3.8rem;text-align:right;font-weight:700;font-size:.9rem}
.story{border-radius:28px;padding:2.2rem 1.6rem;color:#fff;min-height:310px;display:flex;flex-direction:column;
 justify-content:center;gap:.6rem;box-shadow:0 16px 40px rgba(0,0,0,.25)}
.story .big{font-size:2.8rem}.story h2{margin:0;color:#fff;font-size:1.7rem}.story p{margin:0;font-size:1.1rem;opacity:.95}
.goalbox{display:flex;align-items:center;gap:1.4rem;padding:.5rem 0}
.pace{margin:.6rem 0 1.2rem;padding:1.1rem 1.3rem;border-radius:20px;background:rgba(128,128,128,.04);border:1px solid rgba(128,128,128,.12);}
.pace .top{display:flex;justify-content:space-between;font-size:.88rem;margin-bottom:.4rem;font-weight:600;}
.pace .track{position:relative;height:16px;border-radius:99px;background:rgba(128,128,128,.15)}
.pace .fill{height:100%;border-radius:99px}
.pace .mark{position:absolute;top:-6px;width:4px;height:28px;border-radius:2px;background:currentColor;opacity:.8}
.pace .foot{font-size:.78rem;opacity:.7;margin-top:.4rem;line-height:1.4;}
.gcard{border-radius:20px;padding:1.1rem 1.3rem;background:rgba(128,128,128,.03);border:1px solid rgba(128,128,128,.12);margin-bottom:0.8rem;}
.gcard .t{display:flex;justify-content:space-between;align-items:baseline;gap:.5rem}
.gcard .t b{font-size:1.1rem}
.badge{font-size:.72rem;font-weight:700;border-radius:99px;padding:.2rem .7rem;color:#fff;white-space:nowrap}
.sub{font-size:.82rem;opacity:.72;margin-top:0.3rem;}
@media(max-width:640px){.hero{flex-direction:column;text-align:center}.hero .meta{justify-content:center}
 .card .v{font-size:1.15rem}.verdict{font-size:1.02rem}.row .n{width:46%}.cards{grid-template-columns:1fr;}.cards.c2{grid-template-columns:1fr;}}
"""

def card(label, value, sub, color):
    return (f'<div class="card" style="border-top:5px solid {color}"><div class="l">{label}</div>'
            f'<div class="v">{value}</div><div class="s">{sub}</div></div>')

def bars_html(rows):
    return "".join(f'<div class="row"><div class="n">{esc(n)}</div><div class="b"><span style="width:{max(2, min(w, 100)):.0f}%;'
                   f'background:{c}"></span></div><div class="a">{a}</div></div>' for n, w, a, c in rows)

def ring(frac, color, track="rgba(128,128,128,.2)", text="currentColor", size=135):
    f, c = max(0, min(frac, 1)), 2 * math.pi * 54
    return (f'<svg width="{size}" height="{size}" viewBox="0 0 130 130" style="flex:none"><circle cx="65" cy="65" r="54" fill="none" '
            f'stroke="{track}" stroke-width="12"/>'
            f'<circle cx="65" cy="65" r="54" fill="none" stroke="{color}" stroke-width="12" stroke-linecap="round" '
            f'stroke-dasharray="{c * f:.1f} {c:.1f}" transform="rotate(-90 65 65)"/>'
            f'<text x="65" y="73" text-anchor="middle" font-size="24" font-weight="800" fill="{text}">{f * 100:.0f}%</text></svg>')

def pace_html(s):
    cap, proj, spent = max(s["cap"], 1), s["proj"], s["m_out"] + s["fixed_added"]
    ok = proj <= s["cap"] * 1.03
    col = GREEN if ok else RED
    w = min(spent / cap * 100, 100)
    mark = s["day"] / s["dim"] * 100
    head = "On pace for your plan 🟢" if ok else "Heading over your plan 🔴"
    return (f'<div class="pace"><div class="top"><b>{head}</b><span>{inr(spent)} of {inr(s["cap"])}</span></div>'
            f'<div class="track"><div class="fill" style="width:{w:.0f}%;background:{col}"></div>'
            f'<div class="mark" style="left:{mark:.0f}%"></div></div>'
            f'<div class="foot"><b>Today marker</b> ({s["day"]} of {s["dim"]} days). Projected month-end: <b>{inr(proj)}</b>. '
            f'Plan allowance: <b>{inr(s["cap"])}</b>.</div></div>')

# ======================================================================================
# 9. LOGIN & ONBOARDING
# ======================================================================================
def login_screen():
    H("<div style='text-align:center;padding:1.5rem 0 1rem'><div style='font-size:3.5rem'>💸</div>"
      "<h1 style='margin:0;font-weight:800;letter-spacing:-0.02em;'>Money Coach</h1><p style='opacity:.75;font-size:1.05rem;margin-top:0.4rem;'>Know where your money goes, and whether you're on track.</p></div>")
    
    col1, col2, col3 = st.columns([1, 1.4, 1])
    with col2:
        st.button("🚀 Try it now with demo data (no sign-up)", type="primary", use_container_width=True, on_click=start_guest)
        st.caption("<div style='text-align:center;margin:0.8rem 0;opacity:0.6;'>─── OR SIGN IN ───</div>", unsafe_allow_html=True)
        t1, t2 = st.tabs(["🔑 Sign in", "✨ Create account"])
        with t1:
            with st.form("login"):
                u = st.text_input("Username").strip()
                pw = st.text_input("Password", type="password")
                if st.form_submit_button("Sign in", use_container_width=True):
                    row = conn.execute("SELECT password FROM users WHERE username=?", (u,)).fetchone()
                    if row and check_pw(pw, row[0]):
                        st.session_state["user"] = u
                        st.rerun()
                    else:
                        st.error("That username or password doesn't match. Try again?")
        with t2:
            with st.form("signup"):
                u = st.text_input("Pick a username").strip()
                pw = st.text_input("Pick a password (4+ characters)", type="password")
                if st.form_submit_button("Create my account", use_container_width=True):
                    if not u or len(pw) < 4:
                        st.error("Please add a username and a password with at least 4 characters.")
                    elif u.lower().startswith("guest-"):
                        st.error("Please choose a different username.")
                    else:
                        try:
                            conn.execute("INSERT INTO users VALUES(?,?)", (u, hpw(pw)))
                            conn.commit()
                            get_profile(u)
                            st.session_state["user"] = u
                            st.rerun()
                        except sqlite3.IntegrityError:
                            st.error("That username is taken. Try another one.")

def onboarding():
    u = me()
    H(f"<h2 style='text-align:center;margin-bottom:0'>Hi {esc(display_name(u))}! 👋</h2>")
    st.caption("<div style='text-align:center;'>Four quick taps and you're ready. You can change anything later in ⚙️.</div>", unsafe_allow_html=True)
    
    col1, col2, col3 = st.columns([1, 1.5, 1])
    with col2:
        inc = pick_value("1️⃣ How much money comes in each month?", {"₹10,000": 10000, "₹15,000": 15000, "₹20,000": 20000, "₹30,000": 30000}, "ob_inc", 1, 15000)
        fix = pick_value("2️⃣ Fixed costs each month (rent, bills, loans)?", {"₹3,000": 3000, "₹5,000": 5000, "₹8,000": 8000, "₹12,000": 12000}, "ob_fix", 1, 6000)
        ef = pick_value("3️⃣ Emergency money you've already kept aside?", {"₹0": 0, "₹2,000": 2000, "₹5,000": 5000, "₹10,000": 10000}, "ob_ef", 0, 0)
        st.markdown("**4️⃣ What are you saving for?**")
        gl = ["💻 Laptop", "📱 Phone", "✈️ Trip", "🎓 Course", "🛟 Safety cushion", "✏️ Something else"]
        g = chips(gl, "ob_goal", gl[0]) or gl[0]
        gname = st.text_input("Name your goal", value="My goal", key="ob_gname") if g.startswith("✏️") else g.split(" ", 1)[1]
        target = pick_value("How much will it cost?", {"₹5,000": 5000, "₹10,000": 10000, "₹25,000": 25000, "₹50,000": 50000}, "ob_tgt", 2, 30000)
        months = pick_value("By when do you want it?", {"6 months": 6, "1 year": 12, "2 years": 24, "3 years": 36}, "ob_when", 1)
        st.write("")
        if st.button("Start my coach 🚀", type="primary", use_container_width=True):
            run("UPDATE profile SET income=?, fixed=?, ef=?, goal=?, target=?, goal_date=?, saved=0, onboarded=1 WHERE username=?",
                (inc, fix, ef, gname, target, str(date.today() + timedelta(days=int(months * 30.4))), u))
            toast("All set! Your goal is on the home screen 🎉")
            st.rerun()

# ======================================================================================
# 10. SETTINGS
# ======================================================================================
def settings_panel(p, tx):
    with st.form("prof"):
        inc = st.number_input("Money coming in each month (₹)", min_value=0.0, value=float(p.income), step=500.0)
        fix = st.number_input("Fixed costs each month (₹)", min_value=0.0, value=float(p.fixed), step=500.0)
        ef = st.number_input("Safety cushion saved so far (₹)", min_value=0.0, value=float(p.ef), step=500.0)
        if st.form_submit_button("Save changes", use_container_width=True):
            run("UPDATE profile SET income=?, fixed=?, ef=? WHERE username=?", (inc, fix, ef, me()))
            toast("Saved ✅")
            st.rerun()
    st.button("🎬 Add demo data", on_click=add_demo, use_container_width=True)
    d1, d2 = st.columns(2)
    mine = tx[["date", "merchant", "amount", "type", "category"]].to_csv(index=False) if not tx.empty else "date,merchant,amount,type,category\n"
    d1.download_button("⬇️ My data", mine, file_name="my-money-data.csv", mime="text/csv", use_container_width=True)
    d2.download_button("📄 Demo CSV", demo_csv_text(), file_name="demo_data.csv", mime="text/csv", use_container_width=True)
    st.caption("🌗 Dark / light mode: open the ⋮ menu (top right of the page) → Settings → Theme.")
    with st.expander("🗑️ Reset my data"):
        sure = st.checkbox("Yes, delete all my transactions and labels")
        st.button("Delete everything", disabled=not sure, on_click=reset_data)
    st.button("🚪 Sign out", on_click=sign_out, use_container_width=True)
    st.caption("🛡️ Money Coach teaches and models scenarios. It never recommends specific stocks, funds or other securities.")

# ======================================================================================
# 11. HOME (Asymmetric UI / Psychological Layout)
# ======================================================================================
def hero(p, s):
    stt = s["status"]
    grad = {"green": "linear-gradient(135deg,#047857,#10b981)", "amber": "linear-gradient(135deg,#b45309,#f59e0b)",
            "red": "linear-gradient(135deg,#b91c1c,#f97316)", "done": "linear-gradient(135deg,#6d28d9,#6366f1)"}[stt]
    badge = {"green": "🟢 On track", "amber": "🟠 A bit behind", "red": "🔴 Needs attention", "done": "🎉 Reached"}[stt]
    dleft = (pd.to_datetime(p.goal_date).date() - date.today()).days
    due = f"{dleft} days left" if dleft >= 0 else f"{-dleft} days overdue"
    if stt == "done":
        tip = "You did it! Add your next goal in Plan → Goals."
    elif stt == "green":
        tip = f"Keep going: set aside {inr(s['req'])} a month and you'll have it by {pretty(p.goal_date)}."
    elif stt == "amber":
        tip = (f"You're about {inr(s['req'] - s['keep'])} a month short of your date. Trim a little (Plan → What-if)"
               + (f" or move the date to {eta_date(s['eta'])}." if s["eta"] is not None else "."))
    else:
        tip = "At your current spending this goal isn't reachable yet. Open Plan → What-if to find a fix."
    chips_ = [f"Saved {inr(p.saved)} of {inr(p.target)}", f"🗓️ {pretty(p.goal_date, '%d %b %Y')} · {due}"]
    if s["need"] > 0:
        chips_ += [f"Needs {inr(s['req'])}/mo", f"You keep {inr(s['keep'])}/mo"]
        if s["eta"] is not None:
            chips_.append(f"ETA {eta_date(s['eta'])}")
    
    H(f'<div class="hero" style="--hg:{grad}">{ring(p.saved / max(p.target, 1), "#fff", "rgba(255,255,255,.3)", "#fff")}'
      f'<div><div class="lbl">🎯 ACTIVE GOAL FOCUS · {badge}</div><h2>{esc(p.goal)}</h2>'
      f'<div class="big">{"All saved!" if s["need"] == 0 else inr(s["need"]) + " to go"}</div>'
      f'<div class="meta">{"".join(f"<span class=chip>{esc(c)}</span>" for c in chips_)}</div>'
      f'<div class="tip">{esc(tip)}</div></div></div>')
    
    # Asymmetric action buttons with balanced visual weight
    col_act1, col_act2 = st.columns([1, 1])
    with col_act1:
        with popover("➕ Quick Add to Goal"):
            st.number_input("How much did you put aside? (₹)", min_value=0.0, value=0.0, step=500.0, key="hero_add")
            st.button("Add to my goal", key="hero_add_btn", type="primary", use_container_width=True,
                      on_click=add_to_goal_key, args=(p.goal_id, "hero_add"))
    with col_act2:
        st.button("🎯 Open Goal Planner", use_container_width=True, on_click=go, args=("🎯 Plan",))
        
    others = [g for g in s["plan"] if g["id"] != p.goal_id]
    if others:
        rows = [(f"🎯 {g['name']} · {pretty(g['date'], '%b %y')}", g["saved"] / max(g["target"], 1) * 100,
                 f"{g['saved'] / max(g['target'], 1) * 100:.0f}%", STATUS_COLOR[g["status"]]) for g in others]
        st.caption("Secondary Goals Pipeline")
        H(bars_html(rows))

def verdict_html(p, s):
    g, when = esc(p.goal), pretty(p.goal_date)
    if s["status"] == "done":
        return GREEN, f"You've already saved enough for <b>{g}</b>! 🎉 Time to pick your next goal in Plan."
    if s["status"] == "green":
        day = ""
        if s["m_has"]:
            day = (f" You can spend about <b>{inr(s['per_day'])}/day</b> for the rest of this month."
                   if s["per_day"] > 0 else " This month's safe spending is used up, so keep it light until your next income.")
        return GREEN, f"You're on track 🟢 <b>{g}</b> by {when}.{day}"
    if s["status"] == "amber":
        by = f" At this pace you'll get there by <b>{eta_date(s['eta'])}</b>." if s["eta"] is not None else ""
        return AMBER, (f"You're a little behind 🟠 To get <b>{g}</b> by {when} you need to keep {inr(s['req'])} a month. "
                       f"Right now it's about {inr(s['keep'])}.{by}")
    return RED, (f"Heads up 🔴 You're spending about <b>{inr(-s['keep'])}</b> more than you earn each month. "
                 "Let's fix that: open Plan and try a change.")

def build_alerts(tx, p, s, rec):
    u, out, today = me(), [], date.today()
    dis = {r[0] for r in conn.execute("SELECT key FROM dismissed WHERE username=?", (u,)).fetchall()}
    snz = {r[0] for r in conn.execute("SELECT key FROM snoozed WHERE username=? AND until>=?", (u, str(today))).fetchall()}
    subs = dict(conn.execute("SELECT key, answer FROM subs WHERE username=?", (u,)).fetchall())
    budgets = dict(conn.execute("SELECT category, limit_amt FROM budgets WHERE username=?", (u,)).fetchall())
    cur = s["cur"]
    ms = sorted(tx.date.str[:7].unique())
    prev_ms = [m for m in ms if m < cur][-3:]
    c = spend_by_cat(tx[tx.date.str[:7] == cur])
    pv = spend_by_cat(tx[tx.date.str[:7].isin(prev_ms)]) / len(prev_ms) if prev_ms else pd.Series(dtype=float)
    frac = today.day / s["dim"]

    if s["m_has"] and s["day"] >= 7 and s["proj"] > s["cap"] * 1.03:
        out.append(dict(pri=1, key=f"plan:{cur}", icon="🧭", title="You're drifting off your plan",
                        text=f"At this pace you'll spend about {inr(s['proj'])} this month. Your plan allows about {inr(s['cap'])} "
                             f"({inr(s['proj'] - s['cap'])} over).",
                        actions=[("See what to trim", go, ("🎯 Plan",))]))
    elif s["m_has"] and s["day"] >= 10 and s["need"] > 0 and s["proj"] < s["cap"] * 0.9:
        out.append(dict(pri=6, key=f"ahead:{cur}", icon="🌟", title="You're ahead of your plan",
                        text=f"You're on pace to keep about {inr(s['cap'] - s['proj'])} more than needed. Put some towards {p.goal}?",
                        actions=[("Open planner", go, ("🎯 Plan",))]))
    for cat, spent in c.sort_values(ascending=False).items():
        if cat == "Rent":
            continue
        lim, usual = budgets.get(cat), float(pv.get(cat, 0))
        proj = spent / frac if frac >= 0.3 else spent
        e = EMOJI.get(cat, "")
        if lim and spent > lim:
            out.append(dict(pri=1, key=f"over:{cat}:{cur}", icon="🔴", title=f"You've passed your {cat} limit",
                            text=f"{inr(spent)} spent this month, and your limit was {inr(lim)}. No stress: let's see what you can adjust.",
                            actions=[("See how to cut back", go, ("🎯 Plan",))]))
        elif lim and proj > lim:
            out.append(dict(pri=3, key=f"pace:{cat}:{cur}", icon="🟠", title=f"{e} {cat} is heading over your limit",
                            text=f"At this pace it'll reach about {inr(proj)} (limit {inr(lim)}).",
                            actions=[("See how to cut back", go, ("🎯 Plan",))]))
        elif not lim and usual > 0 and proj > 1.25 * usual and proj - usual > 300:
            sug = int(math.ceil(usual * 1.1 / 100) * 100)
            out.append(dict(pri=3, key=f"drift:{cat}:{cur}", icon="🟠", title=f"{e} You're spending more than usual on {cat}",
                            text=f"About {inr(proj)} this month vs {inr(usual)} usually.",
                            actions=[(f"Set a {inr(sug)} limit", set_budget, (cat, sug))]))
    if s["status"] in ("amber", "red") and s["need"] > 0:
        out.append(dict(pri=2, key=f"goal:{p.goal_id}:{cur}", icon="🎯", title=f"{p.goal} needs a boost",
                        text=f"It needs {inr(s['req'])} a month for {pretty(p.goal_date)}; you keep about {inr(max(s['keep'], 0))}.",
                        actions=[("Try a change", go, ("🎯 Plan",))]))
    d = tx[(tx.type == "DR") & ~tx.category.isin(NOT_SPEND | {"Rent"})].copy()
    if not d.empty:
        d["dt"] = pd.to_datetime(d.date)
        recent = d[d.dt >= pd.Timestamp(today - timedelta(days=7))]
        n_sp = 0
        for _, r in recent.sort_values("amount", ascending=False).iterrows():
            hist = d[(d.category == r["category"]) & (d.id != r["id"])].amount
            if n_sp < 2 and len(hist) >= 3 and r["amount"] >= max(1000, 3 * hist.median()):
                n_sp += 1
                k = f"spike:{r['id']}"
                out.append(dict(pri=3, key=k, icon="💥", title=f"Big one: {inr(r['amount'])} on {r['merchant']}",
                                text=f"That's much more than your usual {r['category']} spend (typically about {inr(hist.median())}).",
                                actions=[("Got it", dismiss, (k,))]))
    if s["uncat"]:
        out.append(dict(pri=2, key="teach", icon="🤔", title=f"{s['uncat']} payment{'s' if s['uncat'] > 1 else ''} need a label",
                        text="Tell me what they are once, and I'll recognise them forever.",
                        actions=[("Teach me", go, ("➕ Add",))]))
    for r in rec:
        if r["status"] != "missed" and 0 <= r["days"] <= 3:
            k = f"due:{r['key']}:{r['next']}"
            out.append(dict(pri=2, key=k, icon="⏰", title=f"{r['name']} is due {when_txt(r['days'])}",
                            text=f"{inr(r['last'])} will leave your account. Keep enough balance 🙂",
                            actions=[("Got it", dismiss, (k,))]))
        elif r["status"] == "changed":
            k = f"chg:{r['key']}:{r['last_date']}"
            up = r["last"] > r["usual"]
            out.append(dict(pri=2, key=k, icon="📈", title=f"{r['name']} {'got pricier' if up else 'got cheaper'}",
                            text=f"It was {inr(r['usual'])}, and your last payment was {inr(r['last'])}.",
                            actions=[("Got it", dismiss, (k,))]))
        elif r["status"] == "missed":
            k = f"miss:{r['key']}:{r['last_date']}"
            out.append(dict(pri=2, key=k, icon="👀", title=f"{r['name']} didn't charge this time",
                            text=f"Last paid on {r['last_date']} ({inr(r['last'])}). Cancelled it? Or is it just late?",
                            actions=[("Yes, cancelled", dismiss, (k,))]))
        elif r["cat"] == "Subscriptions" and subs.get(r["key"]) == "no":
            k = f"unused:{r['key']}"
            out.append(dict(pri=2, key=k, icon="✂️", title=f"You said you don't use {r['name']}",
                            text=f"Cancelling would free {inr(r['last'])} a month ({inr(r['last'] * 12)} a year).",
                            actions=[("I cancelled it", dismiss, (k,)), ("Try in planner", go, ("🎯 Plan",))]))
        elif r["cat"] == "Subscriptions" and r["key"] not in subs:
            out.append(dict(pri=4, key=f"use:{r['key']}", icon="🤷", title=f"Still using {r['name']}?",
                            text=f"It costs {inr(r['last'])} every month.",
                            actions=[("Yes 👍", answer_sub, (r["key"], r["name"], r["last"], "yes")),
                                     ("Not really", answer_sub, (r["key"], r["name"], r["last"], "no"))]))
    if s["spend"] > 0 and p.ef < 3 * s["spend"]:
        out.append(dict(pri=5, key="ef", icon="🛟", title="Your safety cushion can grow",
                        text=f"You have {inr(p.ef)}. A good target is 3 months of spending (≈{inr(3 * s['spend'])}).",
                        actions=[("Open cushion planner", go, ("🎯 Plan",))]))
    out = [a for a in out if a["key"] not in dis and a["key"] not in snz]
    return sorted(out, key=lambda a: a["pri"])

def render_alert(a):
    with st.container(border=True):
        st.markdown(f"**{a['icon']} {a['title']}**")
        st.caption(a["text"])
        acts = list(a["actions"]) + [("😴 Snooze 7d", snooze, (a["key"],))]
        cols = st.columns(len(acts))
        for i, (lab, fn, args) in enumerate(acts):
            cols[i].button(lab, key=f"al_{a['key']}_{i}", on_click=fn, args=args, use_container_width=True)

def home(tx, p, s, rec):
    hero(p, s)
    if tx.empty:
        with st.container(border=True):
            st.markdown("### 👋 Welcome!")
            st.write("I haven't seen any spending yet. Add your first one (takes 10 seconds), or look around with demo data.")
            a, b = st.columns(2)
            a.button("➕ Add my first spend", type="primary", use_container_width=True, on_click=go, args=("➕ Add",))
            b.button("🎬 Use demo data", use_container_width=True, on_click=add_demo)
            
    color, text = verdict_html(p, s)
    H(f'<div class="verdict" style="--vc:{color}">{text}</div>')
    
    if s["m_has"]:
        a, b, c = s["m_in"], s["m_out"], s["m_in"] - s["m_out"]
        sub = "this month so far"
    else:
        a, b, c, sub = s["income"], s["spend"], s["keep"], "in a typical month"
        
    # Asymmetric visual balance using non-monotonous staggered card grids
    H('<div class="cards">' + card("Came in", inr(a), sub, INDIGO) + card("Spent", inr(b), sub, AMBER)
      + card("You keep", inr(c), sub, GREEN if c >= 0 else RED) + "</div>")
      
    if s["m_has"] and not tx.empty:
        H('<div class="cards c2">' + card("Safe to spend today", inr(max(s["per_day"], 0)), f"{s['days_left']} days left this month", GREEN if s["per_day"] > 0 else RED)
          + card("Month-end forecast", inr(s["proj"]), f"plan allows {inr(s['cap'])}", GREEN if s["proj"] <= s["cap"] * 1.03 else RED) + "</div>")
        H(pace_html(s))
        
    st.button("🛍️ I just spent something", type="primary", use_container_width=True, on_click=go, args=("➕ Add",))

    # Two-column layout for breaking monotony below the fold
    col_left, col_right = st.columns([1.2, 1], gap="medium")
    
    with col_left:
        alerts = build_alerts(tx, p, s, rec) if not tx.empty else []
        if alerts:
            st.markdown(f"#### 💡 Smart Nudges ({len(alerts)})")
            for a in alerts[:3]:
                render_alert(a)
            if len(alerts) > 3:
                with st.expander(f"See all {len(alerts)} nudges"):
                    for a in alerts[3:]:
                        render_alert(a)
        elif not tx.empty:
            st.success("Nothing needs your attention right now 🎉")
            
        if not s["cat"].empty:
            base = max(s["income"], s["spend"], 1)
            items = [(c, v) for c, v in s["cat"].sort_values(ascending=False).items()]
            if s["fixed_added"] > 0:
                items.append(("Fixed costs", s["fixed_added"]))
            items.sort(key=lambda x: -x[1])
            top, rest = items[:5], sum(v for _, v in items[5:])
            rows = [(f"{EMOJI.get(c, '🏠')} {c}", v / base * 100, inr(v / base * 100), INDIGO) for c, v in top]
            if rest > 0:
                rows.append(("✨ Everything else", rest / base * 100, inr(rest / base * 100), SLATE))
            if s["keep"] > 0:
                rows.append(("🐷 What you keep", s["keep"] / base * 100, inr(s["keep"] / base * 100), GREEN))
            st.markdown("#### 🪙 Where did ₹100 go?")
            st.caption(f"{EMOJI.get(top[0][0], '🏠')} {top[0][0]} is your biggest spend.")
            H(bars_html(rows))

    with col_right:
        soon = sorted([r for r in rec if r["status"] != "missed" and 0 <= r["days"] <= 14], key=lambda r: r["days"])[:4]
        if soon:
            st.markdown("#### 📅 Coming up")
            for r in soon:
                note = " (price changed)" if r["status"] == "changed" else ""
                st.markdown(f"{EMOJI.get(r['cat'], '💳')} **{esc(r['name'])}** {when_txt(r['days'])} · {inr(r['last'])}{note}")

        mt = month_table(tx)
        if len(mt) >= 2:
            st.markdown("#### 📈 Cashflow Trends")
            df = mt.tail(6).assign(Month=lambda d: d.month.map(lambda m: pretty(m + "-01", "%b %y"))).set_index("Month")
            bar_chart(df[["inc", "spent"]].rename(columns={"inc": "Came in", "spent": "Spent"}), [INDIGO, AMBER])

        if not tx.empty:
            st.markdown("#### 🕒 Recent Ledger")
            for _, r in tx.sort_values(["date", "id"], ascending=False).head(4).iterrows():
                sign, col = ("+", GREEN) if r["type"] == "CR" else ("−", "inherit")
                H(f"{EMOJI.get(r['category'], '❓')} **{esc(r['merchant'])}** · {r['date']} · "
                  f"<span style='color:{col};font-weight:700'>{sign}{inr(r['amount'])}</span>")
            st.write("")
            st.button("📅 Month in Review Story", use_container_width=True, on_click=lambda: st.session_state.update(review=True, rev_i=0))

# ======================================================================================
# 12. MONTH IN REVIEW
# ======================================================================================
def month_stats(tx, mth):
    t = tx[tx.date.str[:7] == mth]
    ms = sorted(tx.date.str[:7].unique())
    i = ms.index(mth)
    cats = spend_by_cat(t).sort_values(ascending=False)
    prev = spend_by_cat(tx[tx.date.str[:7] == ms[i - 1]]) if i > 0 else pd.Series(dtype=float)
    inc = t[(t.type == "CR") & (t.category == "Income")].amount.sum()
    return dict(inc=inc, cats=cats, spent=cats.sum(), keep=inc - cats.sum(), prev=prev)

def review_cards(st_, p, s, label):
    cats, prev = st_["cats"], st_["prev"]
    c1 = ("💰", f"{inr(st_['inc'])} came in", f"You spent {inr(st_['spent'])} and kept {inr(st_['keep'])}.", "linear-gradient(135deg,#6366f1,#8b5cf6)")
    if len(cats):
        t = cats.index[0]
        top3 = ", ".join(f"{EMOJI.get(c, '')} {c}" for c in cats.head(3).index)
        c2 = (EMOJI.get(t, "🛍️"), f"{t} was your biggest spend", f"{inr(cats.iloc[0])}, which is {cats.iloc[0] / max(st_['spent'], 1) * 100:.0f}% of what you spent. Top 3: {top3}.", "linear-gradient(135deg,#f59e0b,#ef4444)")
    else:
        c2 = ("🛍️", "No spending yet", "Add a few spends and I'll show your biggest one.", "linear-gradient(135deg,#f59e0b,#ef4444)")
    drops = [(prev.get(c, 0) - v, c) for c, v in cats.items() if prev.get(c, 0) > v]
    if drops:
        dv, dc = max(drops)
        c3 = ("🏆", "Your win", f"You spent {inr(dv)} less on {dc} than last month. Nice!", "linear-gradient(135deg,#10b981,#059669)")
    elif st_["keep"] > 0:
        c3 = ("🏆", "Your win", f"You kept {inr(st_['keep'])} this month. That money is all yours!", "linear-gradient(135deg,#10b981,#059669)")
    else:
        c3 = ("🏆", "Your win", "You tracked your money this month. That's step one, and it counts 💪", "linear-gradient(135deg,#10b981,#059669)")
    d = [c for c in cats.index if c in DISC]
    if d:
        sv = cats[d[0]] * 0.2
        e1 = goal(p, s["keep"])[2]
        e2 = goal(p, s["keep"] + sv)[2]
        extra = f" Your goal would arrive {months_text(e1, e2)}" if (e1 is not None and e2 is not None and e1 > e2) else ""
        c4 = ("💡", "One tip", f"Trim {d[0]} by a fifth and you'd free up {inr(sv)} a month.{extra}", "linear-gradient(135deg,#06b6d4,#3b82f6)")
    else:
        c4 = ("💡", "One tip", "Keep adding your spends. The more I see, the better my tips get.", "linear-gradient(135deg,#06b6d4,#3b82f6)")
    return [c1, c2, c3, c4]

def review_text(st_, cards, label, p):
    lines = [f"MONEY COACH: MONTH IN REVIEW ({label})", "=" * 44,
             f"Came in: {inr(st_['inc'])}", f"Spent: {inr(st_['spent'])}", f"Kept: {inr(st_['keep'])}", "", "Where it went:"]
    lines += [f"  - {c}: {inr(v)}" for c, v in st_["cats"].items()]
    lines += ["", f"Goal: {p.goal} ({inr(p.target)} by {pretty(p.goal_date)}), saved so far {inr(p.saved)}", ""]
    lines += [f"{c[1]}: {c[2]}" for c in cards[2:]]
    lines += ["", "Educational only. This report does not recommend any specific securities."]
    return "\n".join(lines)

def review_view(tx, p, s):
    ms = sorted(tx.date.str[:7].unique(), reverse=True)
    done_m = [m for m in ms if m < s["cur"]]
    mth = st.selectbox("Which month?", ms, index=ms.index(done_m[0] if done_m else ms[0]), key="rev_m",
                       format_func=lambda m: pretty(m + "-01", "%B %Y"))
    label = pretty(mth + "-01", "%B %Y")
    stt = month_stats(tx, mth)
    cards = review_cards(stt, p, s, label)
    i = min(st.session_state.get("rev_i", 0), 3)
    em, head, body, bg = cards[i]
    H(f'<div class="story" style="background:{bg}"><div class="big">{em}</div><h2>{esc(head)}</h2><p>{esc(body)}</p></div>')
    H("<div style='text-align:center;font-size:1.3rem;margin:.4rem'>" + " ".join("●" if j == i else "○" for j in range(4)) + "</div>")
    a, b = st.columns(2)
    a.button("⬅️ Back", disabled=i == 0, use_container_width=True, on_click=lambda: st.session_state.update(rev_i=i - 1))
    b.button("Next ➡️", disabled=i == 3, type="primary", use_container_width=True, on_click=lambda: st.session_state.update(rev_i=i + 1))
    st.download_button("⬇️ Download this report", review_text(stt, cards, label, p), file_name=f"money-review-{mth}.txt", use_container_width=True)
    st.button("✖️ Close", use_container_width=True, on_click=lambda: st.session_state.update(review=False))

# ======================================================================================
# 13. ADD
# ======================================================================================
def teach_block(tx):
    skipped = st.session_state.setdefault("skipped", set())
    un = tx[tx.category == "Uncategorized"]
    todo = un[~un.id.isin(skipped)]
    if todo.empty:
        return
    r = todo.iloc[0]
    rid, guess = int(r.id), guess_cat(r.merchant)
    with st.container(border=True):
        st.markdown(f"#### 🤔 Quick question ({len(todo)} left)")
        st.markdown(f"What was **{esc(r.merchant)}** ({inr(r.amount)} on {r.date})?")
        if guess:
            st.button(f"✅ Yes, {EMOJI[guess]} {guess}", key=f"yes_{rid}", type="primary", use_container_width=True,
                      on_click=learn, args=(rid, r.merchant, guess))
        st.caption("Or pick the right one:" if guess else "Pick the closest one:")
        chips(CAT_LABELS, f"teach_{rid}")
        a, b = st.columns(2)
        a.button("💾 Save my pick", key=f"save_{rid}", use_container_width=True, on_click=learn_pick, args=(rid, r.merchant, f"teach_{rid}"))
        b.button("Skip for now", key=f"skip_{rid}", use_container_width=True, on_click=skip, args=(rid,))

def preview_block():
    pv = st.session_state.get("preview")
    if not pv:
        return
    rules = load_rules(me())
    rows = [(d, clean(m), a, "Spent" if t == "DR" else "Came in", categorize(rules, clean(m), t)[0]) for d, m, a, t in pv["rows"]]
    df = pd.DataFrame(rows, columns=["Date", "What", "₹", "In/Out", "Label"])
    with st.container(border=True):
        st.markdown(f"#### 👀 Found {len(df)} transactions {pv['note']}")
        st.caption("Have a look. Nothing is saved until you press Import (repeats are skipped automatically).")
        st.dataframe(df.head(60), hide_index=True, use_container_width=True)
        n_unc = int((df.Label == "Uncategorized").sum())
        if n_unc:
            st.caption(f"❓ {n_unc} will need a label. I'll ask you right after importing.")
        a, b = st.columns(2)
        a.button(f"✅ Import {len(df)}", type="primary", use_container_width=True, on_click=confirm_import)
        b.button("Cancel", use_container_width=True, on_click=cancel_import)

def add_page(tx):
    teach_block(tx)
    preview_block()
    
    st.markdown("### 🎙️ Speak a Transaction")
    st.caption("Press record and say something like: 'Spent 350 on Swiggy today' or 'Received 15000 salary'.")
    voice_tx = st.audio_input("Record voice transaction", key="voice_tx_input")
    if voice_tx is not None:
        if st.button("Process Voice Note 🤖", type="primary", use_container_width=True, key="proc_voice_tx"):
            with st.spinner("Listening and extracting transaction..."):
                audio_bytes = voice_tx.read()
                row = extract_voice_transaction(audio_bytes)
                if row:
                    stage_import([row], "from your voice note")
                    st.rerun()
                else:
                    st.error("I couldn't detect a valid transaction amount or type in that voice note. Try again?")
    st.divider()

    st.markdown("### ➕ I just spent something")
    with st.form("quick", clear_on_submit=True):
        amt = st.number_input("How much? (₹)", min_value=0.0, value=0.0, step=10.0, format="%.0f")
        st.caption("What was it for?")
        what = chips(list(QA), "qa_chip", list(QA)[0]) or list(QA)[0]
        note = st.text_input("Add a note (optional)", placeholder="e.g. Lunch with friends")
        when = st.date_input("When?", value=date.today(), max_value=date.today())
        if st.form_submit_button("Add it ✅", type="primary", use_container_width=True):
            if amt <= 0:
                st.error("Type an amount first, for example 120.")
            else:
                cat, typ = QA[what]
                add_one(when.isoformat(), note.strip() or cat, amt, typ, cat)
                toast(f"Added {inr(amt)} to {what} 👍")
                st.rerun()

    with st.expander("📲 More ways to add (bank SMS, statements)", expanded=bool(st.session_state.get("preview"))):
        st.markdown("**Paste bank messages** (one per line)")
        raw = st.text_area("Messages", height=120, label_visibility="collapsed",
                           placeholder="A/C XX1234 debited by INR 450.00 at Swiggy on 2026-06-01")
        tdate = st.date_input("Date to use if a message has no date", value=date.today(), max_value=date.today(), key="sms_date")
        ai_ok = get_profile(me()).ai_consent == 1 and bool(gemini_key())
        use_ai = st.checkbox("🤖 Use AI to read messy messages (only masked text is sent)", value=True) if ai_ok else False
        if not ai_ok:
            st.caption("Tip: allow AI in the 💬 Ask tab and add a GEMINI_API_KEY to read messy WhatsApp/SMS dumps.")
        if st.button("Read my messages", use_container_width=True):
            ok, bad, by_ai = [], 0, False
            masked_all = mask(raw)
            ai_rows = extract_sms_ai(masked_all) if use_ai and raw.strip() else None
            if ai_rows:
                ok, by_ai = [(d or tdate.isoformat(), m, a, t) for d, m, a, t in ai_rows], True
            else:
                for line in filter(str.strip, masked_all.splitlines()):
                    row = parse_sms(line)
                    if row:
                        ok.append((row[0] or tdate.isoformat(),) + tuple(row[1:]))
                    else:
                        bad += 1
            if ok:
                stage_import(ok, "from your messages" + (" (read with AI 🤖)" if by_ai else "")
                             + (f"; {bad} line(s) couldn't be read" if bad else ""))
                st.rerun()
            else:
                st.error("I couldn't read that. Try something like: Rs 450 spent at Swiggy")
        st.divider()
        st.markdown("**Upload a statement** (CSV or PDF)")
        st.caption("Messy files are fine: I skip junk lines, find the header row and mask account numbers / UPI ids.")
        up = st.file_uploader("Statement", type=["csv", "pdf"], label_visibility="collapsed")
        if up and st.button("Read this file", use_container_width=True):
            try:
                rows = parse_csv(read_statement_csv(up)) if up.name.lower().endswith(".csv") else parse_pdf(up)
            except ImportError:
                rows = []
                st.error("PDF reading needs one more install: pip install pdfplumber")
            except Exception as e:
                rows = []
                st.error(f"I couldn't open that file ({e}). Try exporting it as CSV.")
            if rows:
                stage_import(rows, f"in {up.name}")
                st.rerun()
            elif up:
                st.warning("I didn't find any transactions in that file.")
        st.download_button("📄 Download a sample statement to try", demo_csv_text(), file_name="demo_data.csv",
                           mime="text/csv", use_container_width=True)

# ======================================================================================
# 14. ACTIVITY
# ======================================================================================
def activity_page(tx):
    t1, t2, t3 = st.tabs(["🧾 Entries", "📊 Insights", "🧠 What I've learned"])
    with t1:
        if tx.empty:
            st.info("Nothing here yet. Add a spend in the ➕ tab.")
        else:
            f1, f2 = st.columns(2)
            months = ["All months"] + sorted(set(tx.date.str[:7]), reverse=True)
            mth = f1.selectbox("Month", months, format_func=lambda m: m if m == "All months" else pretty(m + "-01", "%B %Y"))
            catf = f2.multiselect("Labels", CATS)
            txt = st.text_input("Search", placeholder="e.g. swiggy")
            v = tx.copy()
            if mth != "All months":
                v = v[v.date.str[:7] == mth]
            if catf:
                v = v[v.category.isin(catf)]
            if txt.strip():
                v = v[v.merchant.str.contains(txt.strip(), case=False, regex=False)]
            v = v.sort_values(["date", "id"], ascending=False)
            st.caption(f"{len(v)} entries · spent {inr(spend_by_cat(v).sum())} · came in "
                       f"{inr(v[(v.type == 'CR') & (v.category == 'Income')].amount.sum())}")
            edit = v.head(200).set_index("id")[["date", "merchant", "amount", "type", "category"]].copy()
            edit["type"] = edit["type"].map({"DR": "Spent", "CR": "Came in"})
            edit["Delete"] = False
            edit.columns = ["Date", "What", "₹", "In/Out", "Label", "Delete"]
            st.caption("Change a label and press Save: I'll remember it for next time. Tick Delete to remove an entry.")
            res = st.data_editor(edit, key=f"tx_ed_{mth}_{txt}_{','.join(catf)}", hide_index=True, use_container_width=True,
                                 disabled=["Date", "What", "₹", "In/Out"],
                                 column_config={"Label": st.column_config.SelectboxColumn("Label", options=CATS, required=True),
                                                "Delete": st.column_config.CheckboxColumn("Delete")})
            a, b = st.columns(2)
            if a.button("💾 Save changes", type="primary", use_container_width=True):
                nl = nd = 0
                for rid, row in res.iterrows():
                    if row["Delete"]:
                        conn.execute("DELETE FROM tx WHERE id=? AND username=?", (int(rid), me()))
                        nd += 1
                    elif row["Label"] != edit.loc[rid, "Label"]:
                        learn(int(rid), edit.loc[rid, "What"], row["Label"], quiet=True)
                        nl += 1
                conn.commit()
                toast(f"Saved: {nl} relabelled (and remembered), {nd} deleted ✅" if nl or nd else "No changes to save")
                st.rerun()
            b.download_button("⬇️ Download these", v[["date", "merchant", "amount", "type", "category"]].to_csv(index=False),
                              file_name="my-entries.csv", mime="text/csv", use_container_width=True)
            st.button("↩️ Undo my last entry", on_click=undo_last)
    with t2:
        if tx.empty:
            st.info("Add some transactions and I'll show you patterns here.")
        else:
            insights(tx)
    with t3:
        rules_tab()

def insights(tx):
    mt = month_table(tx)
    full = mt[mt.month < date.today().strftime("%Y-%m")] if len(mt) > 1 else mt
    avg_sp, avg_in = float(full.spent.mean()), float(full.inc.mean())
    rate = (avg_in - avg_sp) / avg_in * 100 if avg_in else 0
    d = tx[(tx.type == "DR") & ~tx.category.isin(NOT_SPEND)]
    big = d.sort_values("amount", ascending=False).iloc[0] if not d.empty else None
    H('<div class="cards">' + card("Avg monthly spend", inr(avg_sp), "full months", AMBER)
      + card("Savings rate", f"{rate:.0f}%", "of what comes in", GREEN if rate >= 10 else RED)
      + card("Avg per day", inr(avg_sp / 30), "everyday average", INDIGO) + "</div>")
    if big is not None:
        st.caption(f"Biggest single spend: {inr(big.amount)} on {big.merchant} ({big.date}).")
    st.markdown("**Came in vs spent, by month**")
    df = mt.assign(Month=mt.month.map(lambda m: pretty(m + "-01", "%b %y"))).set_index("Month")
    bar_chart(df[["inc", "spent", "saved"]].rename(columns={"inc": "Came in", "spent": "Spent", "saved": "Put aside"}), [INDIGO, AMBER, GREEN])
    st.markdown("**Spending by label, month by month**")
    pv = d.assign(m=d.date.str[:7]).pivot_table(index="m", columns="category", values="amount", aggfunc="sum", fill_value=0)
    pv.index = [pretty(m + "-01", "%b %y") for m in pv.index]
    bar_chart(pv)
    ms = sorted(d.date.str[:7].unique())
    if len(ms) >= 2:
        st.markdown(f"**{pretty(ms[-1] + '-01')} vs {pretty(ms[-2] + '-01')}**")
        a, b = d[d.date.str[:7] == ms[-1]].groupby("category").amount.sum(), d[d.date.str[:7] == ms[-2]].groupby("category").amount.sum()
        cmp_ = pd.DataFrame({"This month": a, "Last month": b}).fillna(0)
        cmp_["Change"] = cmp_["This month"] - cmp_["Last month"]
        st.dataframe(cmp_.sort_values("Change", ascending=False).round(0), use_container_width=True)
    st.markdown("**Top places you spend**")
    top = d.groupby("merchant").amount.agg(["sum", "count"]).sort_values("sum", ascending=False).head(8)
    top.columns = ["Total ₹", "Times"]
    st.dataframe(top.round(0), use_container_width=True)
    st.markdown("**Which days of the week?**")
    wd = d.assign(day=pd.to_datetime(d.date).dt.day_name()).groupby("day").amount.sum()
    wd = wd.reindex(["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]).fillna(0)
    st.bar_chart(wd)

def rules_tab():
    st.caption("Every time you fix a label, I save a rule so I recognise that place next time.")
    rules = load_rules(me())
    if rules:
        for pat, cat in rules:
            a, b = st.columns([5, 1], vertical_alignment="center")
            a.markdown(f"“**{esc(pat)}**” → {EMOJI.get(cat, '')} {cat}")
            b.button("🗑️", key=f"dr_{pat}", on_click=delete_rule, args=(pat,))
        st.button("🔄 Re-check all my entries with these rules", on_click=relabel_all, use_container_width=True)
    else:
        st.info("No rules yet. Fix a label in the ➕ Add or 🧾 Entries tab and I'll start learning.")
    with st.form("newrule", clear_on_submit=True):
        st.markdown("**Teach me a new one**")
        pat = st.text_input("When the name contains…", placeholder="e.g. sharma stationers")
        cat = st.selectbox("…label it as", [c for c in CATS if c != "Uncategorized"])
        if st.form_submit_button("Save rule", use_container_width=True):
            add_rule(pat, cat)
            st.rerun()

# ======================================================================================
# 15. PLAN
# ======================================================================================
def goal_card_html(g):
    frac = g["saved"] / max(g["target"], 1)
    col = STATUS_COLOR[g["status"]]
    badge = {"green": "On track", "amber": "Behind", "red": "Not funded", "done": "Reached"}[g["status"]]
    eta = ("🎉 Goal reached!" if g["need"] == 0 else "not reachable at the moment" if g["eta"] is None
           else f"about {g['eta']} months (≈ {eta_date(g['eta'])}) if you fund goals in date order")
    return (f'<div class="gcard"><div class="t"><b>{"⭐ " if g["pinned"] else ""}{esc(g["name"])}</b>'
            f'<span class="badge" style="background:{col}">{badge}</span></div>'
            f'<div class="row"><div class="b"><span style="width:{max(2, frac * 100):.0f}%;background:{col}"></span></div>'
            f'<div class="a">{frac * 100:.0f}%</div></div>'
            f'<div class="sub">{inr(g["saved"])} of {inr(g["target"])} · by {pretty(g["date"])} · needs {inr(g["req"])}/month · {eta}</div></div>')

def goals_tab(p, s):
    plan = s["plan"]
    open_ = [g for g in plan if g["need"] > 0]
    tot = sum(g["req"] for g in open_)
    if open_:
        if tot <= s["keep"]:
            st.success(f"All your goals together need {inr(tot)} a month and you keep about {inr(s['keep'])}. You can fund them all 🎉")
        else:
            st.warning(f"All your goals together need {inr(tot)} a month, but you keep about {inr(max(s['keep'], 0))}. "
                       "I share your money out in date order, so the earliest goal gets funded first. See what-if to close the gap.")
    for g in plan:
        with st.container(border=True):
            H(goal_card_html(g))
            c1, c2, c3 = st.columns([2, 1, 1], vertical_alignment="bottom")
            c1.number_input("Add to this goal (₹)", min_value=0.0, value=0.0, step=500.0, key=f"ag_{g['id']}")
            c2.button("Add", key=f"agb_{g['id']}", use_container_width=True, on_click=add_to_goal_key, args=(g["id"], f"ag_{g['id']}"))
            c3.button("⭐ Focus", key=f"fc_{g['id']}", use_container_width=True, disabled=g["id"] == p.goal_id,
                      help="Show this goal first on Home", on_click=focus_set, args=(g["id"],))
            with st.expander("✏️ Edit or delete"):
                with st.form(f"gf_{g['id']}"):
                    gn = st.text_input("Name", value=g["name"])
                    gt = st.number_input("Cost (₹)", min_value=0.0, value=g["target"], step=1000.0)
                    gd = st.date_input("Target date", value=pd.to_datetime(g["date"]).date())
                    gs_ = st.number_input("Saved so far (₹)", min_value=0.0, value=g["saved"], step=500.0)
                    if st.form_submit_button("Save goal", use_container_width=True):
                        run("UPDATE goals SET name=?, target=?, goal_date=?, saved=? WHERE id=? AND username=?",
                            (gn, gt, str(gd), gs_, g["id"], me()))
                        toast("Goal saved 🎯")
                        st.rerun()
                st.button("🗑️ Delete this goal", key=f"dg_{g['id']}", on_click=delete_goal, args=(g["id"],))
    if p.goal_id and s["need"] > 0:
        st.markdown(f"**📈 {esc(p.goal)}: where you are vs where you need to be**")
        st.line_chart(projection_df(p, s["keep"], s["req"], s["need"]))
        st.caption("If the “At your pace” line reaches the Goal line before the “Needed” line does, you're ahead.")
    if p.goal_id:
        h = q("SELECT date, amount FROM contribs WHERE username=? AND goal_id=? ORDER BY date DESC, id DESC LIMIT 20", (me(), p.goal_id))
        if not h.empty:
            with st.expander(f"🧾 Money you've added to {p.goal}"):
                h.columns = ["Date", "₹"]
                st.dataframe(h, hide_index=True, use_container_width=True)
    with st.expander("➕ Add a new goal", expanded=not p.goal_id):
        with st.form("newgoal", clear_on_submit=True):
            n = st.text_input("What are you saving for?", placeholder="e.g. Bike")
            tg = st.number_input("How much will it cost? (₹)", min_value=0.0, value=10000.0, step=1000.0)
            dt = st.date_input("By when?", value=date.today() + timedelta(days=365), min_value=date.today())
            sv = st.number_input("Already saved (₹)", min_value=0.0, value=0.0, step=500.0)
            if st.form_submit_button("Add goal", use_container_width=True):
                if n.strip() and tg > 0:
                    first = conn.execute("SELECT 1 FROM goals WHERE username=?", (me(),)).fetchone() is None
                    run("INSERT INTO goals(username,name,target,saved,goal_date,is_primary,created) VALUES(?,?,?,?,?,?,?)",
                        (me(), n.strip(), tg, sv, str(dt), int(first), str(date.today())))
                    toast(f"New goal added: {n.strip()} 🎯")
                    st.rerun()
                else:
                    st.error("Give it a name and a cost first.")

def whatif_tab(tx, p, s, rec):
    st.caption("Tap anything you're thinking about. I'll show what it does to your goals.")
    cats = s["cat"]
    food, shop, ent = (float(cats.get(c, 0)) for c in ("Food & Dining", "Shopping", "Entertainment"))
    orders = tx[(tx.category == "Food & Dining") & (tx.type == "DR")].amount if not tx.empty else pd.Series(dtype=float)
    avg_order = float(orders.mean()) if len(orders) else 300.0
    subs = sorted([r for r in rec if r["cat"] == "Subscriptions"], key=lambda r: -r["last"])
    answers = dict(conn.execute("SELECT key, answer FROM subs WHERE username=?", (me(),)).fetchall())
    unused = sum(r["last"] for r in subs if answers.get(r["key"]) == "no")
    presets = {}
    if food > 0:
        presets["🍔 Order in 2 fewer times a week"] = min(2 * 4.3 * avg_order, food)
        presets["🍕 Cut dining out by 30%"] = food * 0.3
    if shop > 0:
        presets["🛍️ Shop half as much"] = shop * 0.5
    if ent > 0:
        presets["🎬 Halve entertainment"] = ent * 0.5
    if subs:
        presets["📺 Cancel one subscription"] = subs[0]["last"]
    if unused > 0:
        presets["✂️ Drop the subscriptions I don't use"] = unused
    presets["💼 Earn ₹2,000 extra a month"] = 2000.0
    presets["📈 Income goes up 10%"] = s["income"] * 0.1
    presets["🏠 Rent goes up ₹2,000"] = -2000.0
    sel = multi_chips(list(presets), "presets")
    with st.expander("🎚️ Fine-tune with sliders"):
        pf = st.slider("Cut dining out by (%)", 0, 100, 0, 5)
        ps = st.slider("Cut shopping by (%)", 0, 100, 0, 5)
        inc_ch = st.number_input("Extra income per month (₹, use − for less)", value=0.0, step=500.0)
        rent_ch = st.number_input("Rent change per month (₹, + means rent goes up)", value=0.0, step=500.0)
        own = st.number_input("Any other change per month (₹, use − for extra costs)", value=0.0, step=100.0)
    lump = st.number_input("One-time amount I could put towards my main goal now (₹)", min_value=0.0, value=0.0, step=500.0)
    delta = sum(presets[x] for x in sel) + food * pf / 100 + shop * ps / 100 + inc_ch - rent_ch + own
    if not (sel or delta or lump):
        st.info("Pick one of the buttons above (or use the sliders) to see what it would change 👆")
        return
    new_keep = s["keep"] + delta
    p2 = SimpleNamespace(**vars(p))
    p2.saved = p.saved + lump
    e0, e1 = s["eta"], goal(p2, new_keep)[2]
    with st.container(border=True):
        for x in sel:
            v = presets[x]
            st.markdown(f"{x} → **{'+' if v >= 0 else '−'}{inr(abs(v))}** a month")
        if pf or ps or inc_ch or rent_ch or own:
            st.markdown(f"🎚️ Fine-tuning → **{'+' if delta - sum(presets[x] for x in sel) >= 0 else '−'}"
                        f"{inr(abs(delta - sum(presets[x] for x in sel)))}** a month")
        if lump:
            st.markdown(f"💵 One-time {inr(lump)} → {p.goal}")
        st.markdown(f"**What you keep:** {inr(s['keep'])} → **{inr(new_keep)}** a month")
        if s["need"] > 0:
            f = lambda e: "never" if e is None else f"{e} months"
            st.markdown(f"**{esc(p.goal)} in:** {f(e0)} → **{f(e1)}**")
            (st.success if (e1 is not None and (e0 is None or e1 < e0)) else st.warning if (e1 is None or (e0 is not None and e1 > e0)) else st.info)(months_text(e0, e1))
    if s["need"] > 0:
        base = projection_df(p, s["keep"], s["req"], s["need"])
        alt = projection_df(p2, new_keep, s["req"], s["need"])
        st.line_chart(pd.DataFrame({"Now": base["At your pace"], "With your changes": alt["At your pace"].reindex(base.index).fillna(p.target),
                                    "Goal": base["Goal"]}))
    after = {g["id"]: g for g in goals_plan(p.goals, new_keep)}
    cmp_ = pd.DataFrame([dict(Goal=g["name"], Now=("done ✅" if g["need"] == 0 else "never" if g["eta"] is None else f"{g['eta']} mo"),
                              **{"With changes": ("done ✅" if g["need"] == 0 else "never" if after[g["id"]]["eta"] is None else f"{after[g['id']]['eta']} mo")})
                         for g in s["plan"]])
    st.markdown("**All your goals (funded in date order)**")
    st.dataframe(cmp_, hide_index=True, use_container_width=True)
    sc1, sc2 = st.columns([3, 1], vertical_alignment="bottom")
    nm = sc1.text_input("Name this scenario to save it", placeholder="e.g. Cook more + cancel Netflix", key="sc_name")
    sc2.button("💾 Save", use_container_width=True, on_click=lambda: save_scenario(st.session_state.get("sc_name", ""), delta, lump))

def saved_scenarios(p, s):
    sc = conn.execute("SELECT id,name,delta,lump FROM scenarios WHERE username=?", (me(),)).fetchall()
    if not sc:
        return
    st.markdown("**💾 Your saved scenarios**")
    for sid, name, delta, lump in sc:
        p2 = SimpleNamespace(**vars(p))
        p2.saved = p.saved + lump
        e1 = goal(p2, s["keep"] + delta)[2]
        a, b = st.columns([6, 1], vertical_alignment="center")
        a.markdown(f"**{esc(name)}** · {'+' if delta >= 0 else '−'}{inr(abs(delta))}/month"
                   + (f" + {inr(lump)} now" if lump else "") + f" → {months_text(s['eta'], e1)}")
        b.button("🗑️", key=f"ds_{sid}", on_click=delete_scenario, args=(sid,))

def limits_tab(tx, p, s):
    u = me()
    budgets = dict(conn.execute("SELECT category, limit_amt FROM budgets WHERE username=?", (u,)).fetchall())
    cur = spend_by_cat(tx[tx.date.str[:7] == s["cur"]]) if not tx.empty else pd.Series(dtype=float)
    st.caption(f"Your plan lets you spend about {inr(s['cap'])} this month overall. Limits per label help you stay inside that.")
    if budgets:
        rows = []
        for c, lim in sorted(budgets.items()):
            sp = float(cur.get(c, 0))
            col = RED if sp > lim else AMBER if sp > 0.8 * lim else GREEN
            rows.append((f"{EMOJI.get(c, '')} {c}", sp / lim * 100, f"{sp / lim * 100:.0f}%", col))
        H(bars_html(rows))
        for c, lim in sorted(budgets.items()):
            a, b = st.columns([5, 1], vertical_alignment="center")
            a.caption(f"{c}: {inr(float(cur.get(c, 0)))} of {inr(lim)} this month")
            b.button("✖️", key=f"rb_{c}", on_click=remove_budget, args=(c,))
    else:
        st.info("No limits yet. Set one below, or let me suggest some.")
    if not s["cat"].empty:
        st.button("✨ Suggest limits for me (about 10% above my usual)", use_container_width=True, on_click=auto_budgets, args=(s["cat"].to_dict(),))
    cat = st.selectbox("Set a limit for…", TOP)
    usual = float(s["cat"].get(cat, 0))
    st.number_input("Monthly limit (₹)", min_value=0.0, value=float(math.ceil(usual * 1.1 / 100) * 100) if usual else 1000.0,
                    step=100.0, key=f"lim_{cat}")
    st.button("Save limit", type="primary", use_container_width=True, on_click=set_budget_key, args=(cat, f"lim_{cat}"))

def cushion_tab(p, s):
    st.caption("A safety cushion is money for surprises (a phone repair, a medical bill) so you never need to borrow. It comes before investing.")
    months = chips(["3 months", "6 months", "9 months"], "cush_m", "3 months") or "3 months"
    n = int(months.split()[0])
    tgt = n * s["spend"]
    have = float(p.ef)
    st.progress(min(have / tgt, 1.0) if tgt else 0.0, text=f"{inr(have)} of {inr(tgt)} ({have / tgt * 100 if tgt else 0:.0f}%)")
    gap = max(tgt - have, 0)
    if gap == 0:
        st.success(f"Your cushion already covers {n} months of spending 🎉")
    else:
        st.number_input("How much could you set aside each month? (₹)", min_value=0.0, value=float(max(min(s["keep"] * 0.3, gap), 500.0)),
                        step=100.0, key="cush_m_amt")
        per = float(st.session_state.get("cush_m_amt") or 0)
        st.info(f"Still needed: {inr(gap)}. At {inr(per)} a month that takes about {math.ceil(gap / per)} months ({eta_date(math.ceil(gap / per))})."
                if per > 0 else f"Still needed: {inr(gap)}.")
    c1, c2 = st.columns([2, 1], vertical_alignment="bottom")
    c1.number_input("I added to my cushion (₹)", min_value=0.0, value=0.0, step=500.0, key="cush_add")
    c2.button("Add", use_container_width=True, on_click=add_ef_key, args=("cush_add",))

def plan_page(tx, p, s, rec):
    st.markdown("### 🎯 Goal planner")
    t1, t2, t3, t4 = st.tabs(["🎯 Goals", "🔧 What-if", "🧮 Limits", "🛟 Cushion"])
    with t1:
        goals_tab(p, s)
    with t2:
        whatif_tab(tx, p, s, rec)
        saved_scenarios(p, s)
    with t3:
        limits_tab(tx, p, s)
    with t4:
        cushion_tab(p, s)

# ======================================================================================
# 16. BILLS
# ======================================================================================
def bills_page(tx, rec):
    st.markdown("### 🔁 Bills & subscriptions")
    if not rec:
        st.info("I find monthly payments automatically once I've seen 2+ months of transactions. You can also add one by hand below.")
    else:
        live = [r for r in rec if r["status"] != "missed"]
        month_tot = sum(r["last"] for r in live)
        subs_tot = sum(r["last"] for r in live if r["cat"] == "Subscriptions")
        H('<div class="cards">' + card("Every month", inr(month_tot), f"{len(live)} regular payments", INDIGO)
          + card("Every year", inr(month_tot * 12), "if nothing changes", AMBER)
          + card("Subscriptions", inr(subs_tot * 12), f"a year ({inr(subs_tot)}/mo)", RED if subs_tot * 12 > 5000 else GREEN) + "</div>")
        answers = dict(conn.execute("SELECT key, answer FROM subs WHERE username=?", (me(),)).fetchall())
        unused = sum(r["last"] * 12 for r in live if r["cat"] == "Subscriptions" and answers.get(r["key"]) == "no")
        if unused:
            st.warning(f"✂️ You said you don't use some subscriptions. Cancelling them would save {inr(unused)} a year.")
        st.markdown("#### 📅 Next 30 days")
        nxt = sorted([r for r in live if 0 <= r["days"] <= 30], key=lambda r: r["days"])
        if nxt:
            for r in nxt:
                note = " 📈 price changed" if r["status"] == "changed" else ""
                st.markdown(f"{EMOJI.get(r['cat'], '💳')} **{esc(r['name'])}** · {r['next'].strftime('%d %b')} ({when_txt(r['days'])}) · {inr(r['last'])}{note}")
        else:
            st.caption("Nothing due in the next 30 days.")
        st.markdown("#### 🧾 All regular payments")
        for r in sorted(rec, key=lambda r: -r["last"]):
            with st.container(border=True):
                badge = {"ok": "✅ regular", "changed": "📈 price changed", "missed": "👀 didn't charge this time"}[r["status"]]
                st.markdown(f"{EMOJI.get(r['cat'], '💳')} **{esc(r['name'])}** · {inr(r['last'])}/month · {inr(r['last'] * 12)}/year")
                st.caption(f"{r['cat']} · {badge}" + (f" · was {inr(r['usual'])}" if r["status"] == "changed" else "")
                           + (" · added by you" if r["manual"] else f" · last paid {r['last_date']}"))
                if r["cat"] == "Subscriptions":
                    cur_a = answers.get(r["key"])
                    c1, c2 = st.columns(2)
                    c1.button("✅ Still using it" if cur_a != "yes" else "✅ Using it (you said)", key=f"su_y_{r['key']}", use_container_width=True,
                              on_click=answer_sub, args=(r["key"], r["name"], r["last"], "yes"))
                    c2.button("✂️ Not really" if cur_a != "no" else "✂️ Not using (you said)", key=f"su_n_{r['key']}", use_container_width=True,
                              on_click=answer_sub, args=(r["key"], r["name"], r["last"], "no"))
                if not r["manual"] and not tx.empty:
                    with st.expander("Price history"):
                        h = tx[(tx.type == "DR") & (tx.merchant.map(norm) == r["key"])].sort_values("date", ascending=False)[["date", "amount"]]
                        h.columns = ["Date", "₹"]
                        st.dataframe(h, hide_index=True, use_container_width=True)
    mine = conn.execute("SELECT id,name,amount,day,category FROM bills WHERE username=?", (me(),)).fetchall()
    if mine:
        st.markdown("#### ✍️ Bills you added")
        for bid, name, amt, day, cat in mine:
            a, b = st.columns([5, 1], vertical_alignment="center")
            a.markdown(f"{EMOJI.get(cat, '💳')} **{esc(name)}** · {inr(amt)} on day {day}")
            b.button("🗑️", key=f"db_{bid}", on_click=delete_bill, args=(bid,))
    with st.expander("➕ Track a bill myself"):
        with st.form("newbill", clear_on_submit=True):
            n = st.text_input("Name", placeholder="e.g. Hostel mess fee")
            a1, a2 = st.columns(2)
            amt = a1.number_input("Amount (₹)", min_value=0.0, value=0.0, step=100.0)
            day = a2.number_input("Day of month", min_value=1, max_value=31, value=5)
            cat = st.selectbox("Type", BILL_CATS)
            if st.form_submit_button("Track it", use_container_width=True):
                add_bill(n, amt, day, cat)
                st.rerun()

# ======================================================================================
# 17. ASK (AI GUIDE)
# ======================================================================================
STARTERS = ["Can I afford a ₹5,000 phone?", "Where am I overspending?", "How can I reach my goal faster?",
            "What bills are coming up?", "How much can I spend today?", "What is a safety cushion?"]

def ask_page(tx, p, s, rec):
    st.markdown("### 💬 Ask Money Coach")
    if p.ai_consent == 0:
        with st.container(border=True):
            st.markdown("**One quick thing before we chat 🙂**")
            st.write("To give smart answers, I may send a short summary of your numbers (totals only, no bank statements, "
                     "account numbers or UPI IDs) to Google's Gemini AI. Is that okay?")
            a, b = st.columns(2)
            a.button("✅ Yes, that's fine", type="primary", use_container_width=True, on_click=set_consent, args=(1,))
            b.button("No, basic mode", use_container_width=True, on_click=set_consent, args=(2,))
        return
    
    key = f"chat_{me()}"
    hist = st.session_state.setdefault(key, [])
    
    st.markdown("#### 🎙️ Voice Question")
    st.caption("Press record and speak your question to your money buddy.")
    voice_q = st.audio_input("Record voice question", key="voice_q_input")
    if voice_q is not None:
        if st.button("Send Voice Note to AI 🤖", type="primary", use_container_width=True, key="proc_voice_q"):
            with st.spinner("Listening to your voice note..."):
                audio_bytes = voice_q.read()
                reply, src = ask_ai_voice(audio_bytes, hist, ai_context(p, s, rec), p.ai_consent == 1, p, s, rec)
                hist += [{"role": "user", "content": "🎙️ [Voice Question]"}, {"role": "assistant", "content": reply}]
                st.rerun()
    st.divider()

    if not hist:
        st.caption("Tap a question to start, or type your own below 👇")
        cols = st.columns(2)
        for i, t in enumerate(STARTERS):
            cols[i % 2].button(t, key=f"st_{i}", use_container_width=True, on_click=ask_pending, args=(t,))
    for m in hist:
        with st.chat_message(m["role"]):
            st.write(m["content"])
    typed = st.chat_input("Ask me anything about your money…")
    question = st.session_state.pop("pending_q", None) or typed
    if question:
        with st.chat_message("user"):
            st.write(question)
        with st.chat_message("assistant"):
            with st.spinner("Thinking…"):
                reply, src = ask_ai(question, hist, ai_context(p, s, rec), p.ai_consent == 1, p, s, rec)
            st.write(reply)
            if src == "basic":
                st.caption("Basic mode answer (uses your real numbers). Add a valid GEMINI_API_KEY in secrets.toml for live AI replies.")
        hist += [{"role": "user", "content": question}, {"role": "assistant", "content": reply}]
    if hist:
        st.button("🧹 Start a new chat", on_click=lambda: st.session_state.__setitem__(key, []))
    st.caption("🛡️ I teach and model scenarios. I never recommend specific stocks, funds or other securities.")

# ======================================================================================
# 18. MAIN
# ======================================================================================
H("<style>" + CSS + "</style>")
if "_toast" in st.session_state:
    st.toast(st.session_state.pop("_toast"))

if not me():
    login_screen()
    st.stop()

user = me()
profile = get_profile(user)
if profile.onboarded == 0:
    onboarding()
    st.stop()

tx = q("SELECT * FROM tx WHERE username=? ORDER BY date, id", (user,))
rec = recurring(tx, user)
snap = snapshot(tx, profile, rec)

hc, sc = st.columns([4, 1], vertical_alignment="center")
hc.markdown(f"### Hi {display_name(user)} 👋")
with sc:
    box = st.popover("⚙️") if hasattr(st, "popover") else st.expander("⚙️ Settings")
    with box:
        settings_panel(profile, tx)

st.session_state.setdefault("nav", NAV[0])

def _nav_fix():
    if st.session_state.nav is None:
        st.session_state.nav = st.session_state.get("_nav_last", NAV[0])

if hasattr(st, "pills"):
    st.pills("Menu", NAV, selection_mode="single", key="nav", label_visibility="collapsed", on_change=_nav_fix)
else:
    st.radio("Menu", NAV, horizontal=True, key="nav", label_visibility="collapsed")
page = st.session_state.nav or NAV[0]
st.session_state["_nav_last"] = page

if profile.goal_id is None and page == NAV[0]:
    page = NAV[3]

if page == NAV[0]:
    if st.session_state.get("review") and not tx.empty:
        review_view(tx, profile, snap)
    else:
        home(tx, profile, snap, rec)
elif page == NAV[1]:
    add_page(tx)
elif page == NAV[2]:
    activity_page(tx)
elif page == NAV[3]:
    plan_page(tx, profile, snap, rec)
elif page == NAV[4]:
    bills_page(tx, rec)
else:
    ask_page(tx, profile, snap, rec)