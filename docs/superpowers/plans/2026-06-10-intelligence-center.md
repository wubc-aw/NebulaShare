# Intelligence Center (情报站) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a multi-source intelligence aggregation system with Hermes daily news, RSS subscriptions, and manual article entry — backed by SQLite, served by Flask, rendered by Next.js.

**Architecture:** SQLite database (`~/.config/nebulashare/intel.db`) stores all articles from three sources. Two Python modules (`intel_db.py` for data access, `intel_sync.py` for collectors) are imported by `app.py` which registers the API routes. The frontend uses a new `components/intel/` directory with modular React components feeding into `/intel` and `/intel/sources` pages.

**Tech Stack:** Flask + SQLite + feedparser + beautifulsoup4 + Flask-APScheduler (backend) / Next.js + React + Tailwind + shadcn + react-markdown (frontend)

---

## File Structure

### New backend files
- `intel_db.py` — Database init, connection pool, all CRUD operations for sources/articles/tags
- `intel_sync.py` — Hermes HTML parser, RSS collector, URL scraper for manual entry
- `tests/test_intel.py` — pytest tests for database layer

### Modified backend files
- `app.py` — Import `intel_db`/`intel_sync`, add `/api/intel/*` routes (inserted before Daily News section at line 1181)
- `requirements.txt` — Add feedparser, beautifulsoup4, Flask-APScheduler, lxml

### New frontend files
- `components/intel/article-list.tsx` — Virtual/scrollable article list with selection
- `components/intel/article-list-item.tsx` — Single article card (title, meta, tags, quick actions)
- `components/intel/article-reader.tsx` — Right-side reading pane with action bar
- `components/intel/search-bar.tsx` — Search input + filter toggles
- `components/intel/tag-selector.tsx` — Popover for adding/removing tags on an article
- `components/intel/article-form.tsx` — Modal for manual article entry (URL scrape or manual)
- `components/intel/source-manager.tsx` — Source list with status/error display
- `components/intel/source-form.tsx` — Form for adding/editing RSS sources
- `components/intel/sync-button.tsx` — Manual sync trigger with spinner state
- `app/intel/sources/page.tsx` — Source management page

### Modified frontend files
- `app/intel/page.tsx` — Complete rewrite: list + reader layout
- `components/intelligence-center.tsx` — Delete (replaced by new components)
- `app/page.tsx` — Update Dashboard intelligence card to use new `/api/intel/articles` endpoint
- `package.json` — Add react-markdown dependency

---

## Phase 1: Data Layer + Hermes Integration (P0)

### Task 1: Install new Python dependencies

**Files:**
- Modify: `requirements.txt`

- [ ] **Step 1: Add dependencies**

Add to `requirements.txt`:

```text
feedparser>=6.0.0
beautifulsoup4>=4.12.0
Flask-APScheduler>=1.13.0
lxml>=4.9.0
```

- [ ] **Step 2: Install**

Run:
```bash
source venv/bin/activate
pip install feedparser beautifulsoup4 Flask-APScheduler lxml
```

Expected: packages installed successfully.

- [ ] **Step 3: Commit**

```bash
git add requirements.txt
git commit -m "deps: add feedparser, beautifulsoup4, Flask-APScheduler, lxml for intel center"
```

---

### Task 2: Create database module `intel_db.py`

**Files:**
- Create: `intel_db.py`

- [ ] **Step 1: Write `intel_db.py` with schema init and connection helper**

```python
"""NebulaShare Intelligence Center — SQLite database layer."""

import os
import sqlite3
import hashlib
import json
from datetime import datetime, timezone
from contextlib import contextmanager
from typing import Any

# ── Config ──────────────────────────────────────────────────────────
NEBULA_STATE_DIR = os.environ.get("NEBULA_STATE_DIR",
                                  os.path.expanduser("~/.config/nebulashare"))
INTEL_DB_PATH = os.path.join(NEBULA_STATE_DIR, "intel.db")


def _ensure_dir() -> None:
    os.makedirs(NEBULA_STATE_DIR, exist_ok=True)


@contextmanager
def _conn():
    _ensure_dir()
    conn = sqlite3.connect(INTEL_DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ── Schema ──────────────────────────────────────────────────────────
SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS sources (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    type TEXT NOT NULL CHECK(type IN ('hermes', 'rss', 'manual')),
    url TEXT,
    config TEXT,
    is_active BOOLEAN DEFAULT 1,
    last_fetch_at TEXT,
    last_error TEXT,
    error_count INTEGER DEFAULT 0,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS articles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id INTEGER NOT NULL,
    external_id TEXT,
    title TEXT NOT NULL,
    summary TEXT,
    content TEXT,
    url TEXT,
    author TEXT,
    published_at TEXT,
    category TEXT,
    is_read BOOLEAN DEFAULT 0,
    is_starred BOOLEAN DEFAULT 0,
    is_archived BOOLEAN DEFAULT 0,
    fetched_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (source_id) REFERENCES sources(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS tags (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    color TEXT DEFAULT '#3b82f6'
);

CREATE TABLE IF NOT EXISTS article_tags (
    article_id INTEGER NOT NULL,
    tag_id INTEGER NOT NULL,
    PRIMARY KEY (article_id, tag_id),
    FOREIGN KEY (article_id) REFERENCES articles(id) ON DELETE CASCADE,
    FOREIGN KEY (tag_id) REFERENCES tags(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_articles_source ON articles(source_id);
CREATE INDEX IF NOT EXISTS idx_articles_category ON articles(category);
CREATE INDEX IF NOT EXISTS idx_articles_published ON articles(published_at DESC);
CREATE INDEX IF NOT EXISTS idx_articles_starred ON articles(is_starred) WHERE is_starred = 1;
CREATE INDEX IF NOT EXISTS idx_articles_archived ON articles(is_archived) WHERE is_archived = 0;
"""

CATEGORIES = ["AI", "互联网", "金融", "创投", "工具", "阅读"]

DEFAULT_TAGS = [
    ("必读", "#ef4444"),
    ("稍后读", "#f59e0b"),
    ("项目参考", "#3b82f6"),
    ("投资相关", "#22c55e"),
]


def init_db() -> None:
    """Create tables, seed default sources and tags."""
    with _conn() as conn:
        conn.executescript(SCHEMA_SQL)

        # Seed Hermes source
        conn.execute("""
            INSERT OR IGNORE INTO sources (id, name, type, url, config)
            VALUES (1, 'Hermes 播报', 'hermes', '', '{}')
        """)
        # Seed manual source
        conn.execute("""
            INSERT OR IGNORE INTO sources (id, name, type, url, config)
            VALUES (2, '手动录入', 'manual', '', '{}')
        """)

        # Seed default tags
        for name, color in DEFAULT_TAGS:
            conn.execute(
                "INSERT OR IGNORE INTO tags (name, color) VALUES (?, ?)",
                (name, color)
            )


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {k: row[k] for k in row.keys()}
```

- [ ] **Step 2: Add source CRUD to `intel_db.py`**

Append to `intel_db.py`:

```python
# ── Sources ─────────────────────────────────────────────────────────

def list_sources() -> list[dict]:
    with _conn() as conn:
        rows = conn.execute("""
            SELECT s.*, COUNT(a.id) as article_count
            FROM sources s
            LEFT JOIN articles a ON a.source_id = s.id
            GROUP BY s.id
            ORDER BY s.id
        """).fetchall()
        return [_row_to_dict(r) for r in rows]


def get_source(source_id: int) -> dict | None:
    with _conn() as conn:
        row = conn.execute("SELECT * FROM sources WHERE id = ?", (source_id,)).fetchone()
        return _row_to_dict(row) if row else None


def create_source(name: str, type_: str, url: str = "", config: dict | None = None,
                  category: str = "") -> dict:
    with _conn() as conn:
        cur = conn.execute("""
            INSERT INTO sources (name, type, url, config, last_fetch_at)
            VALUES (?, ?, ?, ?, ?)
        """, (name, type_, url, json.dumps(config or {}), _now()))
        return get_source(cur.lastrowid)


def update_source(source_id: int, **fields) -> dict | None:
    allowed = {"name", "url", "config", "is_active", "category", "last_fetch_at", "last_error", "error_count"}
    updates = {k: v for k, v in fields.items() if k in allowed}
    if not updates:
        return get_source(source_id)
    with _conn() as conn:
        sets = ", ".join(f"{k} = ?" for k in updates)
        vals = list(updates.values()) + [source_id]
        conn.execute(f"UPDATE sources SET {sets} WHERE id = ?", vals)
        return get_source(source_id)


def delete_source(source_id: int) -> bool:
    with _conn() as conn:
        cur = conn.execute("DELETE FROM sources WHERE id = ?", (source_id,))
        return cur.rowcount > 0
```

- [ ] **Step 3: Add article CRUD to `intel_db.py`**

Append to `intel_db.py`:

```python
# ── Articles ────────────────────────────────────────────────────────

def list_articles(category: str | None = None, tag: str | None = None,
                  search: str | None = None, starred: bool | None = None,
                  unread: bool | None = None, archived: bool = False,
                  source_id: int | None = None,
                  page: int = 1, per_page: int = 20) -> tuple[list[dict], int]:
    conditions = ["1=1"]
    params: list[Any] = []

    if not archived:
        conditions.append("a.is_archived = 0")
    if category:
        conditions.append("a.category = ?")
        params.append(category)
    if starred is not None:
        conditions.append("a.is_starred = ?")
        params.append(1 if starred else 0)
    if unread is not None:
        conditions.append("a.is_read = ?")
        params.append(0 if unread else 1)
    if source_id:
        conditions.append("a.source_id = ?")
        params.append(source_id)
    if search:
        conditions.append("(a.title LIKE ? OR a.summary LIKE ? OR a.content LIKE ?)")
        like = f"%{search}%"
        params.extend([like, like, like])

    where_clause = " AND ".join(conditions)

    with _conn() as conn:
        count_row = conn.execute(f"""
            SELECT COUNT(*) FROM articles a WHERE {where_clause}
        """, params).fetchone()
        total = count_row[0] if count_row else 0

        offset = (page - 1) * per_page
        rows = conn.execute(f"""
            SELECT a.*, s.name as source_name
            FROM articles a
            JOIN sources s ON s.id = a.source_id
            WHERE {where_clause}
            ORDER BY a.published_at DESC
            LIMIT ? OFFSET ?
        """, params + [per_page, offset]).fetchall()

        articles = []
        for r in rows:
            d = _row_to_dict(r)
            d["tags"] = get_article_tags(d["id"])
            articles.append(d)
        return articles, total


def get_article(article_id: int) -> dict | None:
    with _conn() as conn:
        row = conn.execute("""
            SELECT a.*, s.name as source_name
            FROM articles a
            JOIN sources s ON s.id = a.source_id
            WHERE a.id = ?
        """, (article_id,)).fetchone()
        if not row:
            return None
        d = _row_to_dict(row)
        d["tags"] = get_article_tags(article_id)
        return d


def create_article(source_id: int, title: str, summary: str = "", content: str = "",
                   url: str = "", author: str = "", published_at: str | None = None,
                   category: str = "", external_id: str | None = None) -> dict:
    if published_at is None:
        published_at = _now()
    with _conn() as conn:
        cur = conn.execute("""
            INSERT INTO articles
            (source_id, external_id, title, summary, content, url, author, published_at, category)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (source_id, external_id, title, summary, content, url, author, published_at, category))
        return get_article(cur.lastrowid)


def update_article(article_id: int, **fields) -> dict | None:
    allowed = {"title", "summary", "content", "url", "author", "category",
               "is_read", "is_starred", "is_archived"}
    updates = {k: v for k, v in fields.items() if k in allowed}
    if not updates:
        return get_article(article_id)
    with _conn() as conn:
        sets = ", ".join(f"{k} = ?" for k in updates)
        vals = list(updates.values()) + [article_id]
        conn.execute(f"UPDATE articles SET {sets} WHERE id = ?", vals)
        return get_article(article_id)


def delete_article(article_id: int) -> bool:
    with _conn() as conn:
        cur = conn.execute("DELETE FROM articles WHERE id = ?", (article_id,))
        return cur.rowcount > 0


def article_exists(source_id: int, external_id: str) -> bool:
    with _conn() as conn:
        row = conn.execute("""
            SELECT 1 FROM articles WHERE source_id = ? AND external_id = ?
        """, (source_id, external_id)).fetchone()
        return row is not None
```

