#!/usr/bin/env python3
"""Intel DB — SQLite layer for the NebulaShare Intelligence Center."""

import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
import json

# ── Config ──────────────────────────────────────────────────────────

DB_PATH = os.path.join(os.path.expanduser("~/.config/nebulashare"), "intel.db")

# ── Schema ──────────────────────────────────────────────────────────

SCHEMA_SQL = """
-- Sources: where intelligence flows in from
CREATE TABLE IF NOT EXISTS sources (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    name          TEXT    NOT NULL,
    type          TEXT    NOT NULL CHECK(type IN ('hermes','rss','manual')),
    url           TEXT,
    config        TEXT,                       -- JSON blob
    is_active     INTEGER NOT NULL DEFAULT 1, -- 0 or 1
    last_fetch_at TEXT,
    last_error    TEXT,
    error_count   INTEGER NOT NULL DEFAULT 0,
    created_at    TEXT    DEFAULT CURRENT_TIMESTAMP
);

-- Articles: the raw signal
CREATE TABLE IF NOT EXISTS articles (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id   INTEGER NOT NULL,
    external_id TEXT,                         -- id from upstream
    title       TEXT    NOT NULL,
    summary     TEXT,
    content     TEXT,
    url         TEXT,
    author      TEXT,
    published_at TEXT,
    category    TEXT,
    is_read     INTEGER NOT NULL DEFAULT 0,   -- 0 or 1
    is_starred  INTEGER NOT NULL DEFAULT 0,   -- 0 or 1
    is_archived INTEGER NOT NULL DEFAULT 0,   -- 0 or 1
    fetched_at  TEXT    DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (source_id) REFERENCES sources(id) ON DELETE CASCADE
);

-- Tags: categorical colour-coding
CREATE TABLE IF NOT EXISTS tags (
    id    INTEGER PRIMARY KEY AUTOINCREMENT,
    name  TEXT NOT NULL UNIQUE,
    color TEXT NOT NULL DEFAULT '#3b82f6'
);

-- Article-Tag junction
CREATE TABLE IF NOT EXISTS article_tags (
    article_id INTEGER NOT NULL,
    tag_id     INTEGER NOT NULL,
    PRIMARY KEY (article_id, tag_id),
    FOREIGN KEY (article_id) REFERENCES articles(id) ON DELETE CASCADE,
    FOREIGN KEY (tag_id)     REFERENCES tags(id)     ON DELETE CASCADE
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_articles_source    ON articles(source_id);
CREATE INDEX IF NOT EXISTS idx_articles_category  ON articles(category);
CREATE INDEX IF NOT EXISTS idx_articles_published ON articles(published_at);
CREATE INDEX IF NOT EXISTS idx_articles_starred   ON articles(is_starred) WHERE is_starred = 1;
CREATE INDEX IF NOT EXISTS idx_articles_archived  ON articles(is_archived) WHERE is_archived = 0;
CREATE INDEX IF NOT EXISTS idx_tags_name         ON tags(name);
"""

# ── Helpers ─────────────────────────────────────────────────────────

def _ensure_dir():
    """Ensure the parent directory for the database exists."""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)


@contextmanager
def _conn():
    """Yield a SQLite connection with Row factory and FK enforcement."""
    _ensure_dir()
    conn = sqlite3.connect(DB_PATH)
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


def _now():
    """Return current UTC time as ISO 8601 string."""
    return datetime.now(timezone.utc).isoformat()


def _row_to_dict(row):
    """Convert a sqlite3.Row to a plain dict."""
    return dict(row) if row else None


# ── Init ────────────────────────────────────────────────────────────

