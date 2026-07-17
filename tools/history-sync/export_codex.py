#!/usr/bin/env python3
"""
Codex history exporter.
Parses ~/.codex/state_5.sqlite and ~/.codex/sessions/**/*.jsonl,
copies generated images, and emits a unified HistoryData JSON.
"""

import argparse
import json
import os
import re
import shutil
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def log(msg: str) -> None:
    print(f"  {msg}")


def parse_iso(ts: str) -> datetime:
    # Handle both 'Z' and '+00:00'
    ts = ts.replace("Z", "+00:00")
    return datetime.fromisoformat(ts)


def extract_text_from_blocks(content: Any) -> str:
    """Extract readable text from Codex message content blocks."""
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return str(content) if content is not None else ""

    texts = []
    for block in content:
        if not isinstance(block, dict):
            continue
        bt = block.get("type", "")
        if bt == "input_text":
            texts.append(block.get("text", ""))
        elif bt == "output_text":
            texts.append(block.get("text", ""))
        elif bt == "text":
            texts.append(block.get("text", ""))
        elif bt == "thinking":
            t = block.get("thinking", "")
            if t:
                texts.append(f"[思考] {t}")
        elif bt == "tool_use":
            texts.append(f"[使用工具: {block.get('name', '')}]")
        elif bt == "tool_result":
            texts.append("[工具结果]")
        elif bt == "image_url":
            # Generated images usually appear as separate media files
            pass
    return "\n".join(texts)


def is_system_user_message(text: str) -> bool:
    """Filter out Codex system-injected user messages."""
    if not text:
        return True
    if text.startswith("# AGENTS.md instructions"):
        return True
    if text.startswith("<turn_aborted>"):
        return True
    if text.startswith("<environment_context>"):
        return True
    if text.startswith("<collaboration_mode>"):
        return True
    return False