- [ ] **Step 4: Add tags to `intel_db.py`**

Append to `intel_db.py`:

```python
# ── Tags ────────────────────────────────────────────────────────────

def list_tags() -> list[dict]:
    with _conn() as conn:
        rows = conn.execute("""
            SELECT t.*, COUNT(at.article_id) as usage_count
            FROM tags t
            LEFT JOIN article_tags at ON at.tag_id = t.id
            GROUP BY t.id
            ORDER BY usage_count DESC, t.name
        """).fetchall()
        return [_row_to_dict(r) for r in rows]


def get_tag(tag_id: int) -> dict | None:
    with _conn() as conn:
        row = conn.execute("SELECT * FROM tags WHERE id = ?", (tag_id,)).fetchone()
        return _row_to_dict(row) if row else None


def create_tag(name: str, color: str = "#3b82f6") -> dict:
    with _conn() as conn:
        cur = conn.execute(
            "INSERT INTO tags (name, color) VALUES (?, ?)",
            (name, color)
        )
        return get_tag(cur.lastrowid)


def delete_tag(tag_id: int) -> bool:
    with _conn() as conn:
        cur = conn.execute("DELETE FROM tags WHERE id = ?", (tag_id,))
        return cur.rowcount > 0


# ── Article-Tag associations ────────────────────────────────────────

def get_article_tags(article_id: int) -> list[dict]:
    with _conn() as conn:
        rows = conn.execute("""
            SELECT t.* FROM tags t
            JOIN article_tags at ON at.tag_id = t.id
            WHERE at.article_id = ?
            ORDER BY t.name
        """, (article_id,)).fetchall()
        return [_row_to_dict(r) for r in rows]


def set_article_tags(article_id: int, tag_ids: list[int]) -> None:
    with _conn() as conn:
        conn.execute("DELETE FROM article_tags WHERE article_id = ?", (article_id,))
        for tag_id in tag_ids:
            conn.execute(
                "INSERT OR IGNORE INTO article_tags (article_id, tag_id) VALUES (?, ?)",
                (article_id, tag_id)
            )


def add_article_tag(article_id: int, tag_id: int) -> None:
    with _conn() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO article_tags (article_id, tag_id) VALUES (?, ?)",
            (article_id, tag_id)
        )


def remove_article_tag(article_id: int, tag_id: int) -> None:
    with _conn() as conn:
        conn.execute(
            "DELETE FROM article_tags WHERE article_id = ? AND tag_id = ?",
            (article_id, tag_id)
        )
```

- [ ] **Step 5: Add stats to `intel_db.py`**

Append to `intel_db.py`:

```python
# ── Stats ───────────────────────────────────────────────────────────

def get_stats() -> dict:
    with _conn() as conn:
        total = conn.execute("SELECT COUNT(*) FROM articles").fetchone()[0]
        unread = conn.execute("SELECT COUNT(*) FROM articles WHERE is_read = 0 AND is_archived = 0").fetchone()[0]
        starred = conn.execute("SELECT COUNT(*) FROM articles WHERE is_starred = 1").fetchone()[0]

        cat_rows = conn.execute("""
            SELECT category, COUNT(*) as count FROM articles
            WHERE is_archived = 0 GROUP BY category ORDER BY count DESC
        """).fetchall()
        category_breakdown = {r[0] or "未分类": r[1] for r in cat_rows}

        src_rows = conn.execute("""
            SELECT s.name, COUNT(a.id) as count
            FROM sources s
            LEFT JOIN articles a ON a.source_id = s.id
            GROUP BY s.id ORDER BY count DESC
        """).fetchall()
        source_breakdown = [{"name": r[0], "count": r[1]} for r in src_rows]

        return {
            "total_articles": total,
            "unread_count": unread,
            "starred_count": starred,
            "category_breakdown": category_breakdown,
            "source_breakdown": source_breakdown,
        }
```

- [ ] **Step 6: Commit database module**

```bash
git add intel_db.py
git commit -m "feat(intel): add SQLite database layer for intelligence center"
```

---

### Task 3: Test database layer

**Files:**
- Create: `tests/test_intel.py`

- [ ] **Step 1: Create test file**

```python
"""Tests for intel_db.py."""

import os
import sys
import tempfile
import pytest

# Point at repo root so intel_db imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import intel_db as db


@pytest.fixture(autouse=True)
def temp_db(monkeypatch):
    """Use a temp DB for every test."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path = f.name
    monkeypatch.setattr(db, "INTEL_DB_PATH", path)
    db.init_db()
    yield
    os.unlink(path)


def test_init_db_creates_tables():
    sources = db.list_sources()
    assert len(sources) == 2  # hermes + manual
    assert sources[0]["name"] == "Hermes 播报"
    assert sources[1]["name"] == "手动录入"


def test_create_and_get_source():
    s = db.create_source("Test RSS", "rss", "https://example.com/feed")
    assert s["name"] == "Test RSS"
    assert s["type"] == "rss"
    got = db.get_source(s["id"])
    assert got["url"] == "https://example.com/feed"


def test_create_article():
    art = db.create_article(
        source_id=1, title="Test Article", summary="Summary",
        url="https://example.com/article", category="AI"
    )
    assert art["title"] == "Test Article"
    assert art["category"] == "AI"
    assert art["source_name"] == "Hermes 播报"
    assert art["tags"] == []

    got = db.get_article(art["id"])
    assert got["title"] == "Test Article"


def test_list_articles_pagination():
    for i in range(5):
        db.create_article(source_id=1, title=f"Article {i}", category="AI")
    arts, total = db.list_articles(per_page=2, page=1)
    assert len(arts) == 2
    assert total == 5


def test_article_tags():
    art = db.create_article(source_id=1, title="Tagged")
    tag = db.create_tag("重要", "#ff0000")
    db.add_article_tag(art["id"], tag["id"])

    got = db.get_article(art["id"])
    assert len(got["tags"]) == 1
    assert got["tags"][0]["name"] == "重要"

    db.set_article_tags(art["id"], [])
    got2 = db.get_article(art["id"])
    assert got2["tags"] == []


def test_search_articles():
    db.create_article(source_id=1, title="Python news", summary="about python")
    db.create_article(source_id=1, title="Rust news", summary="about rust")
    arts, total = db.list_articles(search="python")
    assert total == 1
    assert arts[0]["title"] == "Python news"


def test_update_article():
    art = db.create_article(source_id=1, title="Old")
    updated = db.update_article(art["id"], is_read=1, is_starred=1)
    assert updated["is_read"] == 1
    assert updated["is_starred"] == 1


def test_stats():
    db.create_article(source_id=1, title="A1", category="AI")
    db.create_article(source_id=1, title="A2", category="AI")
    db.create_article(source_id=1, title="A3", category="金融")
    stats = db.get_stats()
    assert stats["total_articles"] == 3
    assert stats["category_breakdown"]["AI"] == 2
    assert stats["category_breakdown"]["金融"] == 1
```

- [ ] **Step 2: Install pytest and run tests**

```bash
source venv/bin/activate
pip install pytest
python -m pytest tests/test_intel.py -v
```

Expected: 8 tests, all PASS.

- [ ] **Step 3: Commit**

```bash
git add tests/test_intel.py
git commit -m "test(intel): add pytest suite for database layer"
```

---

### Task 4: Create Hermes sync module `intel_sync.py`

**Files:**
- Create: `intel_sync.py`

- [ ] **Step 1: Write Hermes HTML parser**

