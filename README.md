# Intern Hub — Data Engine

Free, fully automated data pipeline for the **Intern Hub** Flutter app: every Sunday it
scrapes public internship and event pages and publishes one clean JSON feed that the app
fetches directly. No paid APIs, no servers, no maintenance.

**Why not LinkedIn?** LinkedIn blocks scrapers and scraping it breaks their terms of
service — that's why the Gemini-based approach kept failing. Internshala and AllEvents
are public listing pages, stable and legal to read. The app's value is *not* being a
search page: deadlines with push reminders, the tracker (saved → applied → interview),
city/stipend/duration/remote filters, and events + workshops in one place.

## Folder contents

| File | What it does |
|---|---|
| `scrape.py` | The scraper. Internships from Internshala + workshops/events per city → `data/feed.json` |
| `serve.py` | *Optional* API server (`/feed?type=&city=&q=`) if you ever want a real backend |
| `data/feed.json` | The output your Flutter app fetches |
| `.github/workflows/refresh.yml` | Runs the scraper **every Sunday automatically** on GitHub's free servers and commits the fresh feed |

## Local run (test it anytime)

```bash
pip install httpx beautifulsoup4
python scrape.py                 # default keywords + cities
python scrape.py --details 40    # also open detail pages for "Apply by" deadlines
python scrape.py --debug         # save raw HTML files for fixing selectors
```

Output shape (`data/feed.json`):

```json
{
  "updated": "2026-10-26T...",
  "count": 120,
  "items": [
    {
      "type": "internship",
      "title": "Software Development",
      "company": "TEN",
      "location": "Work from home",
      "link": "https://internshala.com/internship/detail/...",
      "duration": "1 Month",
      "stipend": "₹ 2,000 /month",
      "deadline": null,
      "source": "internshala"
    }
  ]
}
```

## Go live (do this once — ~10 minutes)

1. Create a new **public** GitHub repo (e.g. `internhub-feed`) and upload this folder.
2. Repo → **Settings → Actions → General** → allow workflows. Check the *Actions* tab:
   "weekly-refresh" will run every Sunday 02:00 UTC (≈7:30 AM IST) and commit `data/feed.json`.
   You can also press **Run workflow** to trigger it manually.
3. Repo → **Settings → Pages** → Source: *deploy from branch* → `main` / root → Save.
4. Your app's data URL is now:
   `https://<your-username>.github.io/internhub-feed/data/feed.json`
   Cost: ₹0, forever.

## Fetching it in Flutter

```dart
import 'dart:convert';
import 'package:http/http.dart' as http;

Future<List<dynamic>> loadFeed() async {
  final res = await http.get(Uri.parse(
      'https://<your-username>.github.io/internhub-feed/data/feed.json'));
  final body = jsonDecode(res.body);
  return body['items'] as List; // filter by item['type'] == 'internship' | 'event'
}
```

Store `updated` so you can show "last refreshed" in the UI. Cache the JSON locally
(`shared_preferences` or a file) so the app works offline.

## Optional: run the API server instead

```bash
pip install fastapi uvicorn
uvicorn serve:app --port 8000     # then GET http://localhost:8000/feed?city=hyderabad&q=python
```

## Customising

- **Keywords / cities** — edit `DEFAULT_KEYWORDS` and `DEFAULT_CITIES` at the top of `scrape.py`
  (e.g. add `"data science"`, `"graphic design"`, or cities like `"pune"`, `"bangalore"`).
- **Events source** — `allevents()` is best-effort. Run `python scrape.py --debug`, open
  `debug_allevents_<city>.html`, and if titles/links look wrong, adjust the CSS selectors
  in that function.
- **More sources later** — Unstop (hackathons), Naukri (jobs), Wellfound (startups) can be
  added as new functions following the same pattern; each writes items with `type` and `source`.

## Troubleshooting

- **Count suddenly 0 / small** — the site changed its HTML. Run `--debug`, compare class
  names in the saved HTML with the selectors in `scrape.py`, update them.
- **GitHub Action failed** — open the Actions tab, read the log; usually a selector fix
  (above) or a network hiccup. Just re-run.
- **Rate limiting** — the scraper hits ~5 pages per run, once a week. If you add many more
  keywords, keep the total under ~15 requests per run.

## Legal note

Reads publicly visible listing pages at human-ish volume (a few requests weekly), stores
only listing metadata, and links back to the original source. Don't add LinkedIn or
login-walled pages to the scraper.

## Roadmap ideas

- Firebase Cloud Messaging reminders X days before each `deadline`
- Telegram bot that posts the weekly digest to student groups (free growth)
- Paid tier gates: reminders + tracker sync, while browsing stays free