def clean_text(text: str) -> str:
    if not text:
        return ""
    # Strip XML artifacts
    text = re.sub(r'<command-name>.*?</command-name>', '', text, flags=re.DOTALL)
    text = re.sub(r'<command-message>.*?</command-message>', '', text, flags=re.DOTALL)
    text = re.sub(r'<local-command-caveat>.*?</local-command-caveat>', '', text, flags=re.DOTALL)
    text = re.sub(r'<[^>]+>', '', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def clean_title(title: str) -> str:
    title = clean_text(title)
    title = re.sub(r'</?command[^>]*>', '', title, flags=re.IGNORECASE)
    title = re.sub(r'\bcommand\b', '', title, flags=re.IGNORECASE)
    title = re.sub(r'\s+', ' ', title).strip()
    return title or "未命名会话"


def load_threads(db_path: Path) -> dict[str, dict[str, Any]]:
    """Load thread metadata from Codex state sqlite."""
    threads = {}
    if not db_path.exists():
        return threads
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute(
        """
        SELECT id, rollout_path, title, cwd, created_at, updated_at,
               tokens_used, source, model, reasoning_effort, preview,
               first_user_message, agent_nickname, agent_role
        FROM threads
        """
    )
    for row in cur.fetchall():
        threads[row["id"]] = dict(row)
    conn.close()
    return threads


def parse_rollout(rollout_path: Path) -> dict[str, Any]:
    """Parse a Codex rollout JSONL file into structured messages and turns."""
    messages = []
    turns = []
    current_turn_id = None
    session_meta = {}

    if not rollout_path.exists():
        return {"session_meta": session_meta, "messages": messages, "turns": turns}

    with open(rollout_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue

            etype = obj.get("type")
            payload = obj.get("payload", {})
            ts = obj.get("timestamp", "")

            if etype == "session_meta":
                session_meta = payload
            elif etype == "turn_context":
                current_turn_id = payload.get("turn_id")
                turns.append(payload)
            elif etype == "response_item":
                if payload.get("type") != "message":
                    continue
                role = payload.get("role")
                if role not in ("user", "assistant"):
                    continue
                content = payload.get("content", [])
                text = extract_text_from_blocks(content)
                if role == "user" and is_system_user_message(text):
                    continue
                text = clean_text(text)
                if not text:
                    continue
                messages.append(
                    {
                        "role": role,
                        "text": text,
                        "timestamp": ts,
                        "turnId": current_turn_id,
                    }
                )

    return {"session_meta": session_meta, "messages": messages, "turns": turns}


def find_images_for_thread(
    thread_id: str, generated_images_dir: Path
) -> list[dict[str, Any]]:
    """Find generated images associated with a thread."""
    images = []
    if not generated_images_dir.exists():
        return images

    # Codex stores images either as {thread_id}/{filename} or {thread_id}.{ext}
    candidates = []
    thread_dir = generated_images_dir / thread_id
    if thread_dir.is_dir():
        candidates.extend(thread_dir.iterdir())
    else:
        for ext in ("png", "jpg", "jpeg", "gif", "webp"):
            candidate = generated_images_dir / f"{thread_id}.{ext}"
            if candidate.exists():
                candidates.append(candidate)
        # Also try prefix match for filenames like {thread_id}-*.png
        for f in generated_images_dir.iterdir():
            if f.is_file() and f.stem.startswith(thread_id):
                candidates.append(f)

    for f in candidates:
        if f.is_file():
            images.append(
                {
                    "filename": f.name,
                    "path": f,
                    "type": "image",
                }
            )
    return images


def export_codex_history(
    codex_dir: Path,
    output_dir: Path,
    hostname: str,
    platform: str = "unknown",
) -> Path:
    """Export all Codex history to output_dir. Returns path to history.json."""
    state_db = codex_dir / "state_5.sqlite"
    sessions_dir = codex_dir / "sessions"
    generated_images_dir = codex_dir / "generated_images"

    output_dir.mkdir(parents=True, exist_ok=True)
    images_dir = output_dir / "images"
    images_dir.mkdir(parents=True, exist_ok=True)

    threads = load_threads(state_db)
    log(f"Loaded {len(threads)} threads from state DB")

    sessions = []
    total_messages = 0
    total_tokens = 0
    projects: dict[str, int] = {}
    skipped = 0

    for thread_id, thread in threads.items():
        rollout_path = Path(thread.get("rollout_path", ""))
        if not rollout_path.is_absolute():
            rollout_path = codex_dir / rollout_path
        if not rollout_path.exists():
            rollout_path = sessions_dir / f"{thread_id}.jsonl"
        if not rollout_path.exists():
            skipped += 1
            continue

        parsed = parse_rollout(rollout_path)
        messages = parsed["messages"]
        if not messages:
            skipped += 1
            continue

        # Determine project from cwd
        cwd = thread.get("cwd") or parsed["session_meta"].get("cwd") or "/unknown"
        projects[cwd] = projects.get(cwd, 0) + 1

        # Time range
        created_at = thread.get("created_at") or 0
        updated_at = thread.get("updated_at") or created_at
        start_time = datetime.fromtimestamp(created_at, tz=timezone.utc).isoformat()
        end_time = datetime.fromtimestamp(updated_at, tz=timezone.utc).isoformat()

        # Use first user message as title fallback
        title = thread.get("title") or ""
        if not title:
            for m in messages:
                if m["role"] == "user":
                    title = m["text"]
                    break
        title = clean_title(title)

        # Copy images
        media = []
        images = find_images_for_thread(thread_id, generated_images_dir)
        if images:
            session_img_dir = images_dir / thread_id
            session_img_dir.mkdir(parents=True, exist_ok=True)
            for img in images:
                dest = session_img_dir / img["filename"]
                shutil.copy2(img["path"], dest)
                media.append(
                    {
                        "type": "image",
                        "filename": img["filename"],
                        "url": f"/history-media/{hostname}/{thread_id}/{img['filename']}",
                    }
                )

        usage = {
            "inputTokens": 0,
            "outputTokens": 0,
            "totalTokens": thread.get("tokens_used") or 0,
            "estimatedCost": 0.0,
            "toolCalls": 0,
        }
        total_tokens += usage["totalTokens"]

        sessions.append(
            {
                "sessionId": thread_id,
                "title": title,
                "project": cwd,
                "messageCount": len(messages),
                "startTime": start_time,
                "endTime": end_time,
                "messages": messages,
                "hasFullDialog": True,
                "source": "codex",
                "deviceName": hostname,
                "deviceId": hostname,
                "usage": usage,
                "media": media,
            }
        )
        total_messages += len(messages)

    sessions.sort(key=lambda s: s["startTime"], reverse=True)

    data = {
        "meta": {
            "generatedAt": datetime.now(tz=timezone.utc).isoformat(),
            "totalSessions": len(sessions),
            "totalMessages": total_messages,
            "projects": projects,
            "devices": {
                hostname: {
                    "hostname": hostname,
                    "machineId": hostname,
                    "localIp": "unknown",
                    "platform": platform,
                    "lastSync": datetime.now(tz=timezone.utc).isoformat(),
                    "sessions": len(sessions),
                    "messages": total_messages,
                }
            },
            "deviceCount": 1,
            "totalTokens": {
                "input": 0,
                "output": 0,
                "total": total_tokens,
                "estimatedCostUSD": 0.0,
            },
            "sources": {"codex": len(sessions)},
        },
        "sessions": sessions,
    }

    history_path = output_dir / "history.json"
    with open(history_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    log(f"Exported {len(sessions)} sessions, {total_messages} messages")
    log(f"Skipped {skipped} threads (missing rollout or empty)")
    log(f"Images: {sum(len(s.get('media', [])) for s in sessions)}")
    log(f"Output: {history_path}")
    return history_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Export Codex history")
    parser.add_argument(
        "--codex-dir",
        type=Path,
        default=Path.home() / ".codex",
        help="Path to ~/.codex directory",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path.cwd() / "codex-export",
        help="Output directory",
    )
    parser.add_argument(
        "--hostname",
        default=os.uname().nodename,
        help="Device hostname identifier",
    )
    parser.add_argument(
        "--platform",
        default=f"{os.uname().sysname}-{os.uname().machine}",
        help="Platform string",
    )
    args = parser.parse_args()

    export_codex_history(
        codex_dir=args.codex_dir,
        output_dir=args.output_dir,
        hostname=args.hostname,
        platform=args.platform,
    )


if __name__ == "__main__":
    main()