```python
"""NebulaShare Intelligence Center — Content collectors."""

import os
import re
import hashlib
from datetime import datetime, timezone
from urllib.parse import urljoin

from bs4 import BeautifulSoup
import requests
import feedparser

import intel_db as db

# ── Config ──────────────────────────────────────────────────────────
DAILY_NEWS_DIR = os.path.expanduser("~/.hermes/daily-news")

# Hermes section header -> fixed category mapping
HERMES_CATEGORY_MAP = {
    "ai": "AI",
    "人工智能": "AI",
    "🤖 ai": "AI",
    "🤖 人工智能": "AI",
    "互联网": "互联网",
    "🌐 互联网": "互联网",
    "美股": "金融",
    "📈 美股": "金融",
    "金融": "金融",
    "💰 金融": "金融",
    "创投": "创投",
    "🚀 创投": "创投",
    "工具": "工具",
    "🛠 工具": "工具",
    "阅读": "阅读",
    "📚 阅读": "阅读",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _map_category(section_title: str) -> str:
    lowered = section_title.lower().strip()
    for key, cat in HERMES_CATEGORY_MAP.items():
        if key in lowered:
            return cat
    return "阅读"  # fallback


def _extract_articles_from_html(html: str, source_id: int, broadcast_date: str) -> list[dict]:
    """Parse a Hermes daily-news HTML file and return article dicts."""
    soup = BeautifulSoup(html, "lxml")
    articles = []
    current_category = "阅读"

    for section in soup.find_all("div", class_="section"):
        h2 = section.find("h2")
        if h2:
            current_category = _map_category(h2.get_text(strip=True))

        for article in section.find_all("div", class_="article"):
            # Source site
            source_span = article.find("span", class_="source")
            site = source_span.get_text(strip=True) if source_span else ""

            # Date
            date_span = article.find("span", class_="date")
            art_date = date_span.get_text(strip=True) if date_span else broadcast_date

            # Title + link
            link = article.find("a", class_="title")
            title = link.get_text(strip=True) if link else ""
            url = link.get("href", "") if link else ""

            # Summary
            summary_div = article.find("div", class_="summary")
            summary = summary_div.get_text(strip=True) if summary_div else ""

            # Generate external_id from URL (or title if no URL)
            external_id = hashlib.md5(url.encode() if url else title.encode()).hexdigest()

            articles.append({
                "source_id": source_id,
                "external_id": external_id,
                "title": title,
                "summary": summary,
                "content": "",
                "url": url,
                "author": site,
                "published_at": f"{broadcast_date}T00:00:00+00:00",
                "category": current_category,
            })

    return articles


def sync_hermes() -> dict:
    """Scan Hermes daily-news dir and import new articles."""
    source = db.get_source(1)
    if not source:
        return {"synced": 0, "errors": 0, "message": "Hermes source not found"}

    synced = 0
    errors = 0

    if not os.path.isdir(DAILY_NEWS_DIR):
        return {"synced": 0, "errors": 1, "message": f"Directory not found: {DAILY_NEWS_DIR}"}

    files = sorted(
        [f for f in os.listdir(DAILY_NEWS_DIR)
         if f.startswith("daily-news-") and f.endswith(".html")]
    )

    for fn in files:
        try:
            date_str = fn.replace("daily-news-", "").replace(".html", "")
            path = os.path.join(DAILY_NEWS_DIR, fn)

            with open(path, "r", encoding="utf-8") as f:
                html = f.read()

            articles = _extract_articles_from_html(html, source["id"], date_str)

            for art in articles:
                if not db.article_exists(source["id"], art["external_id"]):
                    db.create_article(**art)
                    synced += 1

        except Exception as e:
            errors += 1
            print(f"[intel_sync] Error parsing {fn}: {e}")

    db.update_source(source["id"], last_fetch_at=_now())
    return {"synced": synced, "errors": errors}
```

- [ ] **Step 2: Add RSS sync to `intel_sync.py`**

Append to `intel_sync.py`:

```python
# ── RSS Collector ───────────────────────────────────────────────────

def sync_rss_source(source_id: int) -> dict:
    """Fetch and import articles from a single RSS source."""
    source = db.get_source(source_id)
    if not source or source["type"] != "rss":
        return {"synced": 0, "errors": 1, "message": "Invalid RSS source"}
    if not source.get("url"):
        return {"synced": 0, "errors": 1, "message": "No URL configured"}

    try:
        feed = feedparser.parse(source["url"])
    except Exception as e:
        db.update_source(source_id, error_count=source.get("error_count", 0) + 1,
                         last_error=str(e), last_fetch_at=_now())
        return {"synced": 0, "errors": 1, "message": str(e)}

    synced = 0
    errors = 0
    config = {}
    if source.get("config"):
        try:
            config = __import__("json").loads(source["config"])
        except Exception:
            pass
    default_category = config.get("category", "阅读")

    for entry in feed.entries:
        try:
            guid = entry.get("id", entry.get("guid", entry.get("link", "")))
            if not guid:
                continue

            if db.article_exists(source_id, guid):
                continue

            title = entry.get("title", "无标题")
            summary = entry.get("summary", entry.get("description", ""))
            url = entry.get("link", "")
            author = entry.get("author", "")

            published = entry.get("published", "")
            if published:
                try:
                    parsed = entry.get("published_parsed")
                    if parsed:
                        dt = datetime(*parsed[:6], tzinfo=timezone.utc)
                        published_at = dt.isoformat()
                    else:
                        published_at = _now()
                except Exception:
                    published_at = _now()
            else:
                published_at = _now()

            db.create_article(
                source_id=source_id,
                external_id=guid,
                title=title,
                summary=summary,
                content="",
                url=url,
                author=author,
                published_at=published_at,
                category=default_category,
            )
            synced += 1

        except Exception as e:
            errors += 1
            print(f"[intel_sync] Error processing RSS entry: {e}")

    # Reset error count on success
    if errors == 0:
        db.update_source(source_id, error_count=0, last_error=None, last_fetch_at=_now())
    else:
        err_count = source.get("error_count", 0) + 1
        db.update_source(source_id, error_count=err_count, last_fetch_at=_now())

    return {"synced": synced, "errors": errors}


def sync_all_rss() -> dict:
    """Sync all active RSS sources."""
    sources = db.list_sources()
    total_synced = 0
    total_errors = 0

    for s in sources:
        if s["type"] == "rss" and s.get("is_active"):
            # Auto-pause if error_count >= 3
            if s.get("error_count", 0) >= 3:
                db.update_source(s["id"], is_active=0)
                continue
            result = sync_rss_source(s["id"])
            total_synced += result["synced"]
            total_errors += result["errors"]

    return {"synced": total_synced, "errors": total_errors}
```

- [ ] **Step 3: Add URL scraper to `intel_sync.py`**

Append to `intel_sync.py`:

```python
# ── URL Scraper (for manual entry) ──────────────────────────────────

def scrape_url(url: str) -> dict:
    """Fetch a URL and extract title, summary, and content."""
    try:
        headers = {"User-Agent": "Mozilla/5.0 (compatible; NebulaBot/1.0)"}
        resp = requests.get(url, headers=headers, timeout=15)
        resp.raise_for_status()
        resp.encoding = resp.apparent_encoding or "utf-8"

        soup = BeautifulSoup(resp.text, "lxml")

        # Title
        title = ""
        title_tag = soup.find("title")
        if title_tag:
            title = title_tag.get_text(strip=True)

        # Meta description
        summary = ""
        meta = soup.find("meta", attrs={"name": "description"})
        if meta:
            summary = meta.get("content", "")
        if not summary:
            meta = soup.find("meta", property="og:description")
            if meta:
                summary = meta.get("content", "")

        # Try to extract main content
        content = ""
        for selector in ["article", "main", "[role='main']", ".content", "#content", ".post"]:
            elem = soup.select_one(selector)
            if elem:
                content = elem.get_text(separator="\n", strip=True)
                break
        if not content:
            # Fallback: body text minus nav/footer
            body = soup.find("body")
            if body:
                for noise in body.find_all(["nav", "footer", "header", "script", "style", "aside"]):
                    noise.decompose()
                content = body.get_text(separator="\n", strip=True)[:5000]

        return {
            "title": title,
            "summary": summary,
            "content": content[:5000],
            "url": url,
            "ok": True,
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}
```

- [ ] **Step 4: Commit sync module**

```bash
git add intel_sync.py
git commit -m "feat(intel): add Hermes parser, RSS collector, and URL scraper"
```

---

### Task 5: Register intel API routes in `app.py`

**Files:**
- Modify: `app.py` (insert before Daily News section at line 1181)

- [ ] **Step 1: Add imports at top of `app.py`**

After existing imports (line 24), add:

```python
import intel_db
import intel_sync
```

- [ ] **Step 2: Add init call after app creation**

Find where `app = Flask(__name__)` is created (around line 160), add after it:

```python
# ── Intelligence Center ──────────────────────────────────────────────
intel_db.init_db()
```

- [ ] **Step 3: Insert intel API routes before Daily News section**

Insert before `# ── Routes: Daily News ──────────────────────────────────────────────` (line 1181):

```python
# ── Routes: Intelligence Center ─────────────────────────────────────

@app.route("/api/intel/articles")
def intel_articles_list():
    """List articles with filtering, search, and pagination."""
    category = request.args.get("category") or None
    tag = request.args.get("tag") or None
    search_q = request.args.get("search") or None
    starred = request.args.get("starred")
    unread = request.args.get("unread")
    archived = request.args.get("archived", "0") == "1"
    source_id = request.args.get("source_id", type=int)
    page = request.args.get("page", 1, type=int)
    per_page = min(request.args.get("per_page", 20, type=int), 100)

    tag_id = None
    if tag:
        # look up tag by name
        with intel_db._conn() as conn:
            row = conn.execute("SELECT id FROM tags WHERE name = ?", (tag,)).fetchone()
            if row:
                tag_id = row[0]

    articles, total = intel_db.list_articles(
        category=category, tag=None, search=search_q,
        starred=(starred == "1") if starred is not None else None,
        unread=(unread == "1") if unread is not None else None,
        archived=archived, source_id=source_id,
        page=page, per_page=per_page
    )

    # If tag filter was requested, filter in Python (SQLite doesn't have
    # a clean way to do this with our schema without a subquery)
    if tag_id:
        with intel_db._conn() as conn:
            article_ids = {r[0] for r in conn.execute(
                "SELECT article_id FROM article_tags WHERE tag_id = ?", (tag_id,)
            ).fetchall()}
        articles = [a for a in articles if a["id"] in article_ids]
        total = len(articles)

    return jsonify({"articles": articles, "total": total, "page": page, "per_page": per_page})


@app.route("/api/intel/articles", methods=["POST"])
def intel_article_create():
    """Create a new article (manual entry)."""
    data = request.get_json() or {}
    title = data.get("title", "").strip()
    if not title:
        return jsonify({"error": "title is required"}), 400

    art = intel_db.create_article(
        source_id=data.get("source_id", 2),  # default to manual
        title=title,
        summary=data.get("summary", ""),
        content=data.get("content", ""),
        url=data.get("url", ""),
        author=data.get("author", ""),
        published_at=data.get("published_at"),
        category=data.get("category", "阅读"),
    )

    # Set tags if provided
    tag_ids = data.get("tags", [])
    if tag_ids:
        intel_db.set_article_tags(art["id"], tag_ids)
        art = intel_db.get_article(art["id"])

    return jsonify(art)


@app.route("/api/intel/articles/<int:article_id>")
def intel_article_get(article_id):
    art = intel_db.get_article(article_id)
    if not art:
        return jsonify({"error": "not found"}), 404
    return jsonify(art)


@app.route("/api/intel/articles/<int:article_id>", methods=["PUT"])
def intel_article_update(article_id):
    data = request.get_json() or {}
    fields = {k: v for k, v in data.items()
              if k in {"title", "summary", "content", "url", "author",
                       "category", "is_read", "is_starred", "is_archived"}}
    art = intel_db.update_article(article_id, **fields)
    if not art:
        return jsonify({"error": "not found"}), 404

    if "tags" in data:
        intel_db.set_article_tags(article_id, data["tags"])
        art = intel_db.get_article(article_id)

    return jsonify(art)


@app.route("/api/intel/articles/<int:article_id>", methods=["DELETE"])
def intel_article_delete(article_id):
    ok = intel_db.delete_article(article_id)
    if not ok:
        return jsonify({"error": "not found"}), 404
    return jsonify({"ok": True})


@app.route("/api/intel/sources")
def intel_sources_list():
    return jsonify({"sources": intel_db.list_sources()})


@app.route("/api/intel/sources", methods=["POST"])
def intel_source_create():
    data = request.get_json() or {}
    name = data.get("name", "").strip()
    type_ = data.get("type", "rss")
    url = data.get("url", "").strip()
    if not name or type_ not in {"hermes", "rss", "manual"}:
        return jsonify({"error": "name and valid type required"}), 400
    if type_ == "rss" and not url:
        return jsonify({"error": "url required for rss sources"}), 400

    s = intel_db.create_source(name=name, type_=type_, url=url,
                               config=data.get("config", {}))
    return jsonify(s)


@app.route("/api/intel/sources/<int:source_id>", methods=["PUT"])
def intel_source_update(source_id):
    data = request.get_json() or {}
    allowed = {"name", "url", "config", "is_active", "category"}
    fields = {k: v for k, v in data.items() if k in allowed}
    s = intel_db.update_source(source_id, **fields)
    if not s:
        return jsonify({"error": "not found"}), 404
    return jsonify(s)


@app.route("/api/intel/sources/<int:source_id>", methods=["DELETE"])
def intel_source_delete(source_id):
    ok = intel_db.delete_source(source_id)
    if not ok:
        return jsonify({"error": "not found"}), 404
    return jsonify({"ok": True})


@app.route("/api/intel/sync", methods=["POST"])
def intel_sync_trigger():
    data = request.get_json() or {}
    source = data.get("source", "all")
    results = {"hermes": {}, "rss": {}}

    if source in ("all", "hermes"):
        results["hermes"] = intel_sync.sync_hermes()

    if source in ("all", "rss"):
        results["rss"] = intel_sync.sync_all_rss()

    return jsonify({"ok": True, "results": results})


@app.route("/api/intel/tags")
def intel_tags_list():
    return jsonify({"tags": intel_db.list_tags()})


@app.route("/api/intel/tags", methods=["POST"])
def intel_tag_create():
    data = request.get_json() or {}
    name = data.get("name", "").strip()
    if not name:
        return jsonify({"error": "name is required"}), 400
    t = intel_db.create_tag(name, data.get("color", "#3b82f6"))
    return jsonify(t)


@app.route("/api/intel/tags/<int:tag_id>", methods=["DELETE"])
def intel_tag_delete(tag_id):
    ok = intel_db.delete_tag(tag_id)
    if not ok:
        return jsonify({"error": "not found"}), 404
    return jsonify({"ok": True})


@app.route("/api/intel/stats")
def intel_stats():
    return jsonify(intel_db.get_stats())


@app.route("/api/intel/scrape", methods=["POST"])
def intel_scrape_url():
    """Scrape a URL for title/summary/content."""
    data = request.get_json() or {}
    url = data.get("url", "").strip()
    if not url:
        return jsonify({"error": "url is required"}), 400
    result = intel_sync.scrape_url(url)
    return jsonify(result)
```

