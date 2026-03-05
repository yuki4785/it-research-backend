from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import json
import os
import re
from pathlib import Path

app = FastAPI(title="IT Research API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5174"],
    allow_methods=["*"],
    allow_headers=["*"],
)

RESEARCH_DIR = Path("/Users/satoyuki/dev/life/skills/plugins/it-research/research")

SOURCE_ORDER = ["はてなブックマーク", "Hacker News", "Reddit", "Aikido Security", "Wiz Research"]


def load_articles(date: str):
    path = RESEARCH_DIR / f"{date}.json"
    if not path.exists():
        raise HTTPException(status_code=404, detail="Date not found")
    return json.loads(path.read_text())


def load_summaries(date: str):
    path = RESEARCH_DIR / f"{date}-summaries.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text())


@app.get("/")
def root():
    return {"status": "ok"}


@app.get("/dates")
def list_dates():
    """利用可能な日付一覧（新しい順）"""
    dates = set()
    for f in RESEARCH_DIR.glob("????-??-??.json"):
        dates.add(f.stem)
    return sorted(dates, reverse=True)


@app.get("/articles/{date}")
def get_articles(date: str):
    """指定日の記事一覧（要約つき）をソース別に返す"""
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", date):
        raise HTTPException(status_code=400, detail="Invalid date format")

    raw = load_articles(date)
    summaries = load_summaries(date)

    result = []
    for source in raw["sources"]:
        name = source["name"]
        source_summaries = summaries.get(name, [])
        items = []
        for i, item in enumerate(source["items"]):
            items.append({
                "title": item["title"],
                "url": item["url"],
                "desc": item.get("desc", ""),
                "summary": source_summaries[i] if i < len(source_summaries) else None,
            })
        result.append({
            "name": name,
            "items": items,
            "has_summary": len(source_summaries) > 0,
        })

    # 定義順に並び替え
    result.sort(key=lambda s: SOURCE_ORDER.index(s["name"]) if s["name"] in SOURCE_ORDER else 99)

    return {"date": date, "sources": result}
