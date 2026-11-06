"""Weekly scraper: turns public internship/event pages into one JSON feed (no paid API).

Run:
  python scrape.py                     # default keywords + cities
  python scrape.py --pages 3           # fetch 3 pages per keyword (more internships)
  python scrape.py --debug             # also saves raw HTML so you can fix selectors
  python scrape.py --details 40        # also fetch detail pages to grab "Apply by" deadlines
"""
import argparse, json, pathlib, re
import httpx
from bs4 import BeautifulSoup

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
OUT = pathlib.Path("data/feed.json")

# One keyword/page ≈ 40 internships. 8 keywords × 2 pages ≈ up to 500+ unique
# listings per weekly run. Keep the total budget sane (~30 listing requests).
DEFAULT_KEYWORDS = [
    "python",
    "web development",
    "data science",
    "machine learning",
    "marketing",
    "graphic design",
    "android",
    "content writing",
]
# Cities used for events (AllEvents + Eventbrite). "online" = virtual events.
DEFAULT_CITIES = ["hyderabad", "bangalore", "delhi", "mumbai", "pune", "chennai", "online"]


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


# ─── Internships: Internshala ────────────────────────────────────────────────

def internshala(keyword, pages=1):
    items = []
    for page in range(1, pages + 1):
        slug = keyword.replace(" ", "-")
        url = (f"https://internshala.com/internships/keywords-{slug}/"
               if page == 1
               else f"https://internshala.com/internships/keywords-{slug}/page-{page}/")
        soup = get(url, tag=f"internshala_{slug}_{page}")
        cards = soup.select("div.individual_internship")
        if not cards:
            break  # ran past the last page
        for card in cards:
            a = card.select_one("a.job-title-href")
            if not a:
                continue
            loc = clean(" ".join(x.get_text(" ") for x in card.select(".item_link"))) or \
                  text(card, ".row-1-item.locations")
            body = clean(card.get_text())
            m = re.search(r"\b\d+\s*(?:Month|Week)s?\b", body)
            items.append({
                "type": "internship",
                "title": clean(a.get_text()),
                "company": text(card, ".company-name"),
                "location": loc,
                "link": "https://internshala.com" + a.get("href", ""),
                "duration": m.group(0) if m else None,
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


# ─── Events: AllEvents.in ────────────────────────────────────────────────────

# AllEvents uses some non-obvious city slugs — map ours to theirs.
ALLEVENTS_SLUGS = {"pune": "puneindia"}


def allevents(city):
    """Workshops/events per city. Cards are <li.event-card> with data-* attrs."""
    url = f"https://allevents.in/{ALLEVENTS_SLUGS.get(city, city)}/workshops"
    soup = get(url, tag=f"allevents_{city}")
    items = []
    for card in soup.select("li.event-card"):
        link = card.get("data-link") or ""
        title = card.get("data-name") or ""
        a = card.select_one("a[href]")
        if not link and a:
            link = a.get("href", "")
        if not title:
            t = a.select_one("h3, h2, .title") if a else card.select_one("h3, h2, .title")
            title = clean(t.get_text()) if t else ""
        if not (link and title):
            continue
        date_text = text(card, "[class*=date]") or None
        price = text(card, "[class*=price]").lower()
        is_free = True if "free" in price else (False if re.search(r"(inr|₹|\d)", price) else None)
        items.append({
            "type": "event",
            "title": title,
            "company": text(card, "[class*=organizer], [class*=venue]") or None,
            "location": city.title() if city != "online" else "Online",
            "link": link,
            "duration": date_text,
            "stipend": None,
            "deadline": None,
            "is_free": is_free,
            "source": "allevents",
        })
    return items


# ─── Events: Eventbrite (JSON-LD embedded in the listing page) ───────────────

def eventbrite(city):
    """Eventbrite server-renders a schema.org ItemList — parse it directly."""
    url = f"https://www.eventbrite.com/d/india--{city}/workshops--all/"
    if city == "online":
        url = "https://www.eventbrite.com/d/online/workshops--all/"
    soup = get(url, tag=f"eventbrite_{city}")
    items = []
    for s in soup.select('script[type="application/ld+json"]'):
        try:
            data = json.loads(s.string)
        except Exception:
            continue
        if not (isinstance(data, dict) and data.get("@type") == "ItemList"):
            continue
        for entry in data.get("itemListElement", []):
            ev = entry.get("item") or {}
            link = ev.get("url") or ""
            title = clean(ev.get("name") or "")
            if not (link and title):
                continue
            online = "OnlineEventAttendanceMode" in str(ev.get("eventAttendanceMode", ""))
            loc = ((ev.get("location") or {}).get("name")) or None
            organizer = ((ev.get("organizer") or {}).get("name")) or None
            start = ev.get("startDate")
            end = ev.get("endDate")
            if start and end:
                duration = f"{start} to {end}"
            else:
                duration = start
            items.append({
                "type": "event",
                "title": title,
                "company": organizer or "Organizer TBA",
                "location": loc if loc and not online else "Online",
                "link": link,
                "duration": duration,
                "stipend": None,
                "deadline": None,
                "source": "eventbrite",
            })
    return items


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pages", type=int, default=2, help="Internshala pages per keyword")
    ap.add_argument("--details", type=int, default=0)
    ap.add_argument("--debug", action="store_true")
    args = ap.parse_args()

    items = []
    for kw in DEFAULT_KEYWORDS:
        try:
            items += internshala(kw, args.pages)
        except Exception as e:
            print(f"internshala[{kw}] failed: {e}")
    for city in DEFAULT_CITIES:
        for source, fn in (("allevents", allevents), ("eventbrite", eventbrite)):
            try:
                got = fn(city)
                items += got
                print(f"{source}[{city}]: {len(got)} events")
            except Exception as e:
                print(f"{source}[{city}] failed: {e}")

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
        "updated": __import__("datetime").datetime.now().isoformat(),
        "count": len(unique), "items": unique,
    }, indent=1, ensure_ascii=False), encoding="utf-8")
    n_int = sum(1 for i in unique if i["type"] == "internship")
    n_ev = sum(1 for i in unique if i["type"] == "event")
    print(f"wrote {OUT} with {len(unique)} items ({n_int} internships, {n_ev} events)")


if __name__ == "__main__":
    main()