- [ ] **Step 4: Test the API manually**

```bash
curl -s "http://localhost:8080/api/intel/stats" | python -m json.tool
```

Expected: `{"total_articles": 0, ...}` (database is empty before sync)

- [ ] **Step 5: Trigger Hermes sync and verify**

```bash
curl -s -X POST "http://localhost:8080/api/intel/sync" -H "Content-Type: application/json" -d '{"source":"hermes"}' | python -m json.tool
```

Expected: `{"ok": true, "results": {"hermes": {"synced": N, "errors": 0}}}` where N > 0 (if Hermes files exist)

- [ ] **Step 6: Verify articles are queryable**

```bash
curl -s "http://localhost:8080/api/intel/articles" | python -m json.tool | head -30
```

Expected: `{"articles": [...], "total": N}` with real article data.

- [ ] **Step 7: Commit**

```bash
git add app.py
git commit -m "feat(intel): register all intelligence center API routes in app.py"
```

---

### Task 6: Update Dashboard to use new API

**Files:**
- Modify: `app/page.tsx`

- [ ] **Step 1: Update the intelligence card data fetch**

In `app/page.tsx`, find the Dashboard intelligence card section (around line 331). Replace the `fetch("/api/daily-news")` block:

Replace:
```typescript
      fetch("/api/daily-news")
        .then((r) => (r.ok ? r.json() : null))
        .then((d) => {
          if (!mounted || !d?.items?.length) return
          setNews(d.items[0])
        }),
```

With:
```typescript
      fetch("/api/intel/articles?unread=1&per_page=1")
        .then((r) => (r.ok ? r.json() : null))
        .then((d) => {
          if (!mounted || !d?.articles?.length) return
          const a = d.articles[0]
          setNews({
            title: a.title,
            date: a.published_at?.split("T")[0] || "",
            category: a.category,
          })
        }),
```

- [ ] **Step 2: Commit**

```bash
git add nebula-share-frontend/app/page.tsx
git commit -m "feat(dashboard): update intel card to use new /api/intel/articles"
```

---

### Task 7: Build frontend base components (Phase 1)

**Files:**
- Create: `components/intel/article-list.tsx`
- Create: `components/intel/article-list-item.tsx`
- Create: `components/intel/article-reader.tsx`
- Create: `components/intel/search-bar.tsx`

- [ ] **Step 1: Create `components/intel/article-list-item.tsx`**

```tsx
"use client"

import { Star, Circle } from "lucide-react"
import { cn } from "@/lib/utils"

export interface Article {
  id: number
  title: string
  summary: string
  url: string
  author: string
  published_at: string
  category: string
  is_read: boolean
  is_starred: boolean
  source_name: string
  tags: { id: number; name: string; color: string }[]
}

interface ArticleListItemProps {
  article: Article
  selected: boolean
  onClick: () => void
  onToggleStar: () => void
}

const CATEGORY_COLORS: Record<string, string> = {
  AI: "bg-chart-1",
  互联网: "bg-chart-2",
  金融: "bg-chart-3",
  创投: "bg-chart-5",
  工具: "bg-chart-4",
  阅读: "bg-muted-foreground",
}

export function ArticleListItem({ article, selected, onClick, onToggleStar }: ArticleListItemProps) {
  const dateStr = article.published_at
    ? new Date(article.published_at).toLocaleDateString("zh-CN", { month: "short", day: "numeric" })
    : ""

  return (
    <button
      onClick={onClick}
      className={cn(
        "relative w-full px-4 py-3 text-left transition-colors group rounded-xl",
        selected ? "bg-secondary/80" : "hover:bg-secondary/40",
        !article.is_read && "font-medium"
      )}
    >
      {/* Unread indicator */}
      {!article.is_read && (
        <span className="absolute left-1 top-4 w-1 h-1 rounded-full bg-chart-1" />
      )}

      <div className="flex items-start justify-between gap-3">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1.5">
            <span className={cn("w-1.5 h-1.5 rounded-full", CATEGORY_COLORS[article.category] || "bg-muted-foreground")} />
            <span className="text-[11px] text-muted-foreground">{article.source_name}</span>
            <span className="text-[11px] text-muted-foreground/60">·</span>
            <span className="text-[11px] text-muted-foreground/60">{article.category}</span>
            {article.tags.map((t) => (
              <span
                key={t.id}
                className="text-[10px] px-1.5 py-0.5 rounded-full bg-secondary/80 text-muted-foreground"
              >
                {t.name}
              </span>
            ))}
          </div>
          <h3 className={cn("text-sm mb-1 line-clamp-1", !article.is_read && "text-foreground")}>
            {article.title}
          </h3>
          <p className="text-xs text-muted-foreground line-clamp-2 leading-relaxed">
            {article.summary || "暂无摘要"}
          </p>
        </div>
        <div className="flex flex-col items-end gap-1.5 shrink-0">
          <span className="text-[11px] text-muted-foreground/50 font-mono">{dateStr}</span>
          <button
            onClick={(e) => { e.stopPropagation(); onToggleStar() }}
            className={cn(
              "opacity-0 group-hover:opacity-100 transition-opacity",
              article.is_starred && "opacity-100"
            )}
          >
            <Star
              className={cn("w-3.5 h-3.5", article.is_starred ? "fill-chart-1 text-chart-1" : "text-muted-foreground/40")}
              strokeWidth={1.5}
            />
          </button>
        </div>
      </div>
    </button>
  )
}
```

- [ ] **Step 2: Create `components/intel/article-list.tsx`**

```tsx
"use client"

import { useEffect, useState } from "react"
import { ArticleListItem, Article } from "./article-list-item"

interface ArticleListProps {
  articles: Article[]
  selectedId: number | null
  onSelect: (article: Article) => void
  onToggleStar: (id: number) => void
}

export function ArticleList({ articles, selectedId, onSelect, onToggleStar }: ArticleListProps) {
  if (articles.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-12 text-muted-foreground/50">
        <p className="text-sm">暂无文章</p>
      </div>
    )
  }

  return (
    <div className="space-y-0.5">
      {articles.map((article) => (
        <ArticleListItem
          key={article.id}
          article={article}
          selected={selectedId === article.id}
          onClick={() => onSelect(article)}
          onToggleStar={() => onToggleStar(article.id)}
        />
      ))}
    </div>
  )
}
```

- [ ] **Step 3: Create `components/intel/article-reader.tsx`**

