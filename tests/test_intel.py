#!/usr/bin/env python3
"""Pytest suite for the NebulaShare intelligence database layer."""

import sys
import os
import tempfile

# Ensure intel_db is importable from the project root
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
import intel_db


@pytest.fixture(autouse=True)
def temp_db(monkeypatch):
    """Provide an isolated, temporary SQLite database for every test."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    monkeypatch.setattr(intel_db, "DB_PATH", db_path)
    intel_db.init_db()
    yield
    os.unlink(db_path)


# ── 1. Init ─────────────────────────────────────────────────────────

def test_init_db_creates_tables():
    """init_db should create schema and seed 2 sources + 4 tags."""
    sources = intel_db.list_sources()
    assert len(sources) == 2
    assert sources[0]["name"] == "Hermes 播报"
    assert sources[1]["name"] == "手动录入"

    tags = intel_db.list_tags()
    assert len(tags) == 4
    tag_names = {t["name"] for t in tags}
    assert tag_names == {"必读", "稍后读", "项目参考", "投资相关"}


# ── 2. Sources ──────────────────────────────────────────────────────

def test_create_and_get_source():
    """Creating an RSS source should make it retrievable by id."""
    sid = intel_db.create_source("Hacker News", "rss", url="https://news.ycombinator.com/rss")
    src = intel_db.get_source(sid)
    assert src is not None
    assert src["name"] == "Hacker News"
    assert src["type"] == "rss"
    assert src["url"] == "https://news.ycombinator.com/rss"
    assert src["is_active"] == 1


# ── 3. Articles ─────────────────────────────────────────────────────

def test_create_article():
    """Creating an article with all fields should store it correctly."""
    sid = intel_db.create_source("Test Feed", "rss")
    aid = intel_db.create_article(
        source_id=sid,
        title="The Future of Edge Computing",
        external_id="abc123",
        summary="A deep dive into edge computing trends.",
        content="Full article body here...",
        url="https://example.com/edge",
        author="Ada Lovelace",
        published_at="2026-06-01T00:00:00+00:00",
        category="tech",
    )
    article = intel_db.get_article(aid)
    assert article is not None
    assert article["title"] == "The Future of Edge Computing"
    assert article["external_id"] == "abc123"
    assert article["summary"] == "A deep dive into edge computing trends."
    assert article["content"] == "Full article body here..."
    assert article["url"] == "https://example.com/edge"
    assert article["author"] == "Ada Lovelace"
    assert article["date"] == "2026-06-01T00:00:00+00:00"
    assert article["category"] == "tech"
    assert article["is_read"] == 0
    assert article["is_starred"] == 0
    assert article["source"] == "Test Feed"
    assert article["tags"] == []


# ── 4. Pagination ───────────────────────────────────────────────────

def test_list_articles_pagination():
    """list_articles should honour per_page and page, and report total."""
    sid = intel_db.create_source("Multi Feed", "rss")
    for i in range(5):
        intel_db.create_article(
            source_id=sid,
            title=f"Article {i + 1}",
            summary=f"Summary {i + 1}",
        )

    page1, total1 = intel_db.list_articles(page=1, per_page=2)
    assert len(page1) == 2
    assert total1 == 5

    page2, total2 = intel_db.list_articles(page=2, per_page=2)
    assert len(page2) == 2
    assert total2 == 5

    page3, total3 = intel_db.list_articles(page=3, per_page=2)
    assert len(page3) == 1
    assert total3 == 5


# ── 5. Tags ─────────────────────────────────────────────────────────

def test_article_tags():
    """Tags can be attached, queried, and removed from articles."""
    sid = intel_db.create_source("Tag Feed", "rss")
    aid = intel_db.create_article(source_id=sid, title="Tagged Article")

    tid = intel_db.create_tag("Cosmic", "#8b5cf6")
    intel_db.add_article_tag(aid, tid)

    article = intel_db.get_article(aid)
    assert len(article["tags"]) == 1
    assert article["tags"][0]["name"] == "Cosmic"
    assert article["tags"][0]["color"] == "#8b5cf6"

    # Remove all tags via set_article_tags
    intel_db.set_article_tags(aid, [])
    article = intel_db.get_article(aid)
    assert article["tags"] == []


# ── 6. Search ───────────────────────────────────────────────────────

def test_search_articles():
    """Search should filter by title, summary, or content."""
    sid = intel_db.create_source("Search Feed", "rss")
    intel_db.create_article(source_id=sid, title="Quantum Computing", summary="QC summary")
    intel_db.create_article(source_id=sid, title="Neural Networks", summary="NN summary with quantum")
    intel_db.create_article(source_id=sid, title="Blockchain", summary="BC summary")

    results, total = intel_db.list_articles(search="quantum")
    assert total == 2
    titles = {r["title"] for r in results}
    assert titles == {"Quantum Computing", "Neural Networks"}

    results2, total2 = intel_db.list_articles(search="Blockchain")
    assert total2 == 1
    assert results2[0]["title"] == "Blockchain"

    results3, total3 = intel_db.list_articles(search="nonexistent")
    assert total3 == 0


# ── 7. Update ───────────────────────────────────────────────────────

def test_update_article():
    """Updating is_read and is_starred should persist correctly."""
    sid = intel_db.create_source("Update Feed", "rss")
    aid = intel_db.create_article(source_id=sid, title="Update Me")

    updated = intel_db.update_article(aid, is_read=1, is_starred=1)
    assert updated["is_read"] == 1
    assert updated["is_starred"] == 1

    fetched = intel_db.get_article(aid)
    assert fetched["is_read"] == 1
    assert fetched["is_starred"] == 1

    # Toggle back
    intel_db.update_article(aid, is_read=0, is_starred=0)
    fetched2 = intel_db.get_article(aid)
    assert fetched2["is_read"] == 0
    assert fetched2["is_starred"] == 0


# ── 8. Stats ────────────────────────────────────────────────────────

def test_stats():
    """get_stats should reflect correct counts across categories."""
    sid = intel_db.create_source("Stats Feed", "rss")
    a1 = intel_db.create_article(source_id=sid, title="A1", category="tech")
    a2 = intel_db.create_article(source_id=sid, title="A2", category="tech")
    a3 = intel_db.create_article(source_id=sid, title="A3", category="finance")

    # Set states via update_article since create_article doesn't accept them
    intel_db.update_article(a1, is_read=1)
    intel_db.update_article(a2, is_starred=1)

    stats = intel_db.get_stats()
    assert stats["total_articles"] == 3
    assert stats["unread_count"] == 2
    assert stats["starred_count"] == 1
    assert stats["category_breakdown"] == {"tech": 2, "finance": 1}

    src_stats = stats["source_breakdown"]
    # 2 seeded sources + 1 created source
    assert len(src_stats) == 3
    stats_feed = next(s for s in src_stats if s["name"] == "Stats Feed")
    assert stats_feed["cnt"] == 3
