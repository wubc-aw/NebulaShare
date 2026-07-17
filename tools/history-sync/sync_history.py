#!/usr/bin/env python3
"""
Universal AI history sync tool.
Exports Claude Code and/or Codex history from the local machine,
packages it, and uploads to a NebulaShare server.

Works on macOS, Linux, and ARM devices like Raspberry Pi.
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path

# Import the Codex exporter from the same directory
_HERE = Path(__file__).parent.resolve()


def log(msg: str) -> None:
    print(f"  {msg}")


def _hostname() -> str:
    return os.uname().nodename


def _platform() -> str:
    return f"{os.uname().sysname}-{os.uname().machine}"


def export_claude_code(output_dir: Path) -> Path | None:
    """Copy Claude Code history.jsonl if present."""
    source = Path.home() / ".claude" / "history.jsonl"
    if not source.exists():
        return None
    output_dir.mkdir(parents=True, exist_ok=True)
    dest = output_dir / "claude-history.jsonl"
    shutil.copy2(source, dest)
    log(f"Claude Code history: {source} -> {dest}")
    return dest


def export_codex(output_dir: Path, hostname: str, platform: str) -> Path | None:
    """Export Codex history if present."""
    codex_dir = Path.home() / ".codex"
    if not codex_dir.exists():
        return None

    # Ensure exporter module is available
    exporter_path = _HERE / "export_codex.py"
    if not exporter_path.exists():
        log("export_codex.py not found, skipping Codex export")
        return None

    codex_out = output_dir / "codex"
    cmd = [
        sys.executable,
        str(exporter_path),
        "--codex-dir",
        str(codex_dir),
        "--output-dir",
        str(codex_out),
        "--hostname",
        hostname,
        "--platform",
        platform,
    ]
    log("Running Codex exporter...")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        log(f"Codex exporter failed: {result.stderr}")
        return None
    print(result.stdout)
    return codex_out / "history.json"


def package_and_upload(
    work_dir: Path,
    server_url: str,
    hostname: str,
) -> bool:
    """Package exported files and upload to NebulaShare."""
    zip_path = work_dir / f"history-sync-{hostname}.zip"
    manifest = {
        "hostname": hostname,
        "platform": _platform(),
        "generatedAt": datetime.now(tz=timezone.utc).isoformat(),
        "contents": [],
    }

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, _dirs, files in os.walk(work_dir):
            for fname in files:
                if fname == zip_path.name:
                    continue
                fpath = Path(root) / fname
                arcname = str(fpath.relative_to(work_dir))
                # Flatten codex/images/... to images/... for server compatibility
                if arcname.startswith("codex/images/"):
                    arcname = arcname[len("codex/"):]
                elif arcname.startswith("codex/"):
                    arcname = arcname[len("codex/"):]
                zf.write(fpath, arcname)
                manifest["contents"].append(arcname)

    manifest_path = work_dir / "manifest.json"
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    with zipfile.ZipFile(zip_path, "a") as zf:
        zf.write(manifest_path, "manifest.json")

    log(f"Package: {zip_path} ({zip_path.stat().st_size / 1024 / 1024:.1f} MB)")

    upload_url = f"{server_url.rstrip('/')}/api/claude-history/upload"
    log(f"Uploading to {upload_url} ...")

    try:
        import requests

        with open(zip_path, "rb") as f:
            files = {"file": (zip_path.name, f, "application/zip")}
            data = {"hostname": hostname}
            resp = requests.post(upload_url, files=files, data=data, timeout=300)
        resp.raise_for_status()
        result = resp.json()
        if result.get("ok"):
            log(f"Upload OK: {result.get('message', 'done')}")
            return True
        else:
            log(f"Upload failed: {result.get('error', 'unknown')}")
            return False
    except ImportError:
        log("requests not installed, falling back to curl")
        cmd = [
            "curl",
            "-s",
            "-X",
            "POST",
            "-F",
            f"file=@{zip_path}",
            "-F",
            f"hostname={hostname}",
            upload_url,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            log(f"curl upload failed: {result.stderr}")
            return False
        try:
            resp = json.loads(result.stdout)
            if resp.get("ok"):
                log(f"Upload OK: {resp.get('message', 'done')}")
                return True
            else:
                log(f"Upload failed: {resp.get('error', 'unknown')}")
                return False
        except json.JSONDecodeError:
            log(f"Unexpected response: {result.stdout}")
            return False
    except Exception as e:
        log(f"Upload error: {e}")
        return False


def main() -> None:
    parser = argparse.ArgumentParser(description="Sync AI history to NebulaShare")
    parser.add_argument(
        "--server",
        default=os.environ.get("NEBULA_SERVER", "http://100.101.154.44:8080"),
        help="NebulaShare server URL",
    )
    parser.add_argument(
        "--hostname",
        default=os.environ.get("NEBULA_HOSTNAME", _hostname()),
        help="Device hostname identifier",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(tempfile.gettempdir()) / "ai-history-sync",
        help="Temporary output directory",
    )
    parser.add_argument(
        "--keep",
        action="store_true",
        help="Keep temporary output directory after upload",
    )
    args = parser.parse_args()

    work_dir = args.output / args.hostname
    if work_dir.exists():
        shutil.rmtree(work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)

    log(f"Syncing history from {args.hostname} to {args.server}")

    claude_file = export_claude_code(work_dir / "claude")
    codex_file = export_codex(work_dir, args.hostname, _platform())

    if not claude_file and not codex_file:
        log("No history found to sync")
        return

    ok = package_and_upload(work_dir, args.server, args.hostname)

    if not args.keep:
        shutil.rmtree(work_dir, ignore_errors=True)

    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