```tsx
"use client"

import { useState } from "react"
import { X, Star, CheckCircle, Archive, ExternalLink, Tag } from "lucide-react"
import { cn } from "@/lib/utils"
import type { Article } from "./article-list-item"

interface ArticleReaderProps {
  article: Article | null
  onClose: () => void
  onUpdate: (id: number, fields: Partial<Article>) => void
}

const CATEGORY_COLORS: Record<string, string> = {
  AI: "bg-chart-1",
  互联网: "bg-chart-2",
  金融: "bg-chart-3",
  创投: "bg-chart-5",
  工具: "bg-chart-4",
  阅读: "bg-muted-foreground",
}

export function ArticleReader({ article, onClose, onUpdate }: ArticleReaderProps) {
  const [isClosing, setIsClosing] = useState(false)

  if (!article) return null

  const handleClose = () => {
    setIsClosing(true)
    setTimeout(onClose, 200)
  }

  const dateStr = article.published_at
    ? new Date(article.published_at).toLocaleString("zh-CN", {
        month: "short", day: "numeric", hour: "2-digit", minute: "2-digit"
      })
    : ""

  return (
    <div
      className={cn(
        "fixed inset-y-0 right-0 w-full sm:w-[480px] bg-card border-l border-border/40 shadow-xl z-50 flex flex-col",
        "transform transition-transform duration-200",
        isClosing ? "translate-x-full" : "translate-x-0"
      )}
    >
      {/* Header */}
      <div className="flex items-center justify-between px-5 py-4 border-b border-border/40 shrink-0">
        <div className="flex items-center gap-2 overflow-hidden">
          <span className={cn("w-2 h-2 rounded-full shrink-0", CATEGORY_COLORS[article.category] || "bg-muted-foreground")} />
          <span className="text-xs text-muted-foreground truncate">{article.source_name}</span>
          <span className="text-xs text-muted-foreground/40">·</span>
          <span className="text-xs text-muted-foreground/40">{article.category}</span>
        </div>
        <button onClick={handleClose} className="p-1.5 hover:bg-secondary rounded-lg transition-colors">
          <X className="w-4 h-4" strokeWidth={1.5} />
        </button>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-auto px-5 py-5">
        <h1 className="text-lg font-semibold leading-snug mb-3">{article.title}</h1>

        <div className="flex items-center gap-3 text-xs text-muted-foreground mb-5">
          {article.author && <span>{article.author}</span>}
          <span>{dateStr}</span>
        </div>

        {article.tags.length > 0 && (
          <div className="flex flex-wrap gap-1.5 mb-5">
            {article.tags.map((t) => (
              <span key={t.id} className="text-[11px] px-2 py-0.5 rounded-full bg-secondary/80 text-muted-foreground">
                {t.name}
              </span>
            ))}
          </div>
        )}

        {article.summary && (
          <div className="text-sm text-muted-foreground leading-relaxed mb-5 p-4 bg-secondary/40 rounded-xl">
            {article.summary}
          </div>
        )}

        {article.content ? (
          <div className="prose prose-sm dark:prose-invert max-w-none"
            dangerouslySetInnerHTML={{ __html: article.content }}
          />
        ) : (
          <p className="text-sm text-muted-foreground/60">暂无全文内容</p>
        )}
      </div>

      {/* Action bar */}
      <div className="px-5 py-3 border-t border-border/40 shrink-0 flex items-center gap-1">
        <button
          onClick={() => onUpdate(article.id, { is_read: !article.is_read })}
          className={cn(
            "flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-colors",
            article.is_read
              ? "bg-secondary/60 text-muted-foreground"
              : "bg-primary/10 text-primary hover:bg-primary/15"
          )}
        >
          <CheckCircle className="w-3.5 h-3.5" strokeWidth={1.5} />
          {article.is_read ? "已读" : "标记已读"}
        </button>

        <button
          onClick={() => onUpdate(article.id, { is_starred: !article.is_starred })}
          className={cn(
            "flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-colors",
            article.is_starred
              ? "bg-chart-1/10 text-chart-1"
              : "bg-secondary/60 text-muted-foreground hover:bg-secondary"
          )}
        >
          <Star className={cn("w-3.5 h-3.5", article.is_starred && "fill-current")} strokeWidth={1.5} />
          {article.is_starred ? "已收藏" : "收藏"}
        </button>

        <button
          onClick={() => onUpdate(article.id, { is_archived: !article.is_archived })}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium bg-secondary/60 text-muted-foreground hover:bg-secondary transition-colors"
        >
          <Archive className="w-3.5 h-3.5" strokeWidth={1.5} />
          {article.is_archived ? "已归档" : "归档"}
        </button>

        {article.url && (
          <a
            href={article.url}
            target="_blank"
            rel="noopener noreferrer"
            className="ml-auto flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium bg-secondary/60 text-muted-foreground hover:bg-secondary transition-colors"
          >
            <ExternalLink className="w-3.5 h-3.5" strokeWidth={1.5} />
            原文
          </a>
        )}
      </div>
    </div>
  )
}
```

- [ ] **Step 4: Create `components/intel/search-bar.tsx`**

```tsx
"use client"

import { useState } from "react"
import { Search, X, Star, CheckCircle } from "lucide-react"
import { cn } from "@/lib/utils"

const CATEGORIES = ["AI", "互联网", "金融", "创投", "工具", "阅读"]

interface SearchBarProps {
  search: string
  onSearchChange: (v: string) => void
  category: string | null
  onCategoryChange: (v: string | null) => void
  starredOnly: boolean
  onStarredChange: (v: boolean) => void
  unreadOnly: boolean
  onUnreadChange: (v: boolean) => void
}

export function SearchBar({
  search, onSearchChange,
  category, onCategoryChange,
  starredOnly, onStarredChange,
  unreadOnly, onUnreadChange,
}: SearchBarProps) {
  return (
    <div className="space-y-3">
      <div className="relative">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground/50" strokeWidth={1.5} />
        <input
          type="text"
          placeholder="搜索标题、摘要、内容..."
          value={search}
          onChange={(e) => onSearchChange(e.target.value)}
          className="w-full pl-10 pr-10 py-2 rounded-xl bg-card border border-border/40 text-sm placeholder:text-muted-foreground/40 focus:outline-none focus:ring-1 focus:ring-primary/30"
        />
        {search && (
          <button
            onClick={() => onSearchChange("")}
            className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground/50 hover:text-muted-foreground"
          >
            <X className="w-3.5 h-3.5" strokeWidth={1.5} />
          </button>
        )}
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <button
          onClick={() => onCategoryChange(null)}
          className={cn(
            "px-2.5 py-1 rounded-lg text-xs font-medium transition-colors",
            !category ? "bg-primary/10 text-primary" : "bg-secondary/60 text-muted-foreground hover:bg-secondary"
          )}
        >
          全部
        </button>
        {CATEGORIES.map((cat) => (
          <button
            key={cat}
            onClick={() => onCategoryChange(category === cat ? null : cat)}
            className={cn(
              "px-2.5 py-1 rounded-lg text-xs font-medium transition-colors",
              category === cat ? "bg-primary/10 text-primary" : "bg-secondary/60 text-muted-foreground hover:bg-secondary"
            )}
          >
            {cat}
          </button>
        ))}

        <div className="ml-auto flex items-center gap-2">
          <button
            onClick={() => onStarredChange(!starredOnly)}
            className={cn(
              "flex items-center gap-1 px-2.5 py-1 rounded-lg text-xs font-medium transition-colors",
              starredOnly ? "bg-chart-1/10 text-chart-1" : "bg-secondary/60 text-muted-foreground hover:bg-secondary"
            )}
          >
            <Star className={cn("w-3 h-3", starredOnly && "fill-current")} strokeWidth={1.5} />
            收藏
          </button>
          <button
            onClick={() => onUnreadChange(!unreadOnly)}
            className={cn(
              "flex items-center gap-1 px-2.5 py-1 rounded-lg text-xs font-medium transition-colors",
              unreadOnly ? "bg-primary/10 text-primary" : "bg-secondary/60 text-muted-foreground hover:bg-secondary"
            )}
          >
            <CheckCircle className="w-3 h-3" strokeWidth={1.5} />
            未读
          </button>
        </div>
      </div>
    </div>
  )
}
```

- [ ] **Step 5: Commit frontend components**

```bash
git add nebula-share-frontend/components/intel/
git commit -m "feat(intel): add article list, reader, and search bar components"
```

---

### Task 8: Rewrite `/intel` page

**Files:**
- Modify: `app/intel/page.tsx`
- Delete: `components/intelligence-center.tsx` (optional: keep for reference then delete)

- [ ] **Step 1: Rewrite `app/intel/page.tsx`**

```tsx
"use client"

import { useState, useEffect, useCallback } from "react"
import { SearchBar } from "@/components/intel/search-bar"
import { ArticleList } from "@/components/intel/article-list"
import { ArticleReader } from "@/components/intel/article-reader"
import { SyncButton } from "@/components/intel/sync-button"
import type { Article } from "@/components/intel/article-list-item"

export default function IntelPage() {
  const [articles, setArticles] = useState<Article[]>([])
  const [total, setTotal] = useState(0)
  const [selectedArticle, setSelectedArticle] = useState<Article | null>(null)
  const [loading, setLoading] = useState(true)

  // Filters
  const [search, setSearch] = useState("")
  const [category, setCategory] = useState<string | null>(null)
  const [starredOnly, setStarredOnly] = useState(false)
  const [unreadOnly, setUnreadOnly] = useState(false)

  const fetchArticles = useCallback(async () => {
    setLoading(true)
    const params = new URLSearchParams()
    if (search) params.set("search", search)
    if (category) params.set("category", category)
    if (starredOnly) params.set("starred", "1")
    if (unreadOnly) params.set("unread", "1")
    params.set("per_page", "50")

    try {
      const res = await fetch(`/api/intel/articles?${params}`)
      const data = await res.json()
      setArticles(data.articles || [])
      setTotal(data.total || 0)
    } catch (e) {
      console.error("Failed to fetch articles:", e)
    } finally {
      setLoading(false)
    }
  }, [search, category, starredOnly, unreadOnly])

  useEffect(() => {
    fetchArticles()
  }, [fetchArticles])

  const handleSelect = useCallback((article: Article) => {
    setSelectedArticle(article)
    // Auto-mark as read when opening
    if (!article.is_read) {
      handleUpdate(article.id, { is_read: true })
    }
  }, [])

  const handleUpdate = useCallback(async (id: number, fields: Partial<Article>) => {
    try {
      const res = await fetch(`/api/intel/articles/${id}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(fields),
      })
      if (!res.ok) return
      const updated = await res.json()

      setArticles((prev) => prev.map((a) => (a.id === id ? { ...a, ...updated } : a)))
      if (selectedArticle?.id === id) {
        setSelectedArticle({ ...selectedArticle, ...updated })
      }
    } catch (e) {
      console.error("Failed to update article:", e)
    }
  }, [selectedArticle])

  const handleToggleStar = useCallback(async (id: number) => {
    const article = articles.find((a) => a.id === id)
    if (!article) return
    handleUpdate(id, { is_starred: !article.is_starred })
  }, [articles, handleUpdate])

  const handleSync = useCallback(async () => {
    await fetch("/api/intel/sync", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ source: "all" }),
    })
    fetchArticles()
  }, [fetchArticles])

  return (
    <div className="p-6 sm:p-8 max-w-6xl mx-auto h-full flex flex-col">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">情报站</h1>
          <p className="text-sm text-muted-foreground mt-1">
            {total} 篇文章 · 聚合 Hermes 播报、RSS 订阅与手动录入
          </p>
        </div>
        <SyncButton onSync={handleSync} />
      </div>

      <div className="bg-card rounded-2xl p-5 sm:p-6 shadow-[var(--shadow-card)] border border-border/40 flex-1 flex flex-col min-h-0">
        <div className="mb-4 shrink-0">
          <SearchBar
            search={search}
            onSearchChange={setSearch}
            category={category}
            onCategoryChange={setCategory}
            starredOnly={starredOnly}
            onStarredChange={setStarredOnly}
            unreadOnly={unreadOnly}
            onUnreadChange={setUnreadOnly}
          />
        </div>

        <div className="flex-1 overflow-auto min-h-0">
          {loading ? (
            <div className="flex items-center justify-center py-12">
              <div className="w-6 h-6 border-2 border-primary/30 border-t-primary rounded-full animate-spin" />
            </div>
          ) : (
            <ArticleList
              articles={articles}
              selectedId={selectedArticle?.id || null}
              onSelect={handleSelect}
              onToggleStar={handleToggleStar}
            />
          )}
        </div>
      </div>

      {selectedArticle && (
        <ArticleReader
          article={selectedArticle}
          onClose={() => setSelectedArticle(null)}
          onUpdate={handleUpdate}
        />
      )}
    </div>
  )
}
```

- [ ] **Step 2: Create `components/intel/sync-button.tsx`**

```tsx
"use client"

