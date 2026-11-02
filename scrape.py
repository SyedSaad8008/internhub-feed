"""Weekly scraper: turns public internship/event pages into one JSON feed (no paid API).

Run:
  python scrape.py                     # default keywords + cities
  python scrape.py --debug             # also saves raw HTML so you can fix selectors
  python scrape.py --details 40        # also fetch detail pages to grab "Apply by" deadlines
"""
import argparse, json, pathlib, re
import httpx
from bs4 import BeautifulSoup

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
OUT = pathlib.Path("data/feed.json")
DEFAULT_KEYWORDS = ["", "python", "web development", "marketing"]
DEFAULT_CITIES = ["hyderabad", "delhi", "mumbai"]

def get(url, tag="", debug=False):
    r = httpx.get(url, headers=UA, timeout=30, follow_redirects=True)
    r.raise_for_status()
    if debug:
        pathlib.Path(f"debug_{tag}.html").write_text(r.text, encoding="utf-8")
    return BeautifulSoup(r.text, "html.parser")

def clean(s):
    return re.sub(r"\s+", " ", s or "").strip()

def text(card, sel):
    el = card.select_one(sel)
    return clean(el.get_text()) if el else ""

def internshala(keyword=""):
    url = (f"https://internshala.com/internships/keywords-{keyword.replace(' ', '-')}/"
           if keyword else "https://internshala.com/internships/")
    soup = get(url, tag=f"internshala_{keyword or 'all'}")
    items = []
    for card in soup.select("div.individual_internship"):
        a = card.select_one("a.job-title-href")
        if not a:
            continue
        loc = clean(" ".join(x.get_text(" ") for x in card.select(".item_link"))) or \
              text(card, ".row-1-item.locations")
        items.append({
            "type": "internship",
            "title": clean(a.get_text()),
            "company": text(card, ".company-name"),
            "location": loc,
            "link": "https://internshala.com" + a.get("href", ""),
            "duration": (re.search(r"\b\d+\s*(?:Month|Week)s?\b", clean(card.get_text())) or [None]) and
                        (re.search(r"\b\d+\s*(?:Month|Week)s?\b", clean(card.get_text())).group(0)),
            "stipend": text(card, ".stipend") or None,
            "deadline": None,
            "source": "internshala",
        })
    return items

def fetch_deadlines(items, limit=40):
    """Optionally open each detail page and regex out the 'Apply by' date."""
    for it in items[:limit]:
        try:
            page = get(it["link"], tag="detail")
            m = re.search(r"[Aa]pply by\s*:?\s*([A-Za-z]{3,9}\s+\d{1,2},?\s+\d{4}|\d{1,2}\s+[A-Za-z]{3,9}\s+\d{4})", page.get_text())
            if m:
                it["deadline"] = clean(m.group(1))
        except Exception:
            pass
    return items

def allevents(city):
    """Workshops/events per city. Best-effort selectors -- verify with --debug."""
    url = f"https://allevents.in/{city}/workshops"
    soup = get(url, tag=f"allevents_{city}")
    items = []
    for card in soup.select("[class*=event-item], [class*=eventCard], article"):
        a = card.select_one("a[href]")
        title = card.select_one("h2, h3, [class*=title]")
        if not (a and title):
            continue
        items.append({
            "type": "event",
            "title": clean(title.get_text()),
            "company": text(card, "[class*=organizer], [class*=venue]") or None,
            "location": city.title(),
            "link": a.get("href", ""),
            "duration": text(card, "[class*=date], time") or None,
            "stipend": None,
            "deadline": None,
            "source": "allevents",
        })
    return items

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--details", type=int, default=0)
    ap.add_argument("--debug", action="store_true")
    args = ap.parse_args()

    items = []
    for kw in DEFAULT_KEYWORDS:
        try:
            items += internshala(kw)
        except Exception as e:
            print(f"internshala[{kw or 'all'}] failed: {e}")
    for city in DEFAULT_CITIES:
        try:
            items += allevents(city)
        except Exception as e:
            print(f"allevents[{city}] failed: {e}")

    # dedupe by link
    seen, unique = set(), []
    for it in items:
        if it["link"] and it["link"] not in seen:
            seen.add(it["link"])
            unique.append(it)
    if args.details:
        fetch_deadlines([i for i in unique if i["type"] == "internship"], args.details)

    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps({
        "updated": __import__("datetime").datetime.utcnow().isoformat(),
        "count": len(unique), "items": unique,
    }, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"wrote {OUT} with {len(unique)} items")

if __name__ == "__main__":
    main()