def init_db():
    """Create tables, indexes, seed default sources and tags."""
    with _conn() as conn:
        conn.executescript(SCHEMA_SQL)

        # Seed built-in sources
        conn.execute(
            """
            INSERT OR IGNORE INTO sources (id, name, type, created_at)
            VALUES (1, 'Hermes 播报', 'hermes', ?)
            """,
            (_now(),),
        )
        conn.execute(
            """
            INSERT OR IGNORE INTO sources (id, name, type, created_at)
            VALUES (2, '手动录入', 'manual', ?)
            """,
            (_now(),),
        )

        # Seed default tags
        default_tags = [
            ("必读", "#ef4444"),
            ("稍后读", "#f59e0b"),
            ("项目参考", "#3b82f6"),
            ("投资相关", "#22c55e"),
        ]
        for name, color in default_tags:
            conn.execute(
                "INSERT OR IGNORE INTO tags (name, color) VALUES (?, ?)",
                (name, color),
            )


# ── Sources CRUD ────────────────────────────────────────────────────

def list_sources():
    """Return all sources with article_count."""
    with _conn() as conn:
        rows = conn.execute(
            """
            SELECT s.*, COUNT(a.id) AS article_count
            FROM sources s
            LEFT JOIN articles a ON a.source_id = s.id
            GROUP BY s.id
            ORDER BY s.id
            """
        ).fetchall()
        return [_row_to_dict(r) for r in rows]


def get_source(source_id):
    """Return a single source by id."""
    with _conn() as conn:
        row = conn.execute(
            "SELECT * FROM sources WHERE id = ?", (source_id,)
        ).fetchone()
        return _row_to_dict(row)


def create_source(name, type_, url=None, config=None, is_active=1):
    """Create a new source. Returns the new source id."""
    config_json = json.dumps(config, ensure_ascii=False) if config else None
    with _conn() as conn:
        cur = conn.execute(
            """
            INSERT INTO sources (name, type, url, config, is_active, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (name, type_, url, config_json, int(is_active), _now()),
        )
        return cur.lastrowid


def update_source(source_id, **fields):
    """Update arbitrary fields on a source."""
    allowed_map = {
        "name": "name",
        "url": "url",
        "config": "config",
        "is_active": "is_active",
        "category": "category",
        "last_fetch_at": "last_fetch_at",
        "last_error": "last_error",
        "error_count": "error_count",
    }
    updates = {allowed_map[k]: v for k, v in fields.items() if k in allowed_map}
    if not updates:
        return get_source(source_id)
    if "config" in updates and updates["config"] is not None:
        updates["config"] = json.dumps(updates["config"], ensure_ascii=False)
    sets = ", ".join(f"{col} = ?" for col in updates)
    vals = list(updates.values()) + [source_id]
    with _conn() as conn:
        conn.execute(f"UPDATE sources SET {sets} WHERE id = ?", vals)
        row = conn.execute("SELECT * FROM sources WHERE id = ?", (source_id,)).fetchone()
        return _row_to_dict(row)


def delete_source(source_id):
    """Delete a source (cascades to articles via FK)."""
    with _conn() as conn:
        conn.execute("DELETE FROM sources WHERE id = ?", (source_id,))


# ── Articles CRUD ───────────────────────────────────────────────────

def list_articles(
    category=None,
    search=None,
    starred=None,
    unread=None,
    archived=None,
    source_id=None,
    tag=None,
    page=1,
    per_page=20,
):
    """Return (articles, total_count) with optional filtering and pagination."""
    where_clauses = []
    params = []

    if category is not None:
        where_clauses.append("a.category = ?")
        params.append(category)
    if search is not None:
        where_clauses.append(
            "(a.title LIKE ? OR a.summary LIKE ? OR a.content LIKE ?)"
        )
        like = f"%{search}%"
        params.extend([like, like, like])
    if starred is not None:
        where_clauses.append("a.is_starred = ?")
        params.append(1 if starred else 0)
    if unread is not None:
        where_clauses.append("a.is_read = ?")
        params.append(0 if unread else 1)
    if archived is not None:
        where_clauses.append("a.is_archived = ?")
        params.append(1 if archived else 0)
    if source_id is not None:
        where_clauses.append("a.source_id = ?")
        params.append(source_id)
    if tag is not None:
        where_clauses.append(
            "a.id IN (SELECT article_id FROM article_tags at JOIN tags t ON t.id = at.tag_id WHERE t.name = ?)"
        )
        params.append(tag)

    where_sql = "WHERE " + " AND ".join(where_clauses) if where_clauses else ""

    with _conn() as conn:
        total_row = conn.execute(
            f"SELECT COUNT(*) FROM articles a {where_sql}", params
        ).fetchone()
        total = total_row[0] if total_row else 0

        offset = (page - 1) * per_page
        rows = conn.execute(
            f"""
            SELECT a.*, s.name AS source_name
            FROM articles a
            JOIN sources s ON a.source_id = s.id
            {where_sql}
            ORDER BY a.fetched_at DESC
            LIMIT ? OFFSET ?
            """,
            params + [per_page, offset],
        ).fetchall()

        articles = [_row_to_dict(r) for r in rows]
        return articles, total


def get_article(article_id):
    """Return article with source info and tags."""
    with _conn() as conn:
        row = conn.execute(
            """
            SELECT a.*, s.name AS source_name
            FROM articles a
            JOIN sources s ON a.source_id = s.id
            WHERE a.id = ?
            """,
            (article_id,),
        ).fetchone()
        if not row:
            return None
        article = _row_to_dict(row)
        tag_rows = conn.execute(
            "SELECT t.* FROM tags t JOIN article_tags at ON at.tag_id = t.id WHERE at.article_id = ?",
            (article_id,),
        ).fetchall()
        article["tags"] = [_row_to_dict(r) for r in tag_rows]
        return article


def create_article(
    source_id,
    title,
    external_id=None,
    summary=None,
    content=None,
    url=None,
    author=None,
    published_at=None,
    category=None,
):
    """Create a new article. Returns the new article id."""
    with _conn() as conn:
        cur = conn.execute(
            """
            INSERT INTO articles
                (source_id, external_id, title, summary, content, url,
                 author, published_at, category, fetched_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                source_id,
                external_id,
                title,
                summary,
                content,
                url,
                author,
                published_at,
                category,
                _now(),
            ),
        )
        return cur.lastrowid