import { useState } from "react"
import { RefreshCw } from "lucide-react"
import { cn } from "@/lib/utils"

interface SyncButtonProps {
  onSync: () => Promise<void>
}

export function SyncButton({ onSync }: SyncButtonProps) {
  const [syncing, setSyncing] = useState(false)

  const handleClick = async () => {
    if (syncing) return
    setSyncing(true)
    try {
      await onSync()
    } finally {
      setSyncing(false)
    }
  }

  return (
    <button
      onClick={handleClick}
      disabled={syncing}
      className={cn(
        "flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-medium transition-all",
        "bg-primary/10 text-primary hover:bg-primary/15",
        syncing && "opacity-60 cursor-wait"
      )}
    >
      <RefreshCw className={cn("w-4 h-4", syncing && "animate-spin")} strokeWidth={1.5} />
      {syncing ? "同步中..." : "同步"}
    </button>
  )
}
```

- [ ] **Step 3: Delete old mock component**

```bash
rm nebula-share-frontend/components/intelligence-center.tsx
git add nebula-share-frontend/app/intel/page.tsx nebula-share-frontend/components/intel/sync-button.tsx
git rm nebula-share-frontend/components/intelligence-center.tsx || true
git commit -m "feat(intel): rewrite /intel page with real data from API"
```

---

### Task 9: Add tag selector component

**Files:**
- Create: `components/intel/tag-selector.tsx`

- [ ] **Step 1: Write tag selector**

```tsx
"use client"

import { useState, useEffect } from "react"
import { X, Plus, Check } from "lucide-react"
import { cn } from "@/lib/utils"

interface Tag {
  id: number
  name: string
  color: string
}

interface TagSelectorProps {
  articleId: number
  selectedTags: Tag[]
  onChange: (tags: Tag[]) => void
}

export function TagSelector({ articleId, selectedTags, onChange }: TagSelectorProps) {
  const [allTags, setAllTags] = useState<Tag[]>([])
  const [newTagName, setNewTagName] = useState("")
  const [showInput, setShowInput] = useState(false)

  useEffect(() => {
    fetch("/api/intel/tags")
      .then((r) => r.json())
      .then((d) => setAllTags(d.tags || []))
  }, [])

  const toggleTag = async (tagId: number) => {
    const has = selectedTags.some((t) => t.id === tagId)
    const method = has ? "DELETE" : "POST"
    // We use PUT on article to update tags
    const currentIds = selectedTags.map((t) => t.id)
    const newIds = has ? currentIds.filter((id) => id !== tagId) : [...currentIds, tagId]

    try {
      const res = await fetch(`/api/intel/articles/${articleId}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ tags: newIds }),
      })
      if (!res.ok) return
      const updated = await res.json()
      onChange(updated.tags || [])
    } catch (e) {
      console.error(e)
    }
  }

  const createTag = async () => {
    if (!newTagName.trim()) return
    try {
      const res = await fetch("/api/intel/tags", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: newTagName.trim() }),
      })
      if (!res.ok) return
      const tag = await res.json()
      setAllTags((prev) => [...prev, tag])
      await toggleTag(tag.id)
      setNewTagName("")
      setShowInput(false)
    } catch (e) {
      console.error(e)
    }
  }

  return (
    <div className="p-4 space-y-3">
      <p className="text-sm font-medium">标签</p>
      <div className="flex flex-wrap gap-1.5">
        {allTags.map((tag) => {
          const active = selectedTags.some((t) => t.id === tag.id)
          return (
            <button
              key={tag.id}
              onClick={() => toggleTag(tag.id)}
              className={cn(
                "flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-medium transition-colors",
                active
                  ? "text-white"
                  : "bg-secondary/60 text-muted-foreground hover:bg-secondary"
              )}
              style={active ? { backgroundColor: tag.color } : undefined}
            >
              {active && <Check className="w-3 h-3" strokeWidth={2} />}
              {tag.name}
            </button>
          )
        })}
      </div>

      {showInput ? (
        <div className="flex items-center gap-2">
          <input
            type="text"
            placeholder="新标签名称"
            value={newTagName}
            onChange={(e) => setNewTagName(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && createTag()}
            className="flex-1 px-3 py-1.5 rounded-lg bg-secondary/60 text-sm border border-border/40 focus:outline-none focus:ring-1 focus:ring-primary/30"
            autoFocus
          />
          <button onClick={createTag} className="px-3 py-1.5 rounded-lg bg-primary/10 text-primary text-xs font-medium hover:bg-primary/15">添加</button>
          <button onClick={() => setShowInput(false)} className="p-1.5 hover:bg-secondary rounded-lg">
            <X className="w-3.5 h-3.5" strokeWidth={1.5} />
          </button>
        </div>
      ) : (
        <button
          onClick={() => setShowInput(true)}
          className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground transition-colors"
        >
          <Plus className="w-3 h-3" strokeWidth={1.5} />
          新建标签
        </button>
      )}
    </div>
  )
}
```

- [ ] **Step 2: Commit**

```bash
git add nebula-share-frontend/components/intel/tag-selector.tsx
git commit -m "feat(intel): add tag selector component"
```

---

### Task 10: Add manual article entry form

**Files:**
- Create: `components/intel/article-form.tsx`

- [ ] **Step 1: Write article form**

```tsx
"use client"

import { useState } from "react"
import { X, Link2, FileText } from "lucide-react"
import { cn } from "@/lib/utils"

const CATEGORIES = ["AI", "互联网", "金融", "创投", "工具", "阅读"]

interface ArticleFormProps {
  onClose: () => void
  onCreated: () => void
}

export function ArticleForm({ onClose, onCreated }: ArticleFormProps) {
  const [mode, setMode] = useState<"url" | "manual">("url")
  const [url, setUrl] = useState("")
  const [scraping, setScraping] = useState(false)

  const [title, setTitle] = useState("")
  const [summary, setSummary] = useState("")
  const [content, setContent] = useState("")
  const [category, setCategory] = useState("阅读")
  const [submitting, setSubmitting] = useState(false)

  const handleScrape = async () => {
    if (!url.trim()) return
    setScraping(true)
    try {
      const res = await fetch("/api/intel/scrape", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url: url.trim() }),
      })
      const data = await res.json()
      if (data.ok) {
        setTitle(data.title || "")
        setSummary(data.summary || "")
        setContent(data.content || "")
      }
    } catch (e) {
      console.error(e)
    } finally {
      setScraping(false)
    }
  }

  const handleSubmit = async () => {
    if (!title.trim()) return
    setSubmitting(true)
    try {
      const res = await fetch("/api/intel/articles", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          title: title.trim(),
          summary: summary.trim(),
          content: content.trim(),
          url: url.trim(),
          category,
          source_id: 2, // manual
        }),
      })
      if (res.ok) {
        onCreated()
        onClose()
      }
    } catch (e) {
      console.error(e)
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="fixed inset-0 bg-black/40 backdrop-blur-sm z-50 flex items-center justify-center p-4">
      <div className="bg-card rounded-2xl border border-border/40 shadow-xl w-full max-w-lg max-h-[80vh] flex flex-col">
        <div className="flex items-center justify-between px-5 py-4 border-b border-border/40">
          <h2 className="text-base font-semibold">新建文章</h2>
          <button onClick={onClose} className="p-1.5 hover:bg-secondary rounded-lg">
            <X className="w-4 h-4" strokeWidth={1.5} />
          </button>
        </div>

        <div className="flex-1 overflow-auto px-5 py-4 space-y-4">
          <div className="flex rounded-lg bg-secondary/40 p-0.5">
            <button
              onClick={() => setMode("url")}
              className={cn(
                "flex-1 flex items-center justify-center gap-1.5 py-1.5 rounded-md text-xs font-medium transition-colors",
                mode === "url" ? "bg-card text-foreground shadow-sm" : "text-muted-foreground"
              )}
            >
              <Link2 className="w-3.5 h-3.5" strokeWidth={1.5} />
              粘贴链接
            </button>
            <button
              onClick={() => setMode("manual")}
              className={cn(
                "flex-1 flex items-center justify-center gap-1.5 py-1.5 rounded-md text-xs font-medium transition-colors",
                mode === "manual" ? "bg-card text-foreground shadow-sm" : "text-muted-foreground"
              )}
            >
              <FileText className="w-3.5 h-3.5" strokeWidth={1.5} />
              手动撰写
            </button>
          </div>

          {mode === "url" && (
            <div className="flex gap-2">
              <input
                type="url"
                placeholder="https://..."
                value={url}
                onChange={(e) => setUrl(e.target.value)}
                className="flex-1 px-3 py-2 rounded-lg bg-secondary/40 text-sm border border-border/40 focus:outline-none focus:ring-1 focus:ring-primary/30"
              />
              <button
                onClick={handleScrape}
                disabled={scraping || !url.trim()}
                className="px-4 py-2 rounded-lg bg-primary/10 text-primary text-sm font-medium hover:bg-primary/15 disabled:opacity-50"
              >
                {scraping ? "抓取中..." : "抓取"}
              </button>
            </div>
          )}

          <div className="space-y-3">
            <div>
              <label className="text-xs text-muted-foreground mb-1 block">标题</label>
              <input
                type="text"
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                className="w-full px-3 py-2 rounded-lg bg-secondary/40 text-sm border border-border/40 focus:outline-none focus:ring-1 focus:ring-primary/30"
                placeholder="文章标题"
              />
            </div>

            <div>
              <label className="text-xs text-muted-foreground mb-1 block">分类</label>
              <div className="flex flex-wrap gap-1.5">
                {CATEGORIES.map((cat) => (
                  <button
                    key={cat}
                    onClick={() => setCategory(cat)}
                    className={cn(
                      "px-3 py-1 rounded-lg text-xs font-medium transition-colors",
                      category === cat ? "bg-primary/10 text-primary" : "bg-secondary/40 text-muted-foreground hover:bg-secondary"
                    )}
                  >
                    {cat}
                  </button>
                ))}
              </div>
            </div>

            <div>
              <label className="text-xs text-muted-foreground mb-1 block">摘要</label>
              <textarea
                value={summary}
                onChange={(e) => setSummary(e.target.value)}
                rows={3}
                className="w-full px-3 py-2 rounded-lg bg-secondary/40 text-sm border border-border/40 focus:outline-none focus:ring-1 focus:ring-primary/30 resize-none"
                placeholder="文章摘要..."
              />
            </div>

            <div>
              <label className="text-xs text-muted-foreground mb-1 block">内容</label>
              <textarea
                value={content}
                onChange={(e) => setContent(e.target.value)}
                rows={6}
                className="w-full px-3 py-2 rounded-lg bg-secondary/40 text-sm border border-border/40 focus:outline-none focus:ring-1 focus:ring-primary/30 resize-none"
                placeholder="正文内容（支持 Markdown）..."
              />
            </div>
          </div>
        </div>

        <div className="px-5 py-4 border-t border-border/40 flex justify-end gap-2">
          <button onClick={onClose} className="px-4 py-2 rounded-lg text-sm text-muted-foreground hover:bg-secondary transition-colors">取消</button>
          <button
            onClick={handleSubmit}
            disabled={submitting || !title.trim()}
            className="px-4 py-2 rounded-lg bg-primary text-primary-foreground text-sm font-medium hover:bg-primary/90 disabled:opacity-50"
          >
            {submitting ? "保存中..." : "保存"}
          </button>
        </div>
      </div>
    </div>
  )
}
```

- [ ] **Step 2: Commit**

```bash
git add nebula-share-frontend/components/intel/article-form.tsx
git commit -m "feat(intel): add manual article entry form with URL scrape"
```

---

### Task 11: Wire up tag selector and article form in the intel page

**Files:**
- Modify: `app/intel/page.tsx`

- [ ] **Step 1: Add article form button and tag selector integration**

In `app/intel/page.tsx`, add imports:

```tsx
import { ArticleForm } from "@/components/intel/article-form"
import { TagSelector } from "@/components/intel/tag-selector"
import { Plus, Tag } from "lucide-react"
```

Add state:
```tsx
const [showForm, setShowForm] = useState(false)
const [showTagSelector, setShowTagSelector] = useState(false)
```

Replace the header section:

```tsx
<div className="flex items-center justify-between mb-6">
  <div>
    <h1 className="text-2xl font-bold tracking-tight">情报站</h1>
    <p className="text-sm text-muted-foreground mt-1">
      {total} 篇文章 · 聚合 Hermes 播报、RSS 订阅与手动录入
    </p>
  </div>
  <div className="flex items-center gap-2">
    <button
      onClick={() => setShowForm(true)}
      className="flex items-center gap-1.5 px-4 py-2 rounded-xl text-sm font-medium bg-chart-4/10 text-chart-4 hover:bg-chart-4/15 transition-colors"
    >
      <Plus className="w-4 h-4" strokeWidth={1.5} />
      新建
    </button>
    <SyncButton onSync={handleSync} />
  </div>
</div>
```

Add the form modal:
```tsx
{showForm && <ArticleForm onClose={() => setShowForm(false)} onCreated={fetchArticles} />}
```

- [ ] **Step 2: Commit**

```bash
git add nebula-share-frontend/app/intel/page.tsx
git commit -m "feat(intel): wire up article form and tag selector into main page"
```

---

## Phase 3: RSS Sources + Source Management (P1)

### Task 12: Build source management page

**Files:**
- Create: `app/intel/sources/page.tsx`
- Create: `components/intel/source-form.tsx`
- Create: `components/intel/source-manager.tsx`

- [ ] **Step 1: Create `components/intel/source-manager.tsx`**

```tsx
"use client"

import { useState, useEffect } from "react"
import { RefreshCw, Trash2, Pause, Play, AlertCircle, CheckCircle2 } from "lucide-react"
import { cn } from "@/lib/utils"

interface Source {
  id: number
  name: string
  type: string
  url: string
  is_active: boolean
  article_count: number
  last_fetch_at: string | null
  last_error: string | null
  error_count: number
}

interface SourceManagerProps {
  onEdit: (source: Source) => void
}

export function SourceManager({ onEdit }: SourceManagerProps) {
  const [sources, setSources] = useState<Source[]>([])
  const [loading, setLoading] = useState(true)

  const fetchSources = async () => {
    setLoading(true)
    try {
      const res = await fetch("/api/intel/sources")
      const data = await res.json()
      setSources(data.sources || [])
    } catch (e) {
      console.error(e)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { fetchSources() }, [])

  const toggleActive = async (id: number, active: boolean) => {
    try {
      await fetch(`/api/intel/sources/${id}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ is_active: active ? 1 : 0 }),
      })
      fetchSources()
    } catch (e) {
      console.error(e)
    }
  }

  const deleteSource = async (id: number) => {
    if (!confirm("确定删除这个来源？关联的文章也会被删除。")) return
    try {
      await fetch(`/api/intel/sources/${id}`, { method: "DELETE" })
      fetchSources()
    } catch (e) {
      console.error(e)
    }
  }

  if (loading) {
    return <div className="py-8 text-center text-muted-foreground">加载中...</div>
  }

  return (
    <div className="space-y-3">
      {sources.map((s) => (
        <div key={s.id} className="p-4 rounded-xl bg-secondary/30 border border-border/40">
          <div className="flex items-start justify-between">
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2 mb-1">
                <h3 className="text-sm font-semibold">{s.name}</h3>
                <span className={cn(
                  "text-[10px] px-1.5 py-0.5 rounded-full font-medium",
                  s.type === "hermes" && "bg-chart-2/10 text-chart-2",
                  s.type === "rss" && "bg-chart-3/10 text-chart-3",
                  s.type === "manual" && "bg-chart-5/10 text-chart-5"
                )}>
                  {s.type}
                </span>
                {s.is_active ? (
                  <CheckCircle2 className="w-3.5 h-3.5 text-success" strokeWidth={1.5} />
                ) : (
                  <AlertCircle className="w-3.5 h-3.5 text-chart-2" strokeWidth={1.5} />
                )}
              </div>
              {s.url && <p className="text-xs text-muted-foreground truncate">{s.url}</p>}
              <div className="flex items-center gap-3 mt-2 text-[11px] text-muted-foreground/70">
                <span>{s.article_count} 篇文章</span>
                {s.last_fetch_at && <span>同步于 {new Date(s.last_fetch_at).toLocaleString("zh-CN")}</span>}
                {s.last_error && <span className="text-chart-2">错误: {s.last_error}</span>}
              </div>
            </div>
            <div className="flex items-center gap-1">
              {s.type === "rss" && (
                <>
                  <button
                    onClick={() => toggleActive(s.id, !s.is_active)}
                    className="p-1.5 hover:bg-secondary rounded-lg transition-colors"
                    title={s.is_active ? "暂停" : "恢复"}
                  >
                    {s.is_active ? (
                      <Pause className="w-3.5 h-3.5" strokeWidth={1.5} />
                    ) : (
                      <Play className="w-3.5 h-3.5" strokeWidth={1.5} />
                    )}
                  </button>
                  <button
                    onClick={() => onEdit(s)}
                    className="p-1.5 hover:bg-secondary rounded-lg transition-colors"
                    title="编辑"
                  >
                    <RefreshCw className="w-3.5 h-3.5" strokeWidth={1.5} />
                  </button>
                  <button
                    onClick={() => deleteSource(s.id)}
                    className="p-1.5 hover:bg-secondary rounded-lg transition-colors text-chart-2"
                    title="删除"
                  >
                    <Trash2 className="w-3.5 h-3.5" strokeWidth={1.5} />
                  </button>
                </>
              )}
            </div>
          </div>
        </div>
      ))}
    </div>
  )
}
```

- [ ] **Step 2: Create `components/intel/source-form.tsx`**

```tsx
"use client"

