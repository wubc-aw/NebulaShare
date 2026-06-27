#!/usr/bin/env python3
"""Deep summarizer — use Kimi K2.7 to generate structured deep summaries for articles."""

import os
import re

import requests

# ── Config ──────────────────────────────────────────────────────────

KIMI_API_KEY = os.environ.get("KIMI_API_KEY")
KIMI_BASE_URL = os.environ.get("KIMI_BASE_URL", "https://api.kimi.com/coding")
KIMI_MODEL = os.environ.get("KIMI_SUMMARY_MODEL", "kimi-k2.7-code")

# Try loading from .env if not in environment
if not KIMI_API_KEY:
    _env_path = os.path.expanduser("~/.hermes/.env")
    if os.path.exists(_env_path):
        with open(_env_path, "r") as f:
            for line in f:
                if line.startswith("KIMI_API_KEY="):
                    KIMI_API_KEY = line.strip().split("=", 1)[1]
                    break


# ── Prompt ──────────────────────────────────────────────────────────

DEEP_SUMMARY_PROMPT = """你是一位资深分析师。请对以下文章进行深度分析，输出结构化的总结。

要求：
1. 用中文输出
2. 分区块呈现，每个区块有明确标题
3. 内容要具体、有信息量，不要泛泛而谈
4. 如果文章涉及技术，请分析技术原理和创新点
5. 如果文章涉及商业/金融，请分析影响和投资逻辑
6. 如果文章涉及政策，请分析政策背景和潜在影响

输出格式（严格按此格式）：

## 核心要点
（用 2-4 个 bullet point 概括文章最关键的信息）

## 详细分析
（对文章内容进行逐层深入分析，300-500 字）

## 关键数据/事实
（提取文章中的具体数据、数字、时间线等）

## 影响与意义
（分析这件事对行业、市场、技术生态等的潜在影响）

## 值得关注的后续
（列出 2-3 个值得跟踪的后续发展或问题）

---

文章标题：{title}
文章摘要：{summary}
{content_block}
---
"""


# ── Core ────────────────────────────────────────────────────────────


def generate_deep_summary(title: str, summary: str = "", content: str = "") -> str:
    """Generate a structured deep summary using Kimi K2.7.

    Returns the markdown-formatted deep summary, or raises on failure.
    """
    if not KIMI_API_KEY:
        raise RuntimeError("KIMI_API_KEY not configured")

    content_block = f"\n文章内容：{content}" if content else ""
    prompt = DEEP_SUMMARY_PROMPT.format(
        title=title,
        summary=summary or "（无摘要）",
        content_block=content_block,
    )

    resp = requests.post(
        f"{KIMI_BASE_URL}/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {KIMI_API_KEY}",
            "Content-Type": "application/json",
        },
        json={
            "model": KIMI_MODEL,
            "messages": [
                {"role": "system", "content": "你是一位资深技术分析师和商业分析师，擅长从文章中提炼关键信息并进行深度解读。"},
                {"role": "user", "content": prompt},
            ],
            "temperature": 1,
            "max_tokens": 2048,
        },
        timeout=120,
    )
    resp.raise_for_status()
    data = resp.json()
    return data["choices"][0]["message"]["content"].strip()


def generate_deep_summary_for_article(article: dict) -> str:
    """Convenience wrapper: pass an article dict (with title, summary, content keys)."""
    return generate_deep_summary(
        title=article.get("title", ""),
        summary=article.get("summary", ""),
        content=article.get("content", ""),
    )
