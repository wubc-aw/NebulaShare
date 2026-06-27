#!/usr/bin/env python3
"""Intel Sync — Hermes parser, RSS collector, and URL scraper for NebulaShare."""

import hashlib
import os
import re
from datetime import datetime, timezone

import feedparser
import requests
from bs4 import BeautifulSoup

import intel_db

# ── Config ──────────────────────────────────────────────────────────

DAILY_NEWS_DIR = os.path.expanduser("~/.hermes/daily-news")

HERMES_CATEGORY_MAP = {
    "ai": "AI",
    "人工智能": "AI",
    "🤖 ai": "AI",
    "🤖 人工智能": "AI",
    "ai 工程实践": "AI工程实践",
    "🔧 ai 工程实践": "AI工程实践",
    "开源趋势": "开源趋势",
    "📦 开源趋势": "开源趋势",
    "internet": "互联网",
    "互联网": "互联网",
    "🌐 互联网": "互联网",
    "🌐 互联网/科技": "互联网",
    "美股": "金融",
    "📈 美股": "金融",
    "金融": "金融",
    "💰 金融": "金融",
    "📈 金融/宏观": "金融",
    "创投": "创投",
    "🚀 创投": "创投",
    "工具": "工具",
    "🛠 工具": "工具",
    "阅读": "阅读",
    "📚 阅读": "阅读",
}

# ── Helpers ─────────────────────────────────────────────────────────


def _now():
    """Return current UTC time as ISO 8601 string."""
    return datetime.now(timezone.utc).isoformat()


def _map_category(section_title):
    """Map a Hermes section title to a canonical category."""
    if not section_title:
        return "阅读"
    normalized = section_title.strip().lower()
    return HERMES_CATEGORY_MAP.get(normalized, "阅读")


# ── Hermes Parser ───────────────────────────────────────────────────


def _extract_articles_from_html(html, source_id, broadcast_date):
    """Parse a Hermes daily-news HTML file and return article dicts."""
    soup = BeautifulSoup(html, "lxml")
    articles = []

    for section in soup.find_all("div", class_="section"):
        h2 = section.find("h2")
        category = _map_category(h2.get_text(strip=True) if h2 else None)

        for article_div in section.find_all("div", class_="article"):
            # Author
            author_span = article_div.find("span", class_="source")
            author = author_span.get_text(strip=True) if author_span else None

            # Title + URL
            title_link = article_div.find("a", class_="title")
            if title_link:
                title = title_link.get_text(strip=True)
                url = title_link.get("href", "").strip()
            else:
                title_span = article_div.find("span", class_="title")
                title = title_span.get_text(strip=True) if title_span else "Untitled"
                url = ""

            # Summary
            summary_div = article_div.find("div", class_="summary")
            summary = summary_div.get_text(strip=True) if summary_div else None

            # External ID: MD5 of URL, or title if no URL
            id_source = url if url else title
            external_id = hashlib.md5(id_source.encode("utf-8")).hexdigest()

            articles.append(
                {
                    "source_id": source_id,
                    "external_id": external_id,
                    "title": title,
                    "summary": summary,
                    "url": url if url else None,
                    "author": author,
                    "published_at": broadcast_date,
                    "category": category,
                }
            )

    return articles


def sync_hermes():
    """Scan Hermes daily-news files and import new articles.

    Returns {"synced": N, "errors": M}
    """
    if not os.path.isdir(DAILY_NEWS_DIR):
        return {"synced": 0, "errors": 1}

    # Hermes source id is hard-coded to 1 per intel_db.init_db()
    source_id = 1
    synced = 0
    errors = 0

    files = sorted(
        f
        for f in os.listdir(DAILY_NEWS_DIR)
        if f.startswith("daily-news-") and f.endswith(".html")
    )

    for filename in files:
        filepath = os.path.join(DAILY_NEWS_DIR, filename)
        # Extract broadcast date from filename: daily-news-YYYY-MM-DD.html
        m = re.match(r"daily-news-(\d{4}-\d{2}-\d{2})\.html", filename)
        broadcast_date = m.group(1) if m else None

        try:
            with open(filepath, "r", encoding="utf-8") as f:
                html = f.read()
        except Exception:
            errors += 1
            continue

        try:
            articles = _extract_articles_from_html(html, source_id, broadcast_date)
        except Exception:
            errors += 1
            continue

        for art in articles:
            try:
                if intel_db.article_exists(art["source_id"], art["external_id"]):
                    continue
                intel_db.create_article(
                    source_id=art["source_id"],
                    title=art["title"],
                    external_id=art["external_id"],
                    summary=art["summary"],
                    url=art["url"],
                    author=art["author"],
                    published_at=art["published_at"],
                    category=art["category"],
                )
                synced += 1
            except Exception:
                errors += 1

    # Update source last_fetch_at regardless of new articles
    try:
        intel_db.update_source(source_id, last_fetch_at=_now())
    except Exception:
        errors += 1

    return {"synced": synced, "errors": errors}


# ── RSS Collector ───────────────────────────────────────────────────