import { useState } from "react"
import { X } from "lucide-react"
import { cn } from "@/lib/utils"

const CATEGORIES = ["AI", "互联网", "金融", "创投", "工具", "阅读"]

interface SourceFormProps {
  source?: { id: number; name: string; url: string } | null
  onClose: () => void
  onSaved: () => void
}

export function SourceForm({ source, onClose, onSaved }: SourceFormProps) {
  const [name, setName] = useState(source?.name || "")
  const [url, setUrl] = useState(source?.url || "")
  const [category, setCategory] = useState("阅读")
  const [testing, setTesting] = useState(false)
  const [testResult, setTestResult] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  const handleTest = async () => {
    if (!url.trim()) return
    setTesting(true)
    setTestResult(null)
    try {
      const res = await fetch("/api/intel/scrape", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url: url.trim() }),
      })
      const data = await res.json()
      setTestResult(data.ok ? `可访问: ${data.title || "OK"}` : `失败: ${data.error}`)
    } catch (e) {
      setTestResult("请求失败")
    } finally {
      setTesting(false)
    }
  }

  const handleSubmit = async () => {
    if (!name.trim() || !url.trim()) return
    setSubmitting(true)
    try {
      const method = source ? "PUT" : "POST"
      const endpoint = source ? `/api/intel/sources/${source.id}` : "/api/intel/sources"
      const res = await fetch(endpoint, {
        method,
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: name.trim(),
          type: "rss",
          url: url.trim(),
          config: { category },
        }),
      })
      if (res.ok) {
        onSaved()
        onClose()
      }
    } catch (e) {
      console.error(e)
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="fixed inset-0 bg-black/40 backdrop-blur-sm z-50 flex items-center justify-center p-4">
      <div className="bg-card rounded-2xl border border-border/40 shadow-xl w-full max-w-md">
        <div className="flex items-center justify-between px-5 py-4 border-b border-border/40">
          <h2 className="text-base font-semibold">{source ? "编辑来源" : "新增 RSS 源"}</h2>
          <button onClick={onClose} className="p-1.5 hover:bg-secondary rounded-lg">
            <X className="w-4 h-4" strokeWidth={1.5} />
          </button>
        </div>

        <div className="px-5 py-4 space-y-4">
          <div>
            <label className="text-xs text-muted-foreground mb-1 block">名称</label>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="w-full px-3 py-2 rounded-lg bg-secondary/40 text-sm border border-border/40 focus:outline-none focus:ring-1 focus:ring-primary/30"
              placeholder="如: Hacker News"
            />
          </div>

          <div>
            <label className="text-xs text-muted-foreground mb-1 block">RSS URL</label>
            <div className="flex gap-2">
              <input
                type="url"
                value={url}
                onChange={(e) => setUrl(e.target.value)}
                className="flex-1 px-3 py-2 rounded-lg bg-secondary/40 text-sm border border-border/40 focus:outline-none focus:ring-1 focus:ring-primary/30"
                placeholder="https://example.com/feed.xml"
              />
              <button
                onClick={handleTest}
                disabled={testing || !url.trim()}
                className="px-3 py-2 rounded-lg bg-secondary/60 text-xs font-medium hover:bg-secondary disabled:opacity-50"
              >
                {testing ? "测试中..." : "测试"}
              </button>
            </div>
            {testResult && <p className={cn("text-xs mt-1", testResult.startsWith("失败") ? "text-chart-2" : "text-chart-3")}>{testResult}</p>}
          </div>

          <div>
            <label className="text-xs text-muted-foreground mb-1 block">默认分类</label>
            <div className="flex flex-wrap gap-1.5">
              {CATEGORIES.map((cat) => (
                <button
                  key={cat}
                  onClick={() => setCategory(cat)}
                  className={cn(
                    "px-3 py-1 rounded-lg text-xs font-medium transition-colors",
                    category === cat ? "bg-primary/10 text-primary" : "bg-secondary/40 text-muted-foreground hover:bg-secondary"
                  )}
                >
                  {cat}
                </button>
              ))}
            </div>
          </div>
        </div>

        <div className="px-5 py-4 border-t border-border/40 flex justify-end gap-2">
          <button onClick={onClose} className="px-4 py-2 rounded-lg text-sm text-muted-foreground hover:bg-secondary">取消</button>
          <button
            onClick={handleSubmit}
            disabled={submitting || !name.trim() || !url.trim()}
            className="px-4 py-2 rounded-lg bg-primary text-primary-foreground text-sm font-medium hover:bg-primary/90 disabled:opacity-50"
          >
            {submitting ? "保存中..." : "保存"}
          </button>
        </div>
      </div>
    </div>
  )
}
```

- [ ] **Step 3: Create `app/intel/sources/page.tsx`**

```tsx
"use client"

