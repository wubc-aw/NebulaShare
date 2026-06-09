#!/usr/bin/env python3
"""Sync local Claude Code history to NebulaShare (树莓派)"""
import json, os, subprocess, sys, urllib.request, uuid
from datetime import datetime
from pathlib import Path

DEFAULT_PI_URL = "http://100.101.154.44:8080"

def log(msg): print(f"  → {msg}")

def get_machine_info():
    hostname = "unknown"
    try:
        r = subprocess.run(["hostname"], capture_output=True, text=True)
        if r.returncode == 0: hostname = r.stdout.strip()
    except: pass
    home = str(Path.home())
    mid = str(uuid.uuid5(uuid.NAMESPACE_DNS, hostname + home))
    return {"hostname": hostname, "machineId": mid, "homeDir": home, "platform": sys.platform}

def extract_text(content):
    if isinstance(content, str): return content
    if isinstance(content, list):
        texts = []
        for b in content:
            if isinstance(b, dict):
                t = b.get("type","")
                if t == "text": texts.append(b.get("text",""))
                elif t == "thinking": texts.append(f"[思考] {b.get('thinking','')}")
                elif t == "tool_use": texts.append(f"[工具: {b.get('name','')}]")
                elif t == "tool_result": texts.append("[工具结果]")
        return "\n".join(texts)
    return str(content)

def parse_msg(obj, src, mi):
    msg = obj.get("message", {})
    content = msg.get("content", "" if obj.get("type")=="user" else [])
    text = extract_text(content)
    if not text.strip(): return None
    return {
        "role": "user" if obj.get("type")=="user" else "assistant",
        "text": text[:5000],
        "timestamp": obj.get("timestamp", ""),
        "sourceFile": src,
        "machineId": mi["machineId"],
        "hostname": mi["hostname"],
    }

def analyze_usage(fpath):
    """统计会话中的 token 使用量"""
    usage = {"inputTokens": 0, "outputTokens": 0, "cacheReadTokens": 0, "cacheWriteTokens": 0, "totalTokens": 0, "estimatedCost": 0.0}
    if not fpath.exists(): return usage
    try:
        with open(fpath, encoding="utf-8") as f:
            for line in f:
                obj = json.loads(line.strip())
                if obj.get("type") != "assistant": continue
                msg = obj.get("message", {})
                u = msg.get("usage", {})
                if not u: continue
                usage["inputTokens"] += u.get("input_tokens", 0)
                usage["outputTokens"] += u.get("output_tokens", 0)
                usage["cacheReadTokens"] += u.get("cache_read_input_tokens", 0)
                usage["cacheWriteTokens"] += u.get("cache_creation_input_tokens", 0)
    except Exception:
        pass
    usage["totalTokens"] = usage["inputTokens"] + usage["outputTokens"] + usage["cacheReadTokens"] + usage["cacheWriteTokens"]
    usage["estimatedCost"] = round((usage["inputTokens"] * 3 + usage["outputTokens"] * 15 + usage["cacheReadTokens"] * 0.375 + usage["cacheWriteTokens"] * 3) / 1_000_000, 4)
    return usage