def _parse_published(entry):
    """Extract ISO 8601 published_at from a feedparser entry."""
    # Prefer parsed struct
    pp = getattr(entry, "published_parsed", None) or getattr(entry, "updated_parsed", None)
    if pp:
        try:
            dt = datetime(*pp[:6], tzinfo=timezone.utc)
            return dt.isoformat()
        except Exception:
            pass

    # Fallback to raw string
    raw = getattr(entry, "published", None) or getattr(entry, "updated", None)
    if raw:
        return str(raw)
    return None


def sync_rss_source(source_id):
    """Fetch and import articles from a single RSS source.

    Returns {"synced": N, "errors": M}
    """
    source = intel_db.get_source(source_id)
    if not source:
        return {"synced": 0, "errors": 1}

    if source.get("type") != "rss":
        return {"synced": 0, "errors": 1}

    url = source.get("url")
    if not url:
        return {"synced": 0, "errors": 1}

    # Default category from source config
    default_category = None
    config_raw = source.get("config")
    if config_raw:
        import json

        try:
            cfg = json.loads(config_raw) if isinstance(config_raw, str) else config_raw
            default_category = cfg.get("category")
        except Exception:
            pass

    synced = 0
    errors = 0

    try:
        feed = feedparser.parse(url)
    except Exception as exc:
        intel_db.update_source(
            source_id,
            error_count=(source.get("error_count") or 0) + 1,
            last_error=str(exc),
        )
        return {"synced": 0, "errors": 1}

    # feedparser doesn't raise on HTTP errors; check status or bozo
    if hasattr(feed, "status") and feed.status >= 400:
        exc_msg = f"HTTP {feed.status}"
        intel_db.update_source(
            source_id,
            error_count=(source.get("error_count") or 0) + 1,
            last_error=exc_msg,
        )
        return {"synced": 0, "errors": 1}

    for entry in feed.entries:
        try:
            guid = (
                getattr(entry, "id", None)
                or getattr(entry, "guid", None)
                or getattr(entry, "link", None)
            )
            if not guid:
                continue

            external_id = hashlib.md5(str(guid).encode("utf-8")).hexdigest()

            if intel_db.article_exists(source_id, external_id):
                continue

            title = getattr(entry, "title", None) or "Untitled"
            link = getattr(entry, "link", None)
            summary = getattr(entry, "summary", None) or getattr(entry, "description", None)
            author = getattr(entry, "author", None)
            published_at = _parse_published(entry)
            category = default_category

            intel_db.create_article(
                source_id=source_id,
                title=title,
                external_id=external_id,
                summary=summary,
                url=link,
                author=author,
                published_at=published_at,
                category=category,
            )
            synced += 1
        except Exception:
            errors += 1

    # Update last_fetch_at; clear last_error on success
    try:
        intel_db.update_source(source_id, last_fetch_at=_now(), last_error=None)
    except Exception:
        errors += 1

    return {"synced": synced, "errors": errors}


def sync_all_rss():
    """Iterate all active RSS sources, auto-pause those with too many errors.

    Returns {"synced": N, "errors": M}
    """
    sources = intel_db.list_sources()
    total_synced = 0
    total_errors = 0

    for src in sources:
        if src.get("type") != "rss":
            continue
        if not src.get("is_active"):
            continue

        # Auto-pause sources with repeated failures
        if (src.get("error_count") or 0) >= 3:
            intel_db.update_source(src["id"], is_active=0)
            continue

        result = sync_rss_source(src["id"])
        total_synced += result["synced"]
        total_errors += result["errors"]

    return {"synced": total_synced, "errors": total_errors}


# ── URL Scraper ─────────────────────────────────────────────────────


def scrape_url(url):
    """Fetch and extract article content from a URL.

    Returns {"ok": True, "title": ..., "summary": ..., "content": ..., "url": ...}
    or {"ok": False, "error": ...}
    """
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        )
    }

    try:
        resp = requests.get(url, headers=headers, timeout=30)
        resp.raise_for_status()
    except Exception as exc:
        return {"ok": False, "error": str(exc)}

    try:
        soup = BeautifulSoup(resp.text, "lxml")
    except Exception as exc:
        return {"ok": False, "error": f"parse error: {exc}"}

    # Title
    title = None
    og_title = soup.find("meta", property="og:title")
    if og_title and og_title.get("content"):
        title = og_title["content"].strip()
    if not title:
        title_tag = soup.find("title")
        if title_tag:
            title = title_tag.get_text(strip=True)
    if not title:
        h1 = soup.find("h1")
        if h1:
            title = h1.get_text(strip=True)
    title = title or "Untitled"

    # Summary / description
    summary = None
    og_desc = soup.find("meta", property="og:description")
    if og_desc and og_desc.get("content"):
        summary = og_desc["content"].strip()
    if not summary:
        meta_desc = soup.find("meta", attrs={"name": "description"})
        if meta_desc and meta_desc.get("content"):
            summary = meta_desc["content"].strip()

    # Content: prefer article/main/.content, fall back to body
    content = None
    for selector in ("article", "main", ("div", {"class": "content"})):
        if isinstance(selector, tuple):
            tag, attrs = selector
            elem = soup.find(tag, attrs)
        else:
            elem = soup.find(selector)
        if elem:
            content = elem.get_text(separator="\n", strip=True)
            break

    if not content:
        body = soup.find("body")
        if body:
            content = body.get_text(separator="\n", strip=True)

    return {
        "ok": True,
        "title": title,
        "summary": summary,
        "content": content,
        "url": url,
    }