import { useState } from "react"
import { Plus } from "lucide-react"
import { SourceManager } from "@/components/intel/source-manager"
import { SourceForm } from "@/components/intel/source-form"

export default function SourcesPage() {
  const [showForm, setShowForm] = useState(false)
  const [editingSource, setEditingSource] = useState(null)
  const [refreshKey, setRefreshKey] = useState(0)

  const handleSaved = () => {
    setRefreshKey((k) => k + 1)
  }

  return (
    <div className="p-6 sm:p-8 max-w-4xl mx-auto h-full flex flex-col">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">信息源管理</h1>
          <p className="text-sm text-muted-foreground mt-1">管理 RSS 订阅与同步设置</p>
        </div>
        <button
          onClick={() => { setEditingSource(null); setShowForm(true) }}
          className="flex items-center gap-1.5 px-4 py-2 rounded-xl text-sm font-medium bg-primary/10 text-primary hover:bg-primary/15 transition-colors"
        >
          <Plus className="w-4 h-4" strokeWidth={1.5} />
          新增 RSS 源
        </button>
      </div>

      <div className="bg-card rounded-2xl p-5 sm:p-6 shadow-[var(--shadow-card)] border border-border/40 flex-1">
        <SourceManager
          key={refreshKey}
          onEdit={(s) => { setEditingSource(s); setShowForm(true) }}
        />
      </div>

      {showForm && (
        <SourceForm
          source={editingSource}
          onClose={() => setShowForm(false)}
          onSaved={handleSaved}
        />
      )}
    </div>
  )
}
```

- [ ] **Step 4: Commit**

```bash
git add nebula-share-frontend/app/intel/sources/page.tsx nebula-share-frontend/components/intel/source-manager.tsx nebula-share-frontend/components/intel/source-form.tsx
git commit -m "feat(intel): add source management page with RSS CRUD"
```

---

### Task 13: Add APScheduler for automatic sync

**Files:**
- Modify: `app.py`

- [ ] **Step 1: Add APScheduler to app.py**

After Flask app creation, add:

```python
from flask_apscheduler import APScheduler

scheduler = APScheduler()
scheduler.init_app(app)

@scheduler.task('interval', id='sync_hermes', minutes=10)
def scheduled_hermes_sync():
    with app.app_context():
        try:
            result = intel_sync.sync_hermes()
            print(f"[scheduler] Hermes sync: {result}")
        except Exception as e:
            print(f"[scheduler] Hermes sync failed: {e}")

@scheduler.task('interval', id='sync_rss', minutes=30)
def scheduled_rss_sync():
    with app.app_context():
        try:
            result = intel_sync.sync_all_rss()
            print(f"[scheduler] RSS sync: {result}")
        except Exception as e:
            print(f"[scheduler] RSS sync failed: {e}")

scheduler.start()
```

- [ ] **Step 2: Commit**

```bash
git add app.py
git commit -m "feat(intel): add scheduled sync for Hermes (10m) and RSS (30m)"
```

---

## Phase 4: Stats Panel + Polish (P2)

### Task 14: Add stats API and frontend panel

**Files:**
- Create: `components/intel/stats-panel.tsx`
- Modify: `app/intel/page.tsx` (add stats display)

- [ ] **Step 1: Create stats panel**

```tsx
"use client"

import { useState, useEffect } from "react"
import { BarChart3, BookOpen, Star, Eye } from "lucide-react"

interface Stats {
  total_articles: number
  unread_count: number
  starred_count: number
  category_breakdown: Record<string, number>
  source_breakdown: { name: string; count: number }[]
}

export function StatsPanel() {
  const [stats, setStats] = useState<Stats | null>(null)

  useEffect(() => {
    fetch("/api/intel/stats")
      .then((r) => r.json())
      .then((d) => setStats(d))
  }, [])

  if (!stats) return null

  const catEntries = Object.entries(stats.category_breakdown)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 6)

  return (
    <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-6">
      <div className="p-4 rounded-xl bg-card border border-border/40">
        <div className="flex items-center gap-2 mb-2">
          <BookOpen className="w-4 h-4 text-primary" strokeWidth={1.5} />
          <span className="text-xs text-muted-foreground">总文章</span>
        </div>
        <p className="text-2xl font-bold">{stats.total_articles}</p>
      </div>

      <div className="p-4 rounded-xl bg-card border border-border/40">
        <div className="flex items-center gap-2 mb-2">
          <Eye className="w-4 h-4 text-chart-3" strokeWidth={1.5} />
          <span className="text-xs text-muted-foreground">未读</span>
        </div>
        <p className="text-2xl font-bold">{stats.unread_count}</p>
      </div>

      <div className="p-4 rounded-xl bg-card border border-border/40">
        <div className="flex items-center gap-2 mb-2">
          <Star className="w-4 h-4 text-chart-1" strokeWidth={1.5} />
          <span className="text-xs text-muted-foreground">收藏</span>
        </div>
        <p className="text-2xl font-bold">{stats.starred_count}</p>
      </div>

      <div className="p-4 rounded-xl bg-card border border-border/40">
        <div className="flex items-center gap-2 mb-2">
          <BarChart3 className="w-4 h-4 text-chart-4" strokeWidth={1.5} />
          <span className="text-xs text-muted-foreground">分类</span>
        </div>
        <div className="space-y-1">
          {catEntries.map(([cat, count]) => (
            <div key={cat} className="flex items-center justify-between text-xs">
              <span className="text-muted-foreground">{cat}</span>
              <span className="font-medium">{count}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
```

- [ ] **Step 2: Wire stats into intel page**

Add import:
```tsx
import { StatsPanel } from "@/components/intel/stats-panel"
```

Add `<StatsPanel />` above the main card in the page.

- [ ] **Step 3: Commit**

```bash
git add nebula-share-frontend/components/intel/stats-panel.tsx nebula-share-frontend/app/intel/page.tsx
git commit -m "feat(intel): add stats panel to main page"
```

---

### Task 15: Final build and smoke test

**Files:**
- All modified files

- [ ] **Step 1: Build frontend**

```bash
cd nebula-share-frontend
npm run build
```

Expected: build succeeds with 0 errors.

- [ ] **Step 2: Restart Flask server**

```bash
# In one terminal or via systemd
python app.py
```

- [ ] **Step 3: Manual smoke test checklist**

Open `http://localhost:8080/intel` and verify:
- [ ] Hermes articles are loaded and displayed
- [ ] Search filters articles correctly
- [ ] Category pills filter articles
- [ ] Clicking article opens reader
- [ ] Mark as read works (bold title removed)
- [ ] Star/unstar works
- [ ] Archive works
- [ ] Create new article via form works
- [ ] Sync button triggers import
- [ ] Stats panel shows correct numbers
- [ ] Source management page loads
- [ ] Adding RSS source works
- [ ] `/api/intel/articles` returns JSON correctly

- [ ] **Step 4: Final commit**

```bash
git add -A
git commit -m "feat(intel): complete intelligence center with multi-source aggregation"
```

---

## Self-Review

### 1. Spec Coverage Check

| Spec Section | Implemented In | Status |
|---|---|---|
| SQLite schema (4 tables + indexes) | `intel_db.py` lines 1-90 | ✅ Task 2 |
| Source CRUD | `intel_db.py` + `app.py` routes | ✅ Tasks 2, 5 |
| Article CRUD + search/filter | `intel_db.py` + `app.py` routes | ✅ Tasks 2, 5 |
| Tags + article-tag associations | `intel_db.py` | ✅ Task 2 |
| Stats | `intel_db.py` + `app.py` | ✅ Tasks 2, 5, 14 |
| Hermes HTML parser | `intel_sync.py` | ✅ Task 4 |
| RSS collector | `intel_sync.py` | ✅ Task 4 |
| URL scraper | `intel_sync.py` | ✅ Task 4 |
| API routes (/api/intel/*) | `app.py` | ✅ Task 5 |
| Frontend article list | `article-list.tsx` + `article-list-item.tsx` | ✅ Task 7 |
| Frontend reader | `article-reader.tsx` | ✅ Task 7 |
| Search + filters | `search-bar.tsx` + `page.tsx` | ✅ Tasks 7, 8 |
| Manual entry | `article-form.tsx` | ✅ Task 10 |
| Tag selector | `tag-selector.tsx` | ✅ Task 9 |
| Source management | `source-manager.tsx` + `source-form.tsx` + `sources/page.tsx` | ✅ Task 12 |
| APScheduler | `app.py` | ✅ Task 13 |
| Stats panel | `stats-panel.tsx` | ✅ Task 14 |
| Dashboard update | `app/page.tsx` | ✅ Task 6 |

### 2. Placeholder Scan

- No TBD, TODO, or "implement later" found
- No "add appropriate error handling" without code
- No "similar to Task N" references
- All file paths are exact

### 3. Type Consistency

- `Article` interface matches database row structure
- API endpoints use consistent parameter names (`article_id`, `source_id`)
- Category names match between backend (`CATEGORIES` in `intel_db.py`) and frontend (`CATEGORIES` in `search-bar.tsx`)

### 4. Gap: No markdown rendering yet

The spec mentions `react-markdown` but the plan doesn't explicitly add it. This is acceptable for P0/P1 — content can be rendered as plain text or raw HTML initially. Add `react-markdown` in Phase 4 if needed.

---

## Execution Handoff

**Plan complete and saved to `docs/superpowers/plans/2026-06-10-intelligence-center.md`.**

**Two execution options:**

**1. Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, review between tasks, fast iteration. Good for catching issues early and keeping context clean.

**2. Inline Execution** — Execute tasks in this session using executing-plans, batch execution with checkpoints for review. Faster for straightforward mechanical work.

**Which approach?**