def parse_session(fpath, mi):
    msgs = []
    if not fpath.exists(): return msgs
    try:
        with open(fpath, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line: continue
                try: obj = json.loads(line)
                except: continue
                if obj.get("type") in ("user", "assistant"):
                    m = parse_msg(obj, str(fpath), mi)
                    if m: msgs.append(m)
    except Exception as e:
        log(f"warn: {fpath.name} parse failed: {e}")
    msgs.sort(key=lambda x: x.get("timestamp",""))
    deduped = []
    for m in msgs:
        if deduped and deduped[-1]["role"] == m["role"]:
            deduped[-1]["text"] += "\n" + m["text"]
        else:
            deduped.append(dict(m))
    return deduped

def extract_all():
    claude_dir = Path.home() / ".claude"
    history_file = claude_dir / "history.jsonl"
    if not history_file.exists():
        log("ERROR: ~/.claude/history.jsonl not found")
        return None

    mi = get_machine_info()
    log(f"extracting from: {claude_dir}")
    log(f"device: {mi['hostname']}")

    session_info = {}
    projects_counts = {}
    with open(history_file, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line: continue
            try: obj = json.loads(line)
            except: continue
            disp = obj.get("display", "")
            if not disp or disp.startswith("/"): continue
            sid = obj.get("sessionId", "unknown")
            proj = obj.get("project", "unknown")
            ts = obj.get("timestamp", 0)
            if sid not in session_info or ts < session_info[sid]["firstTs"]:
                session_info[sid] = {"project": proj, "firstTs": ts, "firstDisplay": disp}
            projects_counts[proj] = projects_counts.get(proj, 0) + 1

    sessions = []
    tok_total = {"input": 0, "output": 0, "cacheRead": 0, "cacheWrite": 0, "total": 0, "cost": 0.0}
    TOK_MAP = {"inputTokens": "input", "outputTokens": "output", "cacheReadTokens": "cacheRead", "cacheWriteTokens": "cacheWrite", "totalTokens": "total", "estimatedCost": "cost"}

    for sid, info in session_info.items():
        proj_name = info["project"].strip("/").replace("/", "-")
        candidates = [
            claude_dir / "projects" / f"-{proj_name}" / f"{sid}.jsonl",
            claude_dir / "projects" / proj_name / f"{sid}.jsonl",
        ]
        sf = None
        for c in candidates:
            if c.exists(): sf = c; break
        if sf is None:
            sf = claude_dir / "projects" / f"-{proj_name}" / f"{sid}.jsonl"

        full_msgs = parse_session(sf, mi) if sf.exists() else []

        # Token 统计
        usage = analyze_usage(sf) if sf.exists() else {}
        for sk, dk in TOK_MAP.items():
            if sk in usage:
                tok_total[dk] += usage[sk]

        title = info["firstDisplay"][:80]
        if sf.exists():
            ai_title = None
            try:
                with open(sf, encoding="utf-8") as f:
                    for line in f:
                        try: obj = json.loads(line.strip())
                        except: continue
                        if obj and obj.get("type") == "ai-title":
                            ai_title = obj.get("title","").strip(); break
            except: pass
            if ai_title: title = ai_title
            elif full_msgs:
                for m in full_msgs:
                    if m["role"] == "user": title = m["text"][:80]; break

        timestamps = []
        for m in full_msgs:
            if m.get("timestamp"):
                try: timestamps.append(datetime.fromisoformat(m["timestamp"].replace("Z","+00:00")).timestamp())
                except: pass
        if timestamps:
            start_ts, end_ts = min(timestamps), max(timestamps)
        else:
            start_ts = end_ts = info["firstTs"] / 1000

        sessions.append({
            "sessionId": sid, "title": title, "project": info["project"],
            "messageCount": len(full_msgs),
            "startTime": datetime.fromtimestamp(start_ts).isoformat(),
            "endTime": datetime.fromtimestamp(end_ts).isoformat(),
            "startTimeMs": int(start_ts * 1000), "endTimeMs": int(end_ts * 1000),
            "messages": full_msgs, "hasFullDialog": len(full_msgs) > 0,
            "sourceFile": str(sf) if sf.exists() else None,
            "machineId": mi["machineId"], "hostname": mi["hostname"],
        })

    sessions.sort(key=lambda x: x["startTimeMs"], reverse=True)
    return {
        "meta": {
            "generatedAt": datetime.now().isoformat(),
            "totalSessions": len(sessions),
            "totalMessages": sum(s["messageCount"] for s in sessions),
            "projects": projects_counts,
            "machineInfo": mi,
            "sourceDir": str(claude_dir),
            "version": "1.2.1-sync",
            "totalTokens": {
                "input": int(tok_total["input"]),
                "output": int(tok_total["output"]),
                "cacheRead": int(tok_total["cacheRead"]),
                "cacheWrite": int(tok_total["cacheWrite"]),
                "total": int(tok_total["total"]),
                "estimatedCostUSD": round(tok_total["cost"], 4),
            },
        },
        "sessions": sessions,
    }

def upload(data, url):
    payload = json.dumps(data, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url, data=payload,
        headers={"Content-Type": "application/json", "Content-Length": str(len(payload))},
        method="POST")
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        return {"ok": False, "error": str(e)}

def get_remote_sessions(base_url: str, hostname: str) -> int:
    """获取服务端该设备已有的会话数"""
    try:
        req = urllib.request.Request(f"{base_url}/api/claude-history/devices")
        with urllib.request.urlopen(req, timeout=10) as resp:
            devices = json.loads(resp.read().decode("utf-8"))
        dev = devices.get(hostname, {})
        return dev.get("sessions", 0)
    except Exception:
        return 0

def main():
    base_url = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_PI_URL
    base_url = base_url.rstrip("/")

    log("Step 1/3: extracting local history...")
    data = extract_all()
    if not data:
        sys.exit(1)
    local_sessions = data['meta']['totalSessions']
    log(f"extracted {local_sessions} sessions, {data['meta']['totalMessages']} messages")

    # 增量检查
    hostname = data['meta']['machineInfo']['hostname']
    remote_sessions = get_remote_sessions(base_url, hostname)
    log(f"remote has {remote_sessions} sessions for {hostname}")
    if local_sessions <= remote_sessions:
        log("no new sessions, skip upload")
        sys.exit(0)
    log(f"new sessions detected: {remote_sessions} -> {local_sessions}")

    log("Step 2/3: uploading to NebulaShare...")
    result = upload(data, f"{base_url}/api/claude-history/sync")
    if not result.get("ok"):
        log(f"upload FAILED: {result.get('error')}")
        sys.exit(1)
    log(f"upload OK: {result.get('message')}")

    log("Step 3/3: rebuilding knowledge graph...")
    req = urllib.request.Request(f"{base_url}/api/claude-history/process", method="POST")
    try:
        with urllib.request.urlopen(req, timeout=600) as resp:
            pr = json.loads(resp.read().decode("utf-8"))
        for step in pr.get("steps", []):
            icon = "✅" if step["status"]=="done" else "⚠️"
            log(f"{icon} {step['name']}: {step['message']} ({step['durationMs']}ms)")
        fs = pr.get("finalState", {})
        log(f"done! total sessions: {fs.get('totalSessions')}, graph: {fs.get('hasGraph')}")
    except Exception as e:
        log(f"rebuild failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