def update_article(article_id, **fields):
    """Update arbitrary fields on an article."""
    allowed_map = {
        "title": "title",
        "summary": "summary",
        "content": "content",
        "url": "url",
        "author": "author",
        "published_at": "published_at",
        "category": "category",
        "is_read": "is_read",
        "is_starred": "is_starred",
        "is_archived": "is_archived",
    }
    updates = {allowed_map[k]: v for k, v in fields.items() if k in allowed_map}
    if not updates:
        return get_article(article_id)
    sets = ", ".join(f"{col} = ?" for col in updates)
    vals = list(updates.values()) + [article_id]
    with _conn() as conn:
        conn.execute(f"UPDATE articles SET {sets} WHERE id = ?", vals)
        row = conn.execute(
            """
            SELECT a.*, s.name AS source_name
            FROM articles a
            JOIN sources s ON a.source_id = s.id
            WHERE a.id = ?
            """,
            (article_id,),
        ).fetchone()
        if not row:
            return None
        article = _row_to_dict(row)
        tag_rows = conn.execute(
            "SELECT t.* FROM tags t JOIN article_tags at ON at.tag_id = t.id WHERE at.article_id = ?",
            (article_id,),
        ).fetchall()
        article["tags"] = [_row_to_dict(r) for r in tag_rows]
        return article


def delete_article(article_id):
    """Delete an article (cascades to article_tags via FK)."""
    with _conn() as conn:
        conn.execute("DELETE FROM articles WHERE id = ?", (article_id,))


def article_exists(source_id, external_id):
    """Check whether an article with this source+external_id already exists."""
    with _conn() as conn:
        row = conn.execute(
            "SELECT id FROM articles WHERE source_id = ? AND external_id = ?",
            (source_id, external_id),
        ).fetchone()
        return row is not None


