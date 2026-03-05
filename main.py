from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from contextlib import contextmanager
import json
import re
import sqlite3
from pathlib import Path
from typing import Optional

app = FastAPI(title="IT Research API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5174"],
    allow_methods=["*"],
    allow_headers=["*"],
)

RESEARCH_DIR = Path("/Users/satoyuki/dev/life/skills/plugins/it-research/research")
DB_PATH = "/Users/satoyuki/dev/it-research-backend/research.db"

SOURCE_ORDER = ["はてなブックマーク", "Hacker News", "Reddit", "Aikido Security", "Wiz Research"]


@contextmanager
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with get_db() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS articles (
                id       INTEGER PRIMARY KEY AUTOINCREMENT,
                date     TEXT NOT NULL,
                source   TEXT NOT NULL,
                title    TEXT NOT NULL,
                url      TEXT NOT NULL,
                desc     TEXT DEFAULT '',
                summary  TEXT,
                UNIQUE(date, source, url)
            );
            CREATE INDEX IF NOT EXISTS idx_date ON articles(date);
        """)


def sync_json_to_db(date: str):
    """JSON ファイル1日分を DB に取り込む（重複はスキップ）"""
    articles_path = RESEARCH_DIR / f"{date}.json"
    summaries_path = RESEARCH_DIR / f"{date}-summaries.json"

    if not articles_path.exists():
        return 0

    raw = json.loads(articles_path.read_text())
    summaries = json.loads(summaries_path.read_text()) if summaries_path.exists() else {}

    inserted = 0
    with get_db() as conn:
        for source in raw["sources"]:
            name = source["name"]
            source_summaries = summaries.get(name, [])
            for i, item in enumerate(source["items"]):
                try:
                    conn.execute(
                        "INSERT OR IGNORE INTO articles (date, source, title, url, desc, summary) VALUES (?,?,?,?,?,?)",
                        (date, name, item["title"], item["url"],
                         item.get("desc", ""),
                         source_summaries[i] if i < len(source_summaries) else None)
                    )
                    inserted += conn.execute("SELECT changes()").fetchone()[0]
                except Exception:
                    pass
    return inserted


init_db()


# ---------- Models ----------

class SyncRequest(BaseModel):
    date: str


# ---------- Routes ----------

@app.get("/")
def root():
    return {"status": "ok"}


@app.get("/dates")
def list_dates():
    """利用可能な日付一覧（新しい順）"""
    with get_db() as conn:
        rows = conn.execute(
            "SELECT DISTINCT date FROM articles ORDER BY date DESC"
        ).fetchall()
    return [r["date"] for r in rows]


@app.get("/months")
def list_months():
    """月別の日付一覧 { '2026-03': ['2026-03-05', ...] }"""
    with get_db() as conn:
        rows = conn.execute(
            "SELECT DISTINCT date FROM articles ORDER BY date DESC"
        ).fetchall()

    months: dict = {}
    for r in rows:
        month = r["date"][:7]  # YYYY-MM
        months.setdefault(month, [])
        months[month].append(r["date"])
    return months


@app.get("/articles/{date}")
def get_articles(date: str):
    """指定日の記事一覧（要約つき）をソース別に返す"""
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", date):
        raise HTTPException(status_code=400, detail="Invalid date format")

    with get_db() as conn:
        rows = conn.execute(
            "SELECT source, title, url, desc, summary FROM articles WHERE date=? ORDER BY id",
            (date,)
        ).fetchall()

    if not rows:
        raise HTTPException(status_code=404, detail="Date not found")

    sources: dict = {}
    for r in rows:
        sources.setdefault(r["source"], []).append({
            "title": r["title"],
            "url": r["url"],
            "desc": r["desc"],
            "summary": r["summary"],
        })

    result = [
        {"name": name, "items": items, "has_summary": any(a["summary"] for a in items)}
        for name, items in sources.items()
    ]
    result.sort(key=lambda s: SOURCE_ORDER.index(s["name"]) if s["name"] in SOURCE_ORDER else 99)

    return {"date": date, "sources": result}


@app.post("/sync")
def sync_date(body: SyncRequest):
    """JSON ファイルを DB に同期する（it-research スキルから呼ぶ）"""
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", body.date):
        raise HTTPException(status_code=400, detail="Invalid date format")
    inserted = sync_json_to_db(body.date)
    return {"ok": True, "inserted": inserted, "date": body.date}


@app.post("/sync/all")
def sync_all():
    """research ディレクトリの全 JSON を DB に一括インポート"""
    results = {}
    for f in sorted(RESEARCH_DIR.glob("????-??-??.json")):
        date = f.stem
        inserted = sync_json_to_db(date)
        results[date] = inserted
    return {"ok": True, "results": results}
