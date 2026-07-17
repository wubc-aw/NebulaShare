#!/usr/bin/env python3
"""
NebulaShare Skill Sync client.
Install / update / uninstall skills from the central NebulaShare skill center.
"""

import argparse
import json
import os
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path

try:
    import requests
except ImportError:
    requests = None


def log(msg: str) -> None:
    print(f"  {msg}")


def default_server() -> str:
    return os.environ.get("NEBULA_SERVER", "http://100.101.154.44:8080")


def skills_dir(target: str, name: str) -> Path:
    """Resolve local destination based on skill category prefix."""
    base = Path.home() / ".codex" if target == "codex" else Path.home() / ".claude"
    if name.startswith("commands/"):
        return base / "commands"
    return base / "skills"


def http_get(url: str) -> bytes:
    if requests:
        resp = requests.get(url, timeout=120)
        resp.raise_for_status()
        return resp.content
    import subprocess
    result = subprocess.run(["curl", "-s", "-L", url], capture_output=True)
    if result.returncode != 0:
        raise RuntimeError(f"curl failed: {result.stderr.decode()}")
    return result.stdout


def http_get_json(url: str):
    data = http_get(url)
    return json.loads(data.decode("utf-8"))


def cmd_list(args: argparse.Namespace) -> int:
    url = f"{args.server.rstrip('/')}/api/skills"
    data = http_get_json(url)
    if not data.get("ok"):
        log(f"server error: {data.get('error')}")
        return 1
    skills = data.get("skills", [])
    if not skills:
        log("中心仓库暂无 skill / command")
        return 0
    print(f"{'NAME':<35} {'CATEGORY':<12} {'DESCRIPTION':<45}")
    print("-" * 95)
    for s in skills:
        desc = s.get("description", "")[:43]
        cat = s.get("category", "skill")
        print(f"{s['name']:<35} {cat:<12} {desc:<45}")
    return 0


def cmd_install(args: argparse.Namespace) -> int:
    names = [n.strip() for n in args.names.split(",") if n.strip()]
    if not names:
        log("请指定 --names")
        return 1
    url = f"{args.server.rstrip('/')}/api/skills/bundle?names={','.join(names)}&target={args.target}"
    log(f"Downloading bundle from {url}")
    bundle = http_get(url)
    with tempfile.TemporaryDirectory() as tmp:
        zip_path = Path(tmp) / "skills.zip"
        zip_path.write_bytes(bundle)
        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(tmp)
        # Move each selected item into the correct local dir.
        for name in names:
            src = Path(tmp) / name
            if not src.exists():
                log(f"warning: {name} not found in bundle")
                continue
            dest = skills_dir(args.target, name)
            dest.mkdir(parents=True, exist_ok=True)
            dst_name = name.split("/", 1)[1] if "/" in name else name
            dst = dest / dst_name
            if dst.exists():
                if dst.is_dir():
                    shutil.rmtree(dst)
                else:
                    dst.unlink()
                action = "updated"
            else:
                action = "installed"
            if src.is_dir():
                shutil.copytree(src, dst)
            else:
                shutil.copy2(src, dst)
            log(f"{action}: {dst}")
    return 0


def cmd_uninstall(args: argparse.Namespace) -> int:
    names = [n.strip() for n in args.names.split(",") if n.strip()]
    if not names:
        log("请指定 --names")
        return 1
    for name in names:
        dest = skills_dir(args.target, name)
        dst_name = name.split("/", 1)[1] if "/" in name else name
        target = dest / dst_name
        if target.exists():
            if target.is_dir():
                shutil.rmtree(target)
            else:
                target.unlink()
            log(f"uninstalled: {target}")
        else:
            log(f"not installed: {target}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Sync skills from NebulaShare")
    parser.add_argument("--server", default=default_server(), help="NebulaShare server URL")
    parser.add_argument("--target", choices=["claude", "codex"], default="claude", help="Target tool")
    sub = parser.add_subparsers(dest="command", required=True)

    p_list = sub.add_parser("list", help="List available skills")
    p_list.set_defaults(func=cmd_list)

    p_install = sub.add_parser("install", aliases=["sync"], help="Install/update skills")
    p_install.add_argument("--names", required=True, help="Comma-separated skill names")
    p_install.set_defaults(func=cmd_install)

    p_uninstall = sub.add_parser("uninstall", help="Uninstall skills")
    p_uninstall.add_argument("--names", required=True, help="Comma-separated skill names")
    p_uninstall.set_defaults(func=cmd_uninstall)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