# ── Tags CRUD ───────────────────────────────────────────────────────

def list_tags():
    """Return all tags with usage_count."""
    with _conn() as conn:
        rows = conn.execute(
            """
            SELECT t.*, COUNT(at.article_id) AS usage_count
            FROM tags t
            LEFT JOIN article_tags at ON at.tag_id = t.id
            GROUP BY t.id
            ORDER BY t.name
            """
        ).fetchall()
        return [_row_to_dict(r) for r in rows]


def get_tag(tag_id):
    """Return a single tag by id."""
    with _conn() as conn:
        row = conn.execute("SELECT * FROM tags WHERE id = ?", (tag_id,)).fetchone()
        return _row_to_dict(row)


def create_tag(name, color="#3b82f6"):
    """Create a new tag. Returns the new tag id."""
    with _conn() as conn:
        cur = conn.execute(
            "INSERT INTO tags (name, color) VALUES (?, ?)",
            (name, color),
        )
        return cur.lastrowid


def delete_tag(tag_id):
    """Delete a tag (cascades to article_tags via FK)."""
    with _conn() as conn:
        conn.execute("DELETE FROM tags WHERE id = ?", (tag_id,))


# ── Article-Tag associations ────────────────────────────────────────

def get_article_tags(article_id):
    """Return tags attached to an article."""
    with _conn() as conn:
        rows = conn.execute(
            """
            SELECT t.*
            FROM tags t
            JOIN article_tags at ON t.id = at.tag_id
            WHERE at.article_id = ?
            ORDER BY t.name
            """,
            (article_id,),
        ).fetchall()
        return [_row_to_dict(r) for r in rows]


def set_article_tags(article_id, tag_ids):
    """Replace all tags on an article with the given list of tag ids."""
    with _conn() as conn:
        conn.execute("DELETE FROM article_tags WHERE article_id = ?", (article_id,))
        for tid in tag_ids:
            conn.execute(
                "INSERT INTO article_tags (article_id, tag_id) VALUES (?, ?)",
                (article_id, tid),
            )


def add_article_tag(article_id, tag_id):
    """Attach a tag to an article (idempotent)."""
    with _conn() as conn:
        conn.execute(
            """
            INSERT OR IGNORE INTO article_tags (article_id, tag_id)
            VALUES (?, ?)
            """,
            (article_id, tag_id),
        )


def remove_article_tag(article_id, tag_id):
    """Detach a tag from an article."""
    with _conn() as conn:
        conn.execute(
            "DELETE FROM article_tags WHERE article_id = ? AND tag_id = ?",
            (article_id, tag_id),
        )


# ── Stats ───────────────────────────────────────────────────────────

def get_stats():
    """Return intelligence-center statistics."""
    with _conn() as conn:
        total = conn.execute("SELECT COUNT(*) FROM articles").fetchone()[0]
        unread = conn.execute(
            "SELECT COUNT(*) FROM articles WHERE is_read = 0"
        ).fetchone()[0]
        starred = conn.execute(
            "SELECT COUNT(*) FROM articles WHERE is_starred = 1"
        ).fetchone()[0]

        cat_rows = conn.execute(
            """
            SELECT category, COUNT(*) AS cnt
            FROM articles
            WHERE category IS NOT NULL
            GROUP BY category
            ORDER BY cnt DESC
            """
        ).fetchall()
        category_breakdown = {r["category"]: r["cnt"] for r in cat_rows}

        src_rows = conn.execute(
            """
            SELECT s.id, s.name, s.type, COUNT(a.id) AS cnt
            FROM sources s
            LEFT JOIN articles a ON s.id = a.source_id
            GROUP BY s.id
            ORDER BY s.id
            """
        ).fetchall()
        source_breakdown = [_row_to_dict(r) for r in src_rows]

    return {
        "total_articles": total,
        "unread_count": unread,
        "starred_count": starred,
        "category_breakdown": category_breakdown,
        "source_breakdown": source_breakdown,
    }


