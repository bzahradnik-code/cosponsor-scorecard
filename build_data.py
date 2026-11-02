"""Builds data.js for the cosponsor tracker site.

Setup (Windows Command Prompt):
    pip install requests
    set CONGRESS_API_KEY=your-key-here
    python build_data.py
Then open index.html (keep it in the same folder as data.js).
"""
import json, os, sys, requests

API_KEY = os.environ.get("CONGRESS_API_KEY")
if not API_KEY:
    sys.exit("Set CONGRESS_API_KEY first:  set CONGRESS_API_KEY=your-key-here")

CONGRESS = 119
BASE = "https://api.congress.gov/v3"
# (type, number). Types: hr, hres, s, sres
BILLS = [("hres", 981), ("hr", 3289), ("hr", 4642), ("hr", 9452), ("hr", 3912),
         ("hr", 5755), ("hr", 9187), ("sres", 654), ("s", 4012), ("s", 2492),
         ("s", 88), ("s", 4979)]
LABELS = {"hr": "H.R.", "hres": "H.Res.", "s": "S.", "sres": "S.Res."}
STATES = dict(x.split(" ", 1)[::-1] for x in (
    "AL Alabama,AK Alaska,AZ Arizona,AR Arkansas,CA California,CO Colorado,"
    "CT Connecticut,DE Delaware,FL Florida,GA Georgia,HI Hawaii,ID Idaho,"
    "IL Illinois,IN Indiana,IA Iowa,KS Kansas,KY Kentucky,LA Louisiana,"
    "ME Maine,MD Maryland,MA Massachusetts,MI Michigan,MN Minnesota,"
    "MS Mississippi,MO Missouri,MT Montana,NE Nebraska,NV Nevada,"
    "NH New Hampshire,NJ New Jersey,NM New Mexico,NY New York,"
    "NC North Carolina,ND North Dakota,OH Ohio,OK Oklahoma,OR Oregon,"
    "PA Pennsylvania,RI Rhode Island,SC South Carolina,SD South Dakota,"
    "TN Tennessee,TX Texas,UT Utah,VT Vermont,VA Virginia,WA Washington,"
    "WV West Virginia,WI Wisconsin,WY Wyoming,DC District of Columbia,"
    "PR Puerto Rico,GU Guam,VI Virgin Islands,AS American Samoa,"
    "MP Northern Mariana Islands").split(","))


def get(url, params=None):
    p = {"api_key": API_KEY, "format": "json"}
    p.update(params or {})
    r = requests.get(url, params=p, timeout=30)
    if r.status_code == 429:
        sys.exit("Rate limit reached (5,000 requests/hour). Try again later.")
    r.raise_for_status()
    return r.json()


def get_all(url, key, params=None):
    items, params = [], dict(params or {}, limit=250)
    while url:
        data = get(url, params)
        items += data.get(key, [])
        url, params = data.get("pagination", {}).get("next"), None
    return items


def flip(name):  # "Last, First" -> "First Last"
    if "," in name:
        last, first = name.split(",", 1)
        return f"{first.strip()} {last.strip()}"
    return name


def party(p):
    return {"Democratic": "D", "Republican": "R", "Independent": "I"}.get(p, p[:1] or "?")


members = {}


def ensure(bioguide, name="", pty="", state="", chamber="House"):
    if bioguide not in members:
        members[bioguide] = {"id": bioguide, "name": name, "party": party(pty),
                             "state": STATES.get(state, state), "chamber": chamber,
                             "supported": [], "sponsored": []}
    return members[bioguide]


print("Fetching current members...")
for m in get_all(f"{BASE}/member/congress/{CONGRESS}", "members", {"currentMember": "true"}):
    terms = (m.get("terms") or {}).get("item") or [{}]
    last = max(terms, key=lambda t: t.get("startYear", 0))
    ch = "Senate" if "Senate" in last.get("chamber", "") else "House"
    ensure(m["bioguideId"], flip(m.get("name", "")), m.get("partyName", ""),
           m.get("state", ""), ch)

bills = []
for t, n in BILLS:
    bid = f"{t}{n}"
    chamber = "House" if t.startswith("h") else "Senate"
    print(f"Fetching {LABELS[t]} {n}...")
    detail = get(f"{BASE}/bill/{CONGRESS}/{t}/{n}").get("bill", {})
    bills.append({"id": bid, "label": f"{LABELS[t]} {n}", "chamber": chamber,
                  "title": detail.get("title", "")})
    for s in detail.get("sponsors", []):
        m = ensure(s["bioguideId"], flip(s.get("fullName", "")), "", s.get("state", ""), chamber)
        m["sponsored"].append(bid)
        m["supported"].append(bid)
    cos = get_all(f"{BASE}/bill/{CONGRESS}/{t}/{n}/cosponsors", "cosponsors")
    for c in cos:
        if c.get("sponsorshipWithdrawnDate"):  # name was removed; don't count
            continue
        name = f"{c.get('firstName', '')} {c.get('lastName', '')}".strip() or c.get("fullName", "")
        m = ensure(c["bioguideId"], name, c.get("party", ""), c.get("state", ""), chamber)
        if bid not in m["supported"]:
            m["supported"].append(bid)

from datetime import date
out = {"congress": CONGRESS, "generated": date.today().isoformat(),
       "bills": bills, "members": sorted(members.values(), key=lambda m: m["name"])}
path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data.js")
with open(path, "w", encoding="utf-8") as f:
    f.write("window.CONGRESS_DATA = " + json.dumps(out, ensure_ascii=False) + ";\n")
print(f"Done. Wrote {len(out['members'])} members and {len(bills)} bills to {path}")
