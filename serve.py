"""Tiny API over the scraped feed (optional -- your Flutter app can also just
fetch the raw JSON from GitHub Pages). Run:  uvicorn serve:app --port 8000
"""
import json, pathlib
from fastapi import FastAPI, Query

app = FastAPI(title="Intern Hub Feed API")

def load():
    p = pathlib.Path(__file__).parent / "data" / "feed.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {"items": [], "updated": None}

@app.get("/feed")
def feed(type: str = Query(None), city: str = Query(None), q: str = Query(None)):
    items = load()["items"]
    if type:
        items = [i for i in items if i["type"] == type]
    if city:
        c = city.lower()
        items = [i for i in items if c in (i["location"] or "").lower()]
    if q:
        needle = q.lower()
        items = [i for i in items if needle in (i["title"] or "").lower()
                 or needle in (i["company"] or "").lower()]
    return {"count": len(items), "items": items}

@app.get("/health")
def health():
    d = load()
    return {"ok": True, "updated": d.get("updated"), "total": len(d.get("items", []))}
