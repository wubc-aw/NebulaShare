#!/usr/bin/env python3
"""LAN File Share Server - Lightweight file sharing + speedtest for local network."""

import os
import sys
import time
import json
import shutil
import socket
import base64
import threading
import subprocess
import tempfile
import urllib.request
import urllib.parse
import urllib.error
from io import BytesIO
from datetime import datetime, timedelta

from flask import Flask, request, send_file, send_from_directory, jsonify, Response, stream_with_context
from werkzeug.utils import safe_join
import qrcode
import yaml
import requests

# ── Config ──────────────────────────────────────────────────────────
UPLOAD_DIR = os.environ.get("NEBULA_DIR", "/home/aw/vibeProjects/NebulaShare/uploads")
PORT = int(os.environ.get("NEBULA_PORT", "8080"))
MAX_TOTAL_GB = 10
MAX_TOTAL_BYTES = MAX_TOTAL_GB * 1024 * 1024 * 1024
MAX_FILE_AGE_DAYS = 7
CLEAN_INTERVAL_SEC = 600  # 10 minutes
ALLOWED_CHARS = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789.-_ ")

# Locate speedtest-cli inside venv
SPEEDTEST_CLI = os.path.join(os.path.dirname(sys.executable), "speedtest-cli")
if not os.path.isfile(SPEEDTEST_CLI):
    SPEEDTEST_CLI = "speedtest-cli"

# ── mihomo (Periscope gateway) integration ──────────────────────────
MIHOMO_API = os.environ.get("MIHOMO_API", "http://127.0.0.1:9090")
MIHOMO_SECRET = os.environ.get("MIHOMO_SECRET", "")
MIHOMO_CONFIG = os.environ.get("MIHOMO_CONFIG", "/etc/mihomo/config.yaml")
MIHOMO_SERVICE = os.environ.get("MIHOMO_SERVICE", "mihomo.service")
MIHOMO_TEST_URL = os.environ.get("MIHOMO_TEST_URL", "http://www.gstatic.com/generate_204")
MIHOMO_TIMEOUT_MS = 3000

NEBULA_STATE_DIR = os.environ.get("NEBULA_STATE_DIR",
                                  os.path.expanduser("~/.config/nebulashare"))
MIHOMO_STATE_FILE = os.path.join(NEBULA_STATE_DIR, "mihomo.json")
os.makedirs(NEBULA_STATE_DIR, exist_ok=True)

app = Flask(__name__, static_folder=None)
os.makedirs(UPLOAD_DIR, exist_ok=True)

# ── Utils ───────────────────────────────────────────────────────────

VIRTUAL_IFACE_PREFIXES = ("tun", "utun", "docker", "virbr", "veth", "wg", "warp")

def get_local_ips():
    """Return real LAN IPv4 addresses, excluding virtual/TUN interfaces."""
    ips = []
    try:
        import netifaces
        for iface in netifaces.interfaces():
            if any(iface.startswith(p) for p in VIRTUAL_IFACE_PREFIXES):
                continue
            addrs = netifaces.ifaddresses(iface).get(netifaces.AF_INET, [])
            for a in addrs:
                ip = a.get("addr")
                if ip and not ip.startswith("127."):
                    ips.append(ip)
    except Exception:
        pass

    if not ips:
        # fallback: try connecting to LAN gateway instead of 8.8.8.8
        # to avoid routing through TUN
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.settimeout(0.5)
            # connect to a common LAN broadcast address
            s.connect(("192.168.50.255", 80))
            ip = s.getsockname()[0]
            s.close()
            if not ip.startswith("127.") and not ip.startswith("198.18."):
                ips.append(ip)
        except Exception:
            pass

    if not ips:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.settimeout(0.5)
            s.connect(("10.0.0.1", 80))
            ip = s.getsockname()[0]
            s.close()
            if not ip.startswith("127.") and not ip.startswith("198.18."):
                ips.append(ip)
        except Exception:
            pass

    return ips if ips else ["0.0.0.0"]


def safe_filename(name):
    """Sanitize filename."""
    base = os.path.basename(name)
    clean = "".join(c for c in base if c in ALLOWED_CHARS).strip(".")
    if not clean:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        clean = f"upload_{ts}"
    dest = os.path.join(UPLOAD_DIR, clean)
    if os.path.exists(dest):
        stem, ext = os.path.splitext(clean)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        clean = f"{stem}_{ts}{ext}"
    return clean


def fmt_size(n):
    for unit in ["B", "KB", "MB", "GB"]:
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


def total_upload_size():
    total = 0
    for fn in os.listdir(UPLOAD_DIR):
        p = os.path.join(UPLOAD_DIR, fn)
        if os.path.isfile(p):
            total += os.path.getsize(p)
    return total


def qr_data_url(url):
    """Generate QR code as base64 data URL."""
    try:
        qr = qrcode.make(url, box_size=4, border=1)
        buf = BytesIO()
        qr.save(buf, format="PNG")
        b64 = base64.b64encode(buf.getvalue()).decode()
        return f"data:image/png;base64,{b64}"
    except Exception:
        return ""


# ── Self-check ──────────────────────────────────────────────────────

def self_check():
    """Run startup health checks."""
    checks = []
    ok = True

    if not os.path.isdir(UPLOAD_DIR):
        try:
            os.makedirs(UPLOAD_DIR, exist_ok=True)
            checks.append(("DIR", "OK", f"created {UPLOAD_DIR}"))
        except Exception as e:
            checks.append(("DIR", "FAIL", str(e)))
            ok = False
    else:
        if os.access(UPLOAD_DIR, os.W_OK | os.R_OK):
            checks.append(("DIR", "OK", UPLOAD_DIR))
        else:
            checks.append(("DIR", "FAIL", "not writable"))
            ok = False

    try:
        st = shutil.disk_usage(UPLOAD_DIR)
        free_gb = st.free / (1024 ** 3)
        if free_gb < 1:
            checks.append(("DISK", "WARN", f"only {free_gb:.1f} GB free"))
        else:
            checks.append(("DISK", "OK", f"{free_gb:.1f} GB free"))
    except Exception as e:
        checks.append(("DISK", "WARN", str(e)))

    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(1)
        r = s.connect_ex(("0.0.0.0", PORT))
        s.close()
        if r == 0:
            checks.append(("PORT", "FAIL", f"port {PORT} in use"))
            ok = False
        else:
            checks.append(("PORT", "OK", f"port {PORT} available"))
    except Exception as e:
        checks.append(("PORT", "WARN", str(e)))

    return ok, checks


# ── Cleaner ─────────────────────────────────────────────────────────

def cleaner_loop():
    while True:
        time.sleep(CLEAN_INTERVAL_SEC)
        try:
            now = time.time()
            deleted_age = 0
            deleted_space = 0

            files = []
            for fn in os.listdir(UPLOAD_DIR):
                p = os.path.join(UPLOAD_DIR, fn)
                if not os.path.isfile(p):
                    continue
                mtime = os.path.getmtime(p)
                size = os.path.getsize(p)
                age_days = (now - mtime) / 86400

                if age_days > MAX_FILE_AGE_DAYS:
                    try:
                        os.remove(p)
                        deleted_age += 1
                    except Exception:
                        pass
                    continue

                files.append((mtime, size, p))

            files.sort(key=lambda x: x[0])
            total = sum(f[1] for f in files)
            while total > MAX_TOTAL_BYTES and files:
                mtime, size, p = files.pop(0)
                try:
                    os.remove(p)
                    total -= size
                    deleted_space += 1
                except Exception:
                    pass

            if deleted_age or deleted_space:
                ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                print(f"[{ts}] Cleaner: age-deleted={deleted_age} space-deleted={deleted_space}")
        except Exception as e:
            print(f"Cleaner error: {e}")


# ── Routes: File Share ──────────────────────────────────────────────

@app.route("/")
def index():
    # Serve new frontend if available, fallback to legacy inline page
    static_index = os.path.join(STATIC_DIR, "index.html")
    if os.path.isfile(static_index):
        return send_from_directory(STATIC_DIR, "index.html")
    ips = get_local_ips()
    urls = [f"http://{ip}:{PORT}" for ip in ips]
    primary_url = urls[0]
    primary_ip = ips[0]
    # Example phone IP: same /24 subnet as Pi, last octet = 99 (likely free of DHCP)
    parts = primary_ip.split(".")
    phone_ip_example = ".".join(parts[:3] + ["99"]) if len(parts) == 4 else primary_ip
    qr = qr_data_url(primary_url)
    return Response(HTML_PAGE.replace("{{URLS}}", ", ".join(urls))
                           .replace("{{PRIMARY_URL}}", primary_url)
                           .replace("{{PI_IP}}", primary_ip)
                           .replace("{{PHONE_IP_EXAMPLE}}", phone_ip_example)
                           .replace("{{QR}}", qr)
                           .replace("{{PC_NAME}}", PC_NAME)
                           .replace("{{PC_IP}}", PC_IP)
                           .replace("{{PC_MAC}}", PC_MAC)
                           .replace("{{PC_SSH_USER}}", PC_SSH_USER),
                    mimetype="text/html")


@app.route("/api/upload", methods=["POST"])
def upload():
    if "file" not in request.files:
        return jsonify({"error": "no file"}), 400
    f = request.files["file"]
    if not f.filename:
        return jsonify({"error": "empty filename"}), 400

    name = safe_filename(f.filename)
    dest = os.path.join(UPLOAD_DIR, name)
    f.save(dest)

    total = total_upload_size()
    if total > MAX_TOTAL_BYTES:
        files = []
        for fn in os.listdir(UPLOAD_DIR):
            p = os.path.join(UPLOAD_DIR, fn)
            if os.path.isfile(p):
                files.append((os.path.getmtime(p), os.path.getsize(p), p))
        files.sort(key=lambda x: x[0])
        while total > MAX_TOTAL_BYTES and files:
            mtime, size, p = files.pop(0)
            if p == dest:
                continue
            try:
                os.remove(p)
                total -= size
            except Exception:
                pass

    return jsonify({"ok": True, "filename": name})


@app.route("/api/files")
def list_files():
    now = time.time()
    items = []
    for fn in os.listdir(UPLOAD_DIR):
        p = os.path.join(UPLOAD_DIR, fn)
        if not os.path.isfile(p):
            continue
        mtime = os.path.getmtime(p)
        size = os.path.getsize(p)
        age_days = (now - mtime) / 86400
        remain_days = max(0, MAX_FILE_AGE_DAYS - age_days)
        items.append({
            "filename": fn,
            "size": size,
            "size_human": fmt_size(size),
            "mtime": int(mtime),
            "mtime_iso": datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M"),
            "remain_hours": int(remain_days * 24),
        })
    items.sort(key=lambda x: x["mtime"], reverse=True)
    total = sum(i["size"] for i in items)
    return jsonify({
        "files": items,
        "total_size": total,
        "total_size_human": fmt_size(total),
        "max_size_human": fmt_size(MAX_TOTAL_BYTES),
    })


@app.route("/api/download/<path:filename>")
def download(filename):
    safe = os.path.basename(filename)
    p = os.path.join(UPLOAD_DIR, safe)
    if not os.path.isfile(p):
        return jsonify({"error": "not found"}), 404
    return send_file(p, as_attachment=True, download_name=safe)


@app.route("/api/files/<path:filename>", methods=["DELETE"])
def delete_file(filename):
    safe = os.path.basename(filename)
    p = os.path.join(UPLOAD_DIR, safe)
    if os.path.isfile(p):
        os.remove(p)
        return jsonify({"ok": True})
    return jsonify({"error": "not found"}), 404


@app.route("/api/files/batch-delete", methods=["POST"])
def batch_delete_files():
    data = request.get_json(silent=True) or {}
    names = data.get("names", [])
    if not names:
        return jsonify({"error": "no files selected"}), 400
    deleted = []
    failed = []
    for name in names:
        safe = os.path.basename(name)
        p = os.path.join(UPLOAD_DIR, safe)
        if os.path.isfile(p):
            try:
                os.remove(p)
                deleted.append(safe)
            except Exception:
                failed.append(safe)
        else:
            failed.append(safe)
    return jsonify({"deleted": deleted, "failed": failed})


# ── Routes: Speedtest ───────────────────────────────────────────────

@app.route("/api/speedtest/lan")
def lan_speed_download():
    """Stream random data for LAN download speed test."""
    size_mb = request.args.get("size", 50, type=int)
    if size_mb < 1:
        size_mb = 1
    if size_mb > 200:
        size_mb = 200

    chunk = 1024 * 1024  # 1MB
    total = size_mb * chunk

    def gen():
        sent = 0
        while sent < total:
            yield os.urandom(min(chunk, total - sent))
            sent += chunk

    return Response(stream_with_context(gen()),
                    mimetype="application/octet-stream",
                    headers={"Content-Length": str(total)})


@app.route("/api/speedtest/lan-upload", methods=["POST"])
def lan_speed_upload():
    """Accept upload data for LAN upload speed test."""
    total = 0
    while True:
        chunk = request.stream.read(65536)
        if not chunk:
            break
        total += len(chunk)
    return jsonify({"ok": True, "bytes_received": total})


@app.route("/api/speedtest/wan")
def wan_speedtest():
    """Run external speedtest via speedtest-cli, bypassing TUN interface."""
    try:
        lan_ips = get_local_ips()
        source_ip = lan_ips[0] if lan_ips else None
        cmd = [SPEEDTEST_CLI, "--simple"]
        if source_ip and source_ip != "0.0.0.0":
            cmd.extend(["--source", source_ip])
        result = subprocess.run(
            cmd,
            capture_output=True, text=True, timeout=90
        )
        if result.returncode != 0:
            return jsonify({"error": result.stderr or "speedtest failed"}), 500

        lines = result.stdout.strip().splitlines()
        data = {}
        for line in lines:
            if line.startswith("Ping:"):
                data["ping"] = float(line.split(":")[1].strip().split()[0])
            elif line.startswith("Download:"):
                data["download"] = float(line.split(":")[1].strip().split()[0])
            elif line.startswith("Upload:"):
                data["upload"] = float(line.split(":")[1].strip().split()[0])

        return jsonify({"ok": True, **data})
    except subprocess.TimeoutExpired:
        return jsonify({"error": "speedtest timeout"}), 504
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── Routes: Mihomo Gateway ──────────────────────────────────────────

def _mihomo_req(method, path, body=None, timeout=4, stream=False):
    """Make HTTP call to mihomo external-controller API."""
    url = f"{MIHOMO_API}{path}"
    headers = {"Accept": "application/json"}
    if MIHOMO_SECRET:
        headers["Authorization"] = f"Bearer {MIHOMO_SECRET}"
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        resp = urllib.request.urlopen(req, timeout=timeout)
        if stream:
            return resp
        raw = resp.read()
        if not raw:
            return {}
        try:
            return json.loads(raw)
        except Exception:
            return {"_raw": raw.decode("utf-8", errors="replace")}
    except urllib.error.HTTPError as e:
        try:
            err_body = e.read().decode("utf-8", errors="replace")
        except Exception:
            err_body = str(e)
        return {"_error": f"HTTP {e.code}", "_detail": err_body}
    except Exception as e:
        return {"_error": str(e)}


def mihomo_get(path, timeout=4):
    return _mihomo_req("GET", path, timeout=timeout)


def mihomo_put(path, body=None, timeout=8):
    return _mihomo_req("PUT", path, body=body or {}, timeout=timeout)


def mihomo_post(path, body=None, timeout=8):
    return _mihomo_req("POST", path, body=body or {}, timeout=timeout)


def mihomo_traffic_snapshot():
    """Read /traffic stream. First emit is zero (warm-up), use second."""
    return _mihomo_streamed_skip_first("/traffic")


def mihomo_memory_snapshot():
    """Read /memory stream. First emit is zero (warm-up), use second."""
    return _mihomo_streamed_skip_first("/memory")


def _mihomo_streamed_skip_first(path, timeout=3):
    """mihomo's /traffic and /memory emit a warm-up sample of zeros, then real data
    every ~1s. Read both, return the second."""
    try:
        url = f"{MIHOMO_API}{path}"
        headers = {}
        if MIHOMO_SECRET:
            headers["Authorization"] = f"Bearer {MIHOMO_SECRET}"
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            resp.readline()           # drop warm-up
            line = resp.readline()
        if not line:
            return None
        return json.loads(line)
    except Exception:
        return None


def systemd_active(unit):
    try:
        r = subprocess.run(["systemctl", "is-active", unit],
                           capture_output=True, text=True, timeout=3)
        return r.stdout.strip() == "active"
    except Exception:
        return False


def systemd_uptime_seconds(unit):
    """Return how long the unit has been active, or None."""
    try:
        r = subprocess.run(["systemctl", "show", unit,
                            "-p", "ActiveEnterTimestampMonotonic"],
                           capture_output=True, text=True, timeout=3)
        # ActiveEnterTimestampMonotonic=1234567 (microseconds since boot)
        line = r.stdout.strip()
        if "=" not in line:
            return None
        val = int(line.split("=", 1)[1])
        if val == 0:
            return None
        # Compare against current monotonic
        with open("/proc/uptime") as f:
            now_mono = float(f.read().split()[0])
        return max(0, int(now_mono - val / 1_000_000))
    except Exception:
        return None


def file_age_days(path):
    try:
        mt = os.path.getmtime(path)
        return round((time.time() - mt) / 86400, 1)
    except Exception:
        return None


def load_mihomo_state():
    if os.path.isfile(MIHOMO_STATE_FILE):
        try:
            with open(MIHOMO_STATE_FILE) as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def save_mihomo_state(d):
    tmp = MIHOMO_STATE_FILE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(d, f, indent=2, ensure_ascii=False)
    os.replace(tmp, MIHOMO_STATE_FILE)


def mask_url(u):
    """Hide token-like query params for display."""
    if not u:
        return ""
    try:
        p = urllib.parse.urlparse(u)
        scheme = p.scheme or "https"
        netloc = p.netloc
        path = p.path or ""
        if len(path) > 20:
            path = path[:8] + "…" + path[-6:]
        return f"{scheme}://{netloc}{path}"
    except Exception:
        return u[:40] + "…"


@app.route("/api/mihomo/status")
def mihomo_status():
    """Aggregate snapshot for the dashboard."""
    active = systemd_active(MIHOMO_SERVICE)
    if not active:
        return jsonify({"ok": True, "active": False})

    # Run streaming snapshots (each ~2s) in parallel to keep latency low.
    out = {}
    def fetch(name, fn):
        try:
            out[name] = fn()
        except Exception:
            out[name] = None
    workers = [
        threading.Thread(target=fetch, args=("traffic", mihomo_traffic_snapshot)),
        threading.Thread(target=fetch, args=("memory", mihomo_memory_snapshot)),
    ]
    for w in workers: w.start()

    cfg = mihomo_get("/configs", timeout=2)
    ver = mihomo_get("/version", timeout=2)
    conns = mihomo_get("/connections", timeout=3)

    for w in workers: w.join(timeout=4)

    traffic = out.get("traffic") or {}
    mem = out.get("memory") or {}

    n_conn = len(conns.get("connections") or []) if isinstance(conns, dict) else 0
    up_total = conns.get("uploadTotal", 0) if isinstance(conns, dict) else 0
    dn_total = conns.get("downloadTotal", 0) if isinstance(conns, dict) else 0

    state = load_mihomo_state()
    sub_url = state.get("subscription_url", "")
    last_update = state.get("last_update", 0)

    return jsonify({
        "ok": True,
        "active": active,
        "uptime_sec": systemd_uptime_seconds(MIHOMO_SERVICE),
        "version": ver.get("version") if isinstance(ver, dict) else None,
        "meta": ver.get("meta") if isinstance(ver, dict) else None,
        "mode": cfg.get("mode") if isinstance(cfg, dict) else None,
        "tun": (cfg.get("tun") or {}) if isinstance(cfg, dict) else {},
        "memory": mem.get("inuse") if isinstance(mem, dict) else None,
        "traffic": {"up": traffic.get("up", 0), "down": traffic.get("down", 0)},
        "geoip_age_days": file_age_days("/etc/mihomo/GeoIP.dat"),
        "geosite_age_days": file_age_days("/etc/mihomo/GeoSite.dat"),
        "connections": n_conn,
        "upload_total": up_total,
        "download_total": dn_total,
        "subscription": {
            "url_full": sub_url,
            "url": mask_url(sub_url),
            "last_update": last_update,
            "last_update_iso": (datetime.fromtimestamp(last_update).strftime("%Y-%m-%d %H:%M:%S")
                                if last_update else ""),
        },
    })


# ── Per-client byte tracker (1Hz background poller) ─────────────────
_clients_lock = threading.Lock()
_clients_state = {}        # ip -> {"up_total","dn_total","up_rate","dn_rate","since"}
_conn_seen = {}            # conn_id -> (last_up, last_dn, ip)
_clients_last_snap = None  # most recent /connections snapshot (for rule/chain/host meta)
_clients_last_poll = 0.0
_clients_poller_started = False


def _clients_poll_once():
    """One poll cycle: diff each connection by ID, accumulate per-IP totals + rates."""
    global _conn_seen, _clients_last_snap, _clients_last_poll
    snap = mihomo_get("/connections", timeout=3)
    if not isinstance(snap, dict) or "_error" in snap:
        return
    now = time.time()
    now_seen = {}
    delta_per_ip = {}
    for c in snap.get("connections") or []:
        cid = c.get("id")
        if not cid:
            continue
        meta = c.get("metadata") or {}
        ip = meta.get("sourceIP") or "?"
        up = int(c.get("upload") or 0)
        dn = int(c.get("download") or 0)
        prev = _conn_seen.get(cid)
        if prev:
            d_up = up - prev[0]
            d_dn = dn - prev[1]
            if d_up < 0: d_up = 0
            if d_dn < 0: d_dn = 0
        else:
            d_up, d_dn = up, dn  # first-seen conn → count its bytes-since-open
        now_seen[cid] = (up, dn, ip)
        if d_up or d_dn:
            slot = delta_per_ip.setdefault(ip, [0, 0])
            slot[0] += d_up
            slot[1] += d_dn

    interval = max(0.001, now - _clients_last_poll) if _clients_last_poll else 1.0
    with _clients_lock:
        for ip, (d_up, d_dn) in delta_per_ip.items():
            st = _clients_state.setdefault(ip, {
                "up_total": 0, "dn_total": 0,
                "up_rate": 0, "dn_rate": 0,
                "since": now,
            })
            st["up_total"] += d_up
            st["dn_total"] += d_dn
            # EMA smoothing so the displayed rate doesn't flicker between 0
            # and a spike when traffic is bursty (Netflix chunks, video
            # progressive download, etc.). alpha=0.4 → ~3s effective window.
            inst_up = d_up / interval
            inst_dn = d_dn / interval
            st["up_rate"] = int(0.4 * inst_up + 0.6 * st["up_rate"])
            st["dn_rate"] = int(0.4 * inst_dn + 0.6 * st["dn_rate"])
        for ip, st in _clients_state.items():
            if ip not in delta_per_ip:
                st["up_rate"] = int(0.6 * st["up_rate"])
                st["dn_rate"] = int(0.6 * st["dn_rate"])
        _conn_seen = now_seen
        _clients_last_snap = snap
        _clients_last_poll = now


def _clients_poller_loop():
    while True:
        try:
            _clients_poll_once()
        except Exception:
            pass
        time.sleep(1.0)


def _ensure_clients_poller():
    global _clients_poller_started
    if not _clients_poller_started:
        _clients_poller_started = True
        # Seed once synchronously so the first /clients response has fresh metadata
        try:
            _clients_poll_once()
        except Exception:
            pass
        threading.Thread(target=_clients_poller_loop, daemon=True).start()


@app.route("/api/mihomo/clients")
def mihomo_clients():
    """Return per-client throughput + cumulative bytes since first seen.

    mihomo's /connections only lists currently-active connections, so a naive
    aggregation drops bytes the instant a connection closes. Netflix uses many
    short-lived HTTP/2 byte-range fetches, which makes the naive number
    visibly wrong (way too low). To fix this we run a 1Hz background poller
    that diffs each connection by its ID; bytes from connections that close
    between frontend polls are still captured.
    """
    _ensure_clients_poller()
    with _clients_lock:
        state = {ip: dict(s) for ip, s in _clients_state.items()}
        snap = _clients_last_snap or {}

    meta_by_ip = {}
    for c in snap.get("connections") or []:
        meta = c.get("metadata") or {}
        ip = meta.get("sourceIP") or "?"
        e = meta_by_ip.setdefault(ip, {
            "count": 0, "rules": {}, "chains": {}, "host_recent": "",
        })
        e["count"] += 1
        rk = c.get("rule") or "?"
        e["rules"][rk] = e["rules"].get(rk, 0) + 1
        ch = " → ".join(reversed(c.get("chains") or [])) or "DIRECT"
        e["chains"][ch] = e["chains"].get(ch, 0) + 1
        host = meta.get("host") or meta.get("destinationIP") or ""
        if host and not e["host_recent"]:
            e["host_recent"] = host

    out = []
    now = time.time()
    for ip in set(state.keys()) | set(meta_by_ip.keys()):
        st = state.get(ip) or {"up_total": 0, "dn_total": 0, "up_rate": 0, "dn_rate": 0, "since": now}
        m = meta_by_ip.get(ip) or {"count": 0, "rules": {}, "chains": {}, "host_recent": ""}
        if m["count"] == 0 and st["up_total"] == 0 and st["dn_total"] == 0:
            continue
        top_rule = max(m["rules"].items(), key=lambda x: x[1])[0] if m["rules"] else "?"
        top_chain = max(m["chains"].items(), key=lambda x: x[1])[0] if m["chains"] else "?"
        out.append({
            "ip": ip,
            "connections": m["count"],
            "upload_bytes": st["up_total"],
            "download_bytes": st["dn_total"],
            "upload_rate": st["up_rate"],
            "download_rate": st["dn_rate"],
            "rule": top_rule,
            "chain": top_chain,
            "host_recent": m["host_recent"],
            "since_sec": int(now - st.get("since", now)),
        })
    out.sort(key=lambda x: -(x["download_rate"] + x["upload_rate"] + x["download_bytes"] // 1024))
    return jsonify({"ok": True, "clients": out})


# ── Client name aliases (persisted in mihomo state file) ────────────

@app.route("/api/clients/names")
def clients_names_get():
    state = load_mihomo_state()
    return jsonify({"ok": True, "names": state.get("client_names", {})})


@app.route("/api/clients/names", methods=["POST"])
def clients_names_post():
    body = request.get_json(silent=True) or {}
    ip = body.get("ip", "").strip()
    name = body.get("name", "").strip()
    if not ip:
        return jsonify({"ok": False, "error": "ip required"}), 400
    state = load_mihomo_state()
    client_names = state.setdefault("client_names", {})
    if name:
        client_names[ip] = name
    else:
        client_names.pop(ip, None)
    save_mihomo_state(state)
    return jsonify({"ok": True, "names": client_names})


@app.route("/api/mihomo/groups")
def mihomo_groups():
    """List selectable proxy groups + nodes."""
    data = mihomo_get("/proxies", timeout=4)
    if not isinstance(data, dict) or "_error" in data:
        return jsonify({"ok": False, "error": data.get("_error", "no data")}), 502
    proxies = data.get("proxies", {})
    groups = []
    for name, v in proxies.items():
        t = v.get("type")
        if t not in ("Selector", "URLTest", "Fallback", "LoadBalance"):
            continue
        members = []
        for m_name in v.get("all") or []:
            m = proxies.get(m_name) or {}
            hist = m.get("history") or []
            delay = hist[-1].get("delay") if hist else 0
            members.append({
                "name": m_name,
                "type": m.get("type"),
                "delay": delay or 0,  # 0 means unreachable / not tested
            })
        groups.append({
            "name": name,
            "type": t,
            "now": v.get("now"),
            "udp": v.get("udp", False),
            "members": members,
        })
    # Stable order: GLOBAL last, then alphabetical
    groups.sort(key=lambda g: (g["name"] == "GLOBAL", g["name"]))
    return jsonify({"ok": True, "groups": groups})


@app.route("/api/mihomo/select", methods=["POST"])
def mihomo_select():
    """Switch a selector group's current node."""
    body = request.get_json(silent=True) or {}
    group = body.get("group")
    name = body.get("name")
    if not group or not name:
        return jsonify({"ok": False, "error": "group and name required"}), 400
    r = mihomo_put(f"/proxies/{urllib.parse.quote(group, safe='')}", {"name": name})
    if isinstance(r, dict) and "_error" in r:
        return jsonify({"ok": False, "error": r.get("_detail") or r["_error"]}), 502
    return jsonify({"ok": True})


@app.route("/api/mihomo/test/group/<path:group>")
def mihomo_test_group(group):
    """Trigger latency test for all nodes in a group."""
    timeout = request.args.get("timeout", MIHOMO_TIMEOUT_MS, type=int)
    test_url = request.args.get("url", MIHOMO_TEST_URL)
    qs = urllib.parse.urlencode({"url": test_url, "timeout": timeout})
    # /group/{name}/delay returns {nodeName: delayMs} for all nodes; failures -> not in dict or 0
    res = mihomo_get(f"/group/{urllib.parse.quote(group, safe='')}/delay?{qs}",
                     timeout=timeout / 1000 + 5)
    if isinstance(res, dict) and "_error" in res:
        return jsonify({"ok": False, "error": res.get("_detail") or res["_error"]}), 502
    return jsonify({"ok": True, "delays": res})


@app.route("/api/mihomo/test/proxy/<path:name>")
def mihomo_test_proxy(name):
    """Latency test a single proxy node."""
    timeout = request.args.get("timeout", MIHOMO_TIMEOUT_MS, type=int)
    test_url = request.args.get("url", MIHOMO_TEST_URL)
    qs = urllib.parse.urlencode({"url": test_url, "timeout": timeout})
    res = mihomo_get(f"/proxies/{urllib.parse.quote(name, safe='')}/delay?{qs}",
                     timeout=timeout / 1000 + 3)
    if isinstance(res, dict) and "_error" in res:
        return jsonify({"ok": False, "error": res.get("_detail") or res["_error"]}), 502
    delay = res.get("delay") if isinstance(res, dict) else 0
    return jsonify({"ok": True, "delay": delay or 0})


@app.route("/api/mihomo/mode", methods=["POST"])
def mihomo_set_mode():
    body = request.get_json(silent=True) or {}
    mode = (body.get("mode") or "").lower()
    if mode not in ("rule", "global", "direct"):
        return jsonify({"ok": False, "error": "mode must be rule/global/direct"}), 400
    r = mihomo_put("/configs", {"mode": mode})
    if isinstance(r, dict) and "_error" in r:
        return jsonify({"ok": False, "error": r.get("_detail") or r["_error"]}), 502
    return jsonify({"ok": True, "mode": mode})


@app.route("/api/mihomo/connections/recent")
def mihomo_connections_recent():
    limit = request.args.get("limit", 12, type=int)
    data = mihomo_get("/connections", timeout=3)
    if not isinstance(data, dict) or "_error" in data:
        return jsonify({"ok": False, "error": data.get("_error", "no data")}), 502
    conns = list(data.get("connections") or [])
    conns.sort(key=lambda c: c.get("start", ""), reverse=True)
    out = []
    for c in conns[:limit]:
        m = c.get("metadata") or {}
        out.append({
            "src": m.get("sourceIP", ""),
            "host": m.get("host") or m.get("destinationIP", ""),
            "port": m.get("destinationPort", ""),
            "rule": c.get("rule"),
            "rule_payload": c.get("rulePayload"),
            "chain": " → ".join(reversed(c.get("chains") or [])) or "DIRECT",
            "upload": c.get("upload", 0),
            "download": c.get("download", 0),
            "start": c.get("start"),
        })
    return jsonify({"ok": True, "items": out})


# ── Subscription URL: store + manual refresh ──

def _fetch_subscription(url, timeout=30):
    """Fetch a Clash subscription URL and return parsed YAML dict."""
    req = urllib.request.Request(url, headers={
        # Some panels gate by UA; clash-style works for most converters.
        "User-Agent": "clash.meta/v1.19 (mihomo)",
        "Accept": "*/*",
    })
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
    except urllib.error.URLError as e:
        # Surface TLS/network details for easier debugging.
        err = str(e.reason) if hasattr(e, "reason") else str(e)
        print(f"[mihomo] subscription fetch failed for {mask_url(url)}: {err}")
        raise RuntimeError(f"无法拉取订阅 ({err})") from e
    text = raw.decode("utf-8", errors="replace")
    # Some converters return base64-wrapped YAML; try decoding.
    if not text.strip().startswith(("proxies:", "---", "#", "port:", "mixed-port:")):
        try:
            import base64
            decoded = base64.b64decode(text.strip()).decode("utf-8", errors="replace")
            if "proxies:" in decoded:
                text = decoded
        except Exception:
            pass
    parsed = yaml.safe_load(text)
    if not isinstance(parsed, dict):
        preview = text[:200].replace("\n", " ")
        raise ValueError(f"subscription did not return a YAML mapping (got: {preview})")
    if "proxies" not in parsed:
        preview = text[:200].replace("\n", " ")
        raise ValueError(f"subscription has no 'proxies' field (preview: {preview})")
    return parsed


def _replace_mihomo_config(new_proxies, new_groups, new_rules):
    """Read /etc/mihomo/config.yaml, replace proxies/proxy-groups/rules, write back via sudo.
    Returns (ok, message)."""
    # Read current config (root-owned but world-readable)
    try:
        with open(MIHOMO_CONFIG, "r") as f:
            current = yaml.safe_load(f)
    except Exception as e:
        return False, f"read config failed: {e}"

    if not isinstance(current, dict):
        return False, "current config is not a YAML mapping"

    if new_proxies is not None:
        current["proxies"] = new_proxies
    if new_groups:
        current["proxy-groups"] = new_groups
    if new_rules:
        current["rules"] = new_rules

    # Render YAML to a temp file
    try:
        with tempfile.NamedTemporaryFile("w", delete=False, suffix=".yaml",
                                         dir="/tmp") as tmp:
            yaml.safe_dump(current, tmp, allow_unicode=True, sort_keys=False,
                           default_flow_style=False)
            tmp_path = tmp.name
    except Exception as e:
        return False, f"render yaml failed: {e}"

    # Backup current config + install new one via sudo
    try:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        bak = f"{MIHOMO_CONFIG}.bak.{ts}"
        r1 = subprocess.run(["sudo", "-n", "cp", "--preserve=mode,ownership", MIHOMO_CONFIG, bak],
                            capture_output=True, text=True, timeout=10)
        if r1.returncode != 0:
            return False, f"backup failed: {r1.stderr.strip()}"
        r2 = subprocess.run(["sudo", "-n", "install", "-m", "0644", tmp_path, MIHOMO_CONFIG],
                            capture_output=True, text=True, timeout=10)
        if r2.returncode != 0:
            return False, f"install failed: {r2.stderr.strip()}"
    finally:
        try:
            os.unlink(tmp_path)
        except Exception:
            pass

    # Restart mihomo
    r3 = subprocess.run(["sudo", "-n", "systemctl", "restart", MIHOMO_SERVICE],
                        capture_output=True, text=True, timeout=20)
    if r3.returncode != 0:
        return False, f"restart failed: {r3.stderr.strip()}"

    return True, "ok"


@app.route("/api/mihomo/sub", methods=["GET"])
def mihomo_sub_get():
    state = load_mihomo_state()
    return jsonify({
        "ok": True,
        "url_full": state.get("subscription_url", ""),
        "url_masked": mask_url(state.get("subscription_url", "")),
        "last_update": state.get("last_update", 0),
        "last_update_iso": (datetime.fromtimestamp(state["last_update"]).strftime("%Y-%m-%d %H:%M:%S")
                            if state.get("last_update") else ""),
        "last_proxy_count": state.get("last_proxy_count", 0),
    })


@app.route("/api/mihomo/sub", methods=["POST"])
def mihomo_sub_save():
    """Save subscription URL only (does NOT trigger refresh)."""
    body = request.get_json(silent=True) or {}
    url = (body.get("url") or "").strip()
    if not url or not url.startswith(("http://", "https://")):
        return jsonify({"ok": False, "error": "invalid url"}), 400
    state = load_mihomo_state()
    state["subscription_url"] = url
    save_mihomo_state(state)
    return jsonify({"ok": True, "url_masked": mask_url(url)})


@app.route("/api/mihomo/sub/refresh", methods=["POST"])
def mihomo_sub_refresh():
    """Fetch subscription, replace proxies in mihomo config, restart mihomo."""
    body = request.get_json(silent=True) or {}
    state = load_mihomo_state()
    url = (body.get("url") or state.get("subscription_url") or "").strip()
    if not url:
        return jsonify({"ok": False, "error": "no subscription url; save one first"}), 400

    # 1. fetch
    try:
        sub = _fetch_subscription(url)
    except Exception as e:
        return jsonify({"ok": False, "error": f"fetch failed: {e}"}), 502

    new_proxies = sub.get("proxies") or []
    new_groups = sub.get("proxy-groups") or []
    new_rules = sub.get("rules") or []
    if not new_proxies:
        return jsonify({"ok": False, "error": "subscription returned no proxies"}), 502

    # 2. write + restart
    ok, msg = _replace_mihomo_config(new_proxies, new_groups, new_rules)
    if not ok:
        return jsonify({"ok": False, "error": msg}), 500

    # 3. wait for mihomo to come back up (max ~10s)
    started = time.time()
    while time.time() - started < 10:
        v = mihomo_get("/version", timeout=1)
        if isinstance(v, dict) and v.get("version"):
            break
        time.sleep(0.5)

    state["subscription_url"] = url
    state["last_update"] = int(time.time())
    state["last_proxy_count"] = len(new_proxies)
    save_mihomo_state(state)
    return jsonify({
        "ok": True,
        "proxy_count": len(new_proxies),
        "group_count": len(new_groups),
        "rule_count": len(new_rules),
    })


@app.route("/api/mihomo/sub/upload-yaml", methods=["POST"])
def mihomo_sub_upload_yaml():
    """Receive raw Clash YAML from frontend, parse it, replace config, restart mihomo.
    This is the escape-hatch when automatic URL fetch fails (e.g. TLS issues)."""
    body = request.get_json(silent=True) or {}
    raw_yaml = (body.get("yaml") or "").strip()
    if not raw_yaml:
        return jsonify({"ok": False, "error": "yaml content is empty"}), 400

    # Parse the pasted YAML
    try:
        parsed = yaml.safe_load(raw_yaml)
    except Exception as e:
        return jsonify({"ok": False, "error": f"YAML parse failed: {e}"}), 400

    if not isinstance(parsed, dict):
        return jsonify({"ok": False, "error": "YAML root is not a mapping"}), 400

    new_proxies = parsed.get("proxies") or []
    new_groups = parsed.get("proxy-groups") or []
    new_rules = parsed.get("rules") or []

    if not new_proxies:
        return jsonify({"ok": False, "error": "pasted config has no 'proxies' field"}), 400

    # Write + restart
    ok, msg = _replace_mihomo_config(new_proxies, new_groups, new_rules)
    if not ok:
        return jsonify({"ok": False, "error": msg}), 500

    # Wait for mihomo to come back up
    started = time.time()
    while time.time() - started < 10:
        v = mihomo_get("/version", timeout=1)
        if isinstance(v, dict) and v.get("version"):
            break
        time.sleep(0.5)

    state = load_mihomo_state()
    state["last_update"] = int(time.time())
    state["last_proxy_count"] = len(new_proxies)
    # Note: we don't touch subscription_url here since user bypassed URL fetch
    save_mihomo_state(state)
    return jsonify({
        "ok": True,
        "proxy_count": len(new_proxies),
        "group_count": len(new_groups),
        "rule_count": len(new_rules),
    })


@app.route("/api/mihomo/restart", methods=["POST"])
def mihomo_restart():
    r = subprocess.run(["sudo", "-n", "systemctl", "restart", MIHOMO_SERVICE],
                       capture_output=True, text=True, timeout=20)
    if r.returncode != 0:
        return jsonify({"ok": False, "error": r.stderr.strip()}), 500
    return jsonify({"ok": True})


@app.route("/api/mihomo/start", methods=["POST"])
def mihomo_start():
    r = subprocess.run(["sudo", "-n", "systemctl", "start", MIHOMO_SERVICE],
                       capture_output=True, text=True, timeout=20)
    if r.returncode != 0:
        return jsonify({"ok": False, "error": r.stderr.strip()}), 500
    return jsonify({"ok": True})


@app.route("/api/mihomo/stop", methods=["POST"])
def mihomo_stop():
    r = subprocess.run(["sudo", "-n", "systemctl", "stop", MIHOMO_SERVICE],
                       capture_output=True, text=True, timeout=20)
    if r.returncode != 0:
        return jsonify({"ok": False, "error": r.stderr.strip()}), 500
    return jsonify({"ok": True})


# ── Routes: Daily News ──────────────────────────────────────────────
DAILY_NEWS_DIR = os.path.expanduser("~/.hermes/daily-news")

@app.route("/api/daily-news")
def daily_news_list():
    """List all daily news HTML files."""
    items = []
    if os.path.isdir(DAILY_NEWS_DIR):
        for fn in sorted(os.listdir(DAILY_NEWS_DIR), reverse=True):
            if fn.startswith("daily-news-") and fn.endswith(".html"):
                # daily-news-YYYY-MM-DD.html
                date_str = fn.replace("daily-news-", "").replace(".html", "")
                path = os.path.join(DAILY_NEWS_DIR, fn)
                mtime = os.path.getmtime(path)
                mtime_str = datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M")
                items.append({
                    "filename": fn,
                    "title": f"每日信息播报 - {date_str}",
                    "date": date_str,
                    "mtime": mtime_str,
                    "category": "AI/金融摘要"
                })
    return jsonify({"items": items})

@app.route("/api/daily-news/view/<path:filename>")
def daily_news_view(filename):
    """View a daily news HTML file inline."""
    safe_name = safe_filename(filename)
    if not safe_name.startswith("daily-news-") or not safe_name.endswith(".html"):
        return jsonify({"error": "invalid filename"}), 400
    path = os.path.join(DAILY_NEWS_DIR, safe_name)
    if not os.path.isfile(path):
        return jsonify({"error": "not found"}), 404
    return send_file(path, mimetype="text/html")

@app.route("/api/daily-news/download/<path:filename>")
def daily_news_download(filename):
    """Download a daily news HTML file."""
    safe_name = safe_filename(filename)
    if not safe_name.startswith("daily-news-") or not safe_name.endswith(".html"):
        return jsonify({"error": "invalid filename"}), 400
    path = os.path.join(DAILY_NEWS_DIR, safe_name)
    if not os.path.isfile(path):
        return jsonify({"error": "not found"}), 404
    return send_file(path, mimetype="text/html",
                     as_attachment=True, download_name=safe_name)


# ── Routes: Reachability check ──────────────────────────────────────
# Probe the most-used domestic + international apps, so AW can tell at a
# glance whether the gateway's routing is healthy. Domestic targets should
# all hit DIRECT (fast); international targets should all hit Proxies
# (also fast, if the current proxy node is alive).

REACH_TARGETS = [
    {"id": "wechat",   "group": "domestic", "name": "微信",        "icon": "💬", "url": "https://weixin.qq.com/"},
    {"id": "bilibili", "group": "domestic", "name": "B 站",        "icon": "📺", "url": "https://www.bilibili.com/"},
    {"id": "taobao",   "group": "domestic", "name": "淘宝",        "icon": "🛒", "url": "https://www.taobao.com/"},
    {"id": "baidu",    "group": "domestic", "name": "百度",        "icon": "🔍", "url": "https://www.baidu.com/"},
    {"id": "douyin",   "group": "domestic", "name": "抖音",        "icon": "🎵", "url": "https://www.douyin.com/"},
    {"id": "google",   "group": "intl",     "name": "Google",      "icon": "🌐", "url": "https://www.google.com/generate_204"},
    {"id": "youtube",  "group": "intl",     "name": "YouTube",     "icon": "▶",  "url": "https://www.youtube.com/"},
    {"id": "github",   "group": "intl",     "name": "GitHub",      "icon": "💻", "url": "https://github.com/"},
    {"id": "x",        "group": "intl",     "name": "X / Twitter", "icon": "𝕏",  "url": "https://twitter.com/"},
    {"id": "openai",   "group": "intl",     "name": "ChatGPT",     "icon": "🤖", "url": "https://chat.openai.com/"},
]


def _reach_check_one(target, timeout=6):
    """Probe a single target. Reachable = any HTTP response (incl. 4xx/5xx).
    Unreachable = DNS failure / connection refused / read timeout.
    """
    url = target["url"]
    start = time.monotonic()
    code = 0
    err = ""
    status = "fail"
    try:
        req = urllib.request.Request(url, method="GET", headers={
            "User-Agent": "Mozilla/5.0 (compatible; NebulaShare-Reach/1.0)",
            "Accept": "*/*",
            # Range hint so we don't pull big home pages when the server honors it
            "Range": "bytes=0-0",
        })
        with urllib.request.urlopen(req, timeout=timeout) as r:
            code = r.status
        status = "ok" if 200 <= code < 400 else "warn"
    except urllib.error.HTTPError as e:
        # An HTTP error means the host responded — counts as reachable.
        code = e.code
        # 200/206/301/302/304 = clean ok; 403/451/4xx still means TCP/TLS works;
        # 5xx = server up but unhappy.
        if 200 <= code < 400:
            status = "ok"
        elif 400 <= code < 500:
            status = "warn"  # reachable but blocked/forbidden
        else:
            status = "warn"
    except urllib.error.URLError as e:
        err = str(getattr(e, "reason", e))
        status = "fail"
    except (socket.timeout, TimeoutError):
        err = "timeout"
        status = "fail"
    except Exception as e:
        err = str(e)[:80]
        status = "fail"
    latency_ms = int((time.monotonic() - start) * 1000)
    return {
        "id": target["id"],
        "status": status,
        "code": code,
        "latency_ms": latency_ms,
        "error": err,
        "checked_at": int(time.time()),
    }


@app.route("/api/reach/list")
def reach_list():
    return jsonify({"ok": True, "targets": REACH_TARGETS})


@app.route("/api/reach/check")
def reach_check_one():
    tid = request.args.get("id") or ""
    target = next((t for t in REACH_TARGETS if t["id"] == tid), None)
    if not target:
        return jsonify({"ok": False, "error": "unknown id"}), 400
    result = _reach_check_one(target)
    return jsonify({"ok": True, "result": result})


@app.route("/api/reach/check-all")
def reach_check_all():
    results = [None] * len(REACH_TARGETS)
    threads = []
    for i, t in enumerate(REACH_TARGETS):
        def worker(idx=i, tgt=t):
            try:
                results[idx] = _reach_check_one(tgt)
            except Exception as e:
                results[idx] = {"id": tgt["id"], "status": "fail",
                                "code": 0, "latency_ms": 0,
                                "error": str(e)[:80], "checked_at": int(time.time())}
        thr = threading.Thread(target=worker)
        thr.daemon = True
        thr.start()
        threads.append(thr)
    for thr in threads:
        thr.join(timeout=8.0)
    return jsonify({"ok": True, "results": [r for r in results if r is not None]})


# ── PC Console: Wake-on-LAN + Status + Shutdown ─────────────────────

PC_IP = os.environ.get("PC_IP", "192.168.50.206")
PC_MAC = os.environ.get("PC_MAC", "34:5A:60:CE:E6:DB")
PC_NAME = os.environ.get("PC_NAME", "Windows PC")
PC_SSH_USER = os.environ.get("PC_SSH_USER", "aw")
PC_SSH_KEY = os.environ.get("PC_SSH_KEY", "")
WOL_BROADCAST = os.environ.get("WOL_BROADCAST", "")


@app.route("/api/pc/status")
def api_pc_status():
    """Ping the PC to check if it's online."""
    try:
        r = subprocess.run(
            ["ping", "-c", "1", "-W", "2", PC_IP],
            capture_output=True, text=True, timeout=5
        )
        online = r.returncode == 0
        # Extract RTT from ping output (e.g., "time=0.526 ms")
        rtt = None
        if online:
            m = __import__("re").search(r"time=([\d.]+)\s*ms", r.stdout)
            if m:
                rtt = round(float(m.group(1)), 2)
        return jsonify({
            "ok": True,
            "online": online,
            "ip": PC_IP,
            "mac": PC_MAC,
            "name": PC_NAME,
            "rtt_ms": rtt,
        })
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/wol", methods=["POST"])
def api_wol():
    """Send Wake-on-LAN magic packet via wakeonlan CLI."""
    body = request.get_json(silent=True) or {}
    mac = (body.get("mac") or PC_MAC).strip().upper()
    # Validate MAC format
    if not mac or len(mac.replace(":", "")) != 12:
        return jsonify({"ok": False, "error": "invalid MAC address"}), 400
    cmd = ["wakeonlan", mac]
    if WOL_BROADCAST:
        cmd.extend(["-i", WOL_BROADCAST])
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        if r.returncode != 0:
            return jsonify({"ok": False, "error": r.stderr.strip() or "wakeonlan failed"}), 500
        return jsonify({"ok": True, "mac": mac, "output": r.stdout.strip()})
    except FileNotFoundError:
        return jsonify({"ok": False, "error": "wakeonlan command not found. Run: sudo apt install wakeonlan"}), 500
    except subprocess.TimeoutExpired:
        return jsonify({"ok": False, "error": "wakeonlan timeout"}), 504
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/pc/shutdown", methods=["POST"])
def api_pc_shutdown():
    """SSH into Windows PC and execute shutdown command."""
    try:
        cmd = [
            "ssh",
            "-o", "ConnectTimeout=5",
            "-o", "BatchMode=yes",
            "-o", "StrictHostKeyChecking=accept-new",
        ]
        if PC_SSH_KEY and os.path.isfile(PC_SSH_KEY):
            cmd.extend(["-i", PC_SSH_KEY])
        cmd.append(f"{PC_SSH_USER}@{PC_IP}")
        cmd.append("shutdown /s /t 0")

        r = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        # ssh may return 255 on connection failure, or 0 on success
        # Windows shutdown command doesn't wait, so success usually means ssh succeeded
        if r.returncode == 0:
            return jsonify({"ok": True})
        # Some versions return 1 even if shutdown was triggered
        if "shutdown" in r.stderr.lower() or "logoff" in r.stderr.lower():
            return jsonify({"ok": True, "warn": "command may have succeeded"})
        err = r.stderr.strip() or r.stdout.strip() or f"ssh exit code {r.returncode}"
        return jsonify({"ok": False, "error": err}), 502
    except FileNotFoundError:
        return jsonify({"ok": False, "error": "ssh command not found. Run: sudo apt install openssh-client"}), 500
    except subprocess.TimeoutExpired:
        return jsonify({"ok": False, "error": "ssh connection timeout"}), 504
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


# ── Routes: System Stats ────────────────────────────────────────────
# Pure on-demand: no background thread. Each call to /api/system/stats
# samples /proc files (μs) + one vcgencmd shell-out (~5ms). CPU% is
# computed against the previous call's /proc/stat snapshot, so values
# are averaged over the actual client polling interval — accurate, and
# zero cost when nobody is watching.

_sys_lock = threading.Lock()
_sys_cpu_prev = None        # (idle, total) from /proc/stat
_sys_cpu_prev_ts = 0.0


def _read_cpu_idle_total():
    try:
        with open("/proc/stat", "r") as f:
            line = f.readline()
        parts = line.split()
        if not parts or parts[0] != "cpu":
            return None
        nums = [int(x) for x in parts[1:]]
        # idle + iowait
        idle = nums[3] + (nums[4] if len(nums) > 4 else 0)
        total = sum(nums)
        return (idle, total)
    except Exception:
        return None


def _read_meminfo():
    info = {}
    try:
        with open("/proc/meminfo", "r") as f:
            for ln in f:
                k, _, v = ln.partition(":")
                v = v.strip().split()
                if v:
                    info[k] = int(v[0]) * 1024
    except Exception:
        pass
    return info


def _read_temp_c():
    try:
        with open("/sys/class/thermal/thermal_zone0/temp", "r") as f:
            return int(f.read().strip()) / 1000.0
    except Exception:
        pass
    try:
        out = subprocess.run(["vcgencmd", "measure_temp"],
                             capture_output=True, text=True, timeout=1).stdout
        if "=" in out:
            return float(out.split("=", 1)[1].split("'", 1)[0])
    except Exception:
        pass
    return None


def _read_throttle():
    try:
        out = subprocess.run(["vcgencmd", "get_throttled"],
                             capture_output=True, text=True, timeout=1).stdout.strip()
        if "=" in out:
            raw = out.split("=", 1)[1]
            mask = int(raw, 16)
            # bits 0-3: now (under-volt, freq-cap, throttled, soft-temp limit)
            # bits 16-19: history flags (ever happened since boot)
            return raw, bool(mask & 0xF), bool(mask & 0xF0000)
    except Exception:
        pass
    return "", False, False


# ── Process Monitor helpers ─────────────────────────────────────────

# Cache for process CPU sampling: pid -> (utime+stime, system_total, timestamp)
_proc_cpu_cache = {}
_proc_cpu_cache_ts = 0.0

_SC_CLK_TCK = os.sysconf(os.sysconf_names.get('SC_CLK_TCK', 2)) if hasattr(os, 'sysconf') else 100


def _get_boot_time():
    """Read system boot time from /proc/stat (cached)."""
    try:
        with open("/proc/stat", "r") as f:
            for line in f:
                if line.startswith("btime "):
                    return int(line.split()[1])
    except Exception:
        pass
    return 0

_BOOT_TIME = _get_boot_time()


def _read_proc_utime_stime(pid):
    """Read a process's user+system CPU ticks from /proc/<pid>/stat."""
    try:
        with open(f"/proc/{pid}/stat", "r") as f:
            stat = f.read().strip()
        # Command name is in parentheses; find the last ')'
        idx = stat.rfind(")")
        if idx == -1:
            return None
        parts = stat[idx + 1 :].split()
        # fields: state, ppid, pgrp, session, tty_nr, tpgid, flags, minflt,
        #         cminflt, majflt, cmajflt, utime, stime, ...
        return int(parts[11]) + int(parts[12])
    except Exception:
        return None


def _sample_all_procs_cpu():
    """Return (dict pid->utime_stime, system_total, timestamp)."""
    result = {}
    sys_total = None
    try:
        sys_total = _read_cpu_idle_total()
        if sys_total:
            sys_total = sys_total[1]
    except Exception:
        pass
    now = time.time()
    try:
        for name in os.listdir("/proc"):
            if not name.isdigit():
                continue
            pid = int(name)
            t = _read_proc_utime_stime(pid)
            if t is not None:
                result[pid] = t
    except Exception:
        pass
    return result, sys_total, now


def _get_daemon_info(pid):
    """Return (is_daemon: bool, service_name: str|None, auto_restart: bool)."""
    # 1. Try cgroup path for systemd service
    service = None
    try:
        with open(f"/proc/{pid}/cgroup", "r") as f:
            cg = f.read()
        for line in cg.strip().split("\n"):
            parts = line.split(":")
            if len(parts) >= 3:
                path = parts[2]
                if ".service" in path:
                    # e.g. /system.slice/mihomo.service
                    svc = path.split("/")[-1]
                    if svc.endswith(".service"):
                        service = svc
                        break
    except Exception:
        pass

    # 2. If no service found, check PPID == 1 (direct child of init)
    ppid = None
    try:
        with open(f"/proc/{pid}/stat", "r") as f:
            stat = f.read().strip()
        idx = stat.rfind(")")
        parts = stat[idx + 1 :].split()
        ppid = int(parts[1])
    except Exception:
        pass

    if service:
        # Check Restart policy
        auto_restart = False
        try:
            out = (
                subprocess.run(
                    ["systemctl", "show", service, "--property=Restart"],
                    capture_output=True,
                    text=True,
                    timeout=2,
                )
                .stdout.strip()
            )
            if "=" in out:
                val = out.split("=", 1)[1].strip()
                auto_restart = val != "no"
        except Exception:
            pass
        return True, service, auto_restart

    if ppid == 1:
        return True, None, False

    return False, None, False


def _read_processes():
    """Read all accessible processes. Returns list of dicts."""
    global _proc_cpu_cache, _proc_cpu_cache_ts

    # ── Two-point sampling for CPU % ──
    sample1, sys_total1, ts1 = _sample_all_procs_cpu()
    time.sleep(0.25)
    sample2, sys_total2, ts2 = _sample_all_procs_cpu()

    delta_sys = (sys_total2 - sys_total1) if sys_total1 and sys_total2 else 0
    ncpu = os.cpu_count() or 1

    processes = []
    try:
        for name in os.listdir("/proc"):
            if not name.isdigit():
                continue
            pid = int(name)
            try:
                # /proc/<pid>/stat
                with open(f"/proc/{pid}/stat", "r") as f:
                    stat = f.read().strip()
                idx = stat.rfind(")")
                if idx == -1:
                    continue
                sparts = stat[idx + 1 :].split()
                ppid = int(sparts[1])

                # starttime is field 22 (0-indexed 19 from state)
                starttime_ticks = int(sparts[19]) if len(sparts) > 19 else 0
                if _BOOT_TIME and _SC_CLK_TCK:
                    proc_start = _BOOT_TIME + starttime_ticks / _SC_CLK_TCK
                    runtime_seconds = max(0, int(time.time() - proc_start))
                else:
                    runtime_seconds = 0

                # /proc/<pid>/status
                proc_name = ""
                uid = 0
                vm_rss = 0
                try:
                    with open(f"/proc/{pid}/status", "r") as f:
                        for line in f:
                            if line.startswith("Name:"):
                                proc_name = line.split(":", 1)[1].strip()
                            elif line.startswith("Uid:"):
                                uid = int(line.split()[1])
                            elif line.startswith("VmRSS:"):
                                vm_rss = int(line.split()[1].strip().split()[0]) * 1024
                except Exception:
                    pass

                # /proc/<pid>/cmdline
                cmdline = ""
                try:
                    with open(f"/proc/{pid}/cmdline", "rb") as f:
                        raw = f.read()
                    cmdline = raw.replace(b"\x00", b" ").decode("utf-8", "replace").strip()
                except Exception:
                    pass

                # CPU %
                cpu_pct = None
                t1 = sample1.get(pid)
                t2 = sample2.get(pid)
                if t1 is not None and t2 is not None and delta_sys > 0:
                    d_proc = t2 - t1
                    cpu_pct = max(0.0, min(100.0 * ncpu, 100.0 * d_proc / delta_sys * ncpu))

                # Daemon info
                is_daemon, service_name, auto_restart = _get_daemon_info(pid)

                # Memory fallback: use statm if status VmRSS missing
                if vm_rss == 0:
                    try:
                        with open(f"/proc/{pid}/statm", "r") as f:
                            sm = f.read().split()
                        vm_rss = int(sm[1]) * 4096  # pages -> bytes
                    except Exception:
                        pass

                processes.append(
                    {
                        "pid": pid,
                        "ppid": ppid,
                        "name": proc_name or (cmdline.split()[0] if cmdline else f"[{pid}]"),
                        "cmdline": cmdline,
                        "uid": uid,
                        "cpu_percent": round(cpu_pct, 1) if cpu_pct is not None else None,
                        "mem_bytes": vm_rss,
                        "runtime_seconds": runtime_seconds,
                        "is_daemon": is_daemon,
                        "service_name": service_name,
                        "auto_restart": auto_restart,
                    }
                )
            except (PermissionError, FileNotFoundError, ProcessLookupError):
                continue
            except Exception:
                continue
    except Exception:
        pass

    # Update cache for future reference
    _proc_cpu_cache = sample2
    _proc_cpu_cache_ts = ts2
    return processes


@app.route("/api/system/processes")
def api_system_processes():
    procs = _read_processes()
    # Sort by CPU desc, then mem desc
    procs.sort(key=lambda p: (p.get("cpu_percent") or -1, p.get("mem_bytes") or 0), reverse=True)
    return jsonify({"ok": True, "processes": procs, "count": len(procs)})


@app.route("/api/system/process/<int:pid>/kill", methods=["POST"])
def api_kill_process(pid):
    if pid <= 1:
        return jsonify({"ok": False, "error": "不能终止系统关键进程"}), 403
    if pid == os.getpid():
        return jsonify({"ok": False, "error": "不能终止自身进程"}), 403
    try:
        os.kill(pid, 15)  # SIGTERM
        return jsonify({"ok": True, "pid": pid, "signal": 15})
    except ProcessLookupError:
        return jsonify({"ok": False, "error": "进程不存在"}), 404
    except PermissionError:
        return jsonify({"ok": False, "error": "权限不足"}), 403
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/system/stats")
def api_system_stats():
    global _sys_cpu_prev, _sys_cpu_prev_ts

    now = time.time()

    # ── CPU % via delta against previous call ──
    # On a cold/stale prev, do an inline 200ms re-sample so the very first
    # request still returns a real value instead of null.
    cur = _read_cpu_idle_total()
    cpu_pct = None
    with _sys_lock:
        prev = _sys_cpu_prev
        prev_ts = _sys_cpu_prev_ts

    if cur is not None and (prev is None or (now - prev_ts) > 10.0):
        time.sleep(0.2)
        cur2 = _read_cpu_idle_total()
        if cur2 is not None:
            d_idle = cur2[0] - cur[0]
            d_total = cur2[1] - cur[1]
            if d_total > 0:
                cpu_pct = max(0.0, min(100.0, 100.0 * (1 - d_idle / d_total)))
            cur = cur2
    elif cur is not None and prev is not None:
        d_idle = cur[0] - prev[0]
        d_total = cur[1] - prev[1]
        if d_total > 0:
            cpu_pct = max(0.0, min(100.0, 100.0 * (1 - d_idle / d_total)))

    with _sys_lock:
        _sys_cpu_prev = cur
        _sys_cpu_prev_ts = now

    # ── Memory ──
    mem = _read_meminfo()
    mem_total = mem.get("MemTotal", 0)
    mem_avail = mem.get("MemAvailable", 0)
    mem_used = mem_total - mem_avail
    mem_pct = (100.0 * mem_used / mem_total) if mem_total else 0.0

    # ── Disk (root) ──
    try:
        du = shutil.disk_usage("/")
        disk_total, disk_used, disk_free = du.total, du.used, du.free
    except Exception:
        disk_total = disk_used = disk_free = 0
    disk_pct = (100.0 * disk_used / disk_total) if disk_total else 0.0

    # ── Disk (external HDD /mnt/andrew) ──
    HDD_MOUNT = "/mnt/andrew"
    hdd_total = hdd_used = hdd_free = 0
    hdd_pct = 0.0
    hdd_mounted = False
    try:
        if os.path.ismount(HDD_MOUNT):
            hdu = shutil.disk_usage(HDD_MOUNT)
            hdd_total, hdd_used, hdd_free = hdu.total, hdu.used, hdu.free
            hdd_pct = (100.0 * hdd_used / hdd_total) if hdd_total else 0.0
            hdd_mounted = True
    except Exception:
        pass

    # ── Temp + throttle (Pi-specific, gracefully None on non-Pi) ──
    temp_c = _read_temp_c()
    throttle_raw, throttle_now, throttle_history = _read_throttle()

    # ── Uptime + load ──
    try:
        with open("/proc/uptime", "r") as f:
            uptime_s = int(float(f.read().split()[0]))
    except Exception:
        uptime_s = 0
    boot_at = int(now) - uptime_s
    try:
        load = os.getloadavg()
    except Exception:
        load = (0.0, 0.0, 0.0)

    return jsonify({
        "ok": True,
        "stats": {
            "cpu_percent": round(cpu_pct, 1) if cpu_pct is not None else None,
            "cpu_count": os.cpu_count() or 1,
            "load_1": round(load[0], 2),
            "load_5": round(load[1], 2),
            "load_15": round(load[2], 2),
            "mem_total": mem_total, "mem_used": mem_used, "mem_avail": mem_avail,
            "mem_percent": round(mem_pct, 1),
            "disk_total": disk_total, "disk_used": disk_used, "disk_free": disk_free,
            "disk_percent": round(disk_pct, 1),
            "hdd_total": hdd_total, "hdd_used": hdd_used, "hdd_free": hdd_free,
            "hdd_percent": round(hdd_pct, 1),
            "hdd_mounted": hdd_mounted,
            "temp_c": round(temp_c, 1) if temp_c is not None else None,
            "throttle_raw": throttle_raw,
            "throttle_now": throttle_now,
            "throttle_history": throttle_history,
            "uptime_s": uptime_s,
            "boot_at": boot_at,
            "updated": int(now),
        },
    })


# ── Storage file manager (multi-device) ─────────────────────────────
STORAGE_ROOTS = {
    "/mnt/andrew": "移动硬盘",
    "/": "SSD",
}
STORAGE_MAX_UPLOAD_MB = 1024  # 1 GB per upload safety limit


def _get_storage_root(root_param):
    """Validate and return a storage root path from user input."""
    if not root_param:
        return "/mnt/andrew"
    # Only allow exact paths from the whitelist
    for allowed in STORAGE_ROOTS:
        if os.path.realpath(root_param) == os.path.realpath(allowed):
            return allowed
    return None


def _validate_storage_path(rel, root):
    """Prevent path traversal; return absolute path under root or None."""
    if not root or root not in STORAGE_ROOTS:
        return None
    if not rel:
        rel = ""
    target = os.path.realpath(os.path.join(root, rel))
    real_root = os.path.realpath(root)
    # Use relpath to check target is inside or equal to real_root
    try:
        rel_to_root = os.path.relpath(target, real_root)
    except ValueError:
        return None
    if rel_to_root.startswith(".."):
        return None
    return target


def _storage_entry_info(p, name):
    """Return dict describing a file or directory entry."""
    try:
        st = os.stat(p, follow_symlinks=False)
        is_dir = os.path.isdir(p) and not os.path.islink(p)
        info = {
            "name": name,
            "type": "dir" if is_dir else "file",
            "size": st.st_size if not is_dir else 0,
            "size_human": fmt_size(st.st_size) if not is_dir else "-",
            "mtime": int(st.st_mtime),
            "mtime_iso": datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d %H:%M"),
        }
        return info
    except Exception:
        return None


@app.route("/api/storage/roots")
def api_storage_roots():
    roots = []
    for path, label in STORAGE_ROOTS.items():
        try:
            if os.path.ismount(path) or (path == "/" and os.path.isdir(path)):
                du = shutil.disk_usage(path)
                roots.append({
                    "path": path,
                    "label": label,
                    "total": du.total,
                    "used": du.used,
                    "free": du.free,
                    "used_human": fmt_size(du.used),
                    "total_human": fmt_size(du.total),
                    "percent": round(100.0 * du.used / du.total, 1),
                })
        except Exception:
            pass
    return jsonify({"ok": True, "roots": roots})


@app.route("/api/storage/files")
def api_storage_files():
    root = _get_storage_root(request.args.get("root", ""))
    if root is None:
        return jsonify({"ok": False, "error": "invalid root"}), 400
    rel = request.args.get("path", "")
    target = _validate_storage_path(rel, root)
    if target is None:
        return jsonify({"ok": False, "error": "invalid path"}), 400
    if not os.path.isdir(target):
        return jsonify({"ok": False, "error": "not a directory"}), 404
    items = []
    try:
        for name in os.listdir(target):
            # skip hidden
            if name.startswith("."):
                continue
            p = os.path.join(target, name)
            info = _storage_entry_info(p, name)
            if info:
                items.append(info)
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500
    items.sort(key=lambda x: (0 if x["type"] == "dir" else 1, x["name"].lower()))
    # compute usage bar
    try:
        du = shutil.disk_usage(root)
        total, used = du.total, du.used
    except Exception:
        total = used = 0
    return jsonify({
        "ok": True,
        "items": items,
        "path": rel,
        "root": root,
        "root_label": STORAGE_ROOTS.get(root, root),
        "total": total,
        "used": used,
        "used_human": fmt_size(used),
        "total_human": fmt_size(total),
        "percent": round(100.0 * used / total, 1) if total else 0.0,
    })


@app.route("/api/storage/upload", methods=["POST"])
def api_storage_upload():
    root = _get_storage_root(request.args.get("root", ""))
    if root is None:
        return jsonify({"ok": False, "error": "invalid root"}), 400
    rel = request.args.get("path", "")
    target = _validate_storage_path(rel, root)
    if target is None or not os.path.isdir(target):
        return jsonify({"ok": False, "error": "invalid path"}), 400
    if "file" not in request.files:
        return jsonify({"ok": False, "error": "no file"}), 400
    f = request.files["file"]
    if not f.filename:
        return jsonify({"ok": False, "error": "empty filename"}), 400
    content_length = request.content_length
    if content_length and content_length > STORAGE_MAX_UPLOAD_MB * 1024 * 1024:
        return jsonify({"ok": False, "error": f"file too large (>{STORAGE_MAX_UPLOAD_MB}MB)"}), 413
    name = safe_filename(f.filename)
    dest = os.path.join(target, name)
    if os.path.exists(dest):
        base, ext = os.path.splitext(name)
        counter = 1
        while os.path.exists(dest):
            dest = os.path.join(target, f"{base}_{counter}{ext}")
            counter += 1
        name = os.path.basename(dest)
    f.save(dest)
    return jsonify({"ok": True, "filename": name})


@app.route("/api/storage/download")
def api_storage_download():
    root = _get_storage_root(request.args.get("root", ""))
    if root is None:
        return jsonify({"ok": False, "error": "invalid root"}), 400
    rel = request.args.get("path", "")
    target = _validate_storage_path(rel, root)
    if target is None or not os.path.isfile(target):
        return jsonify({"ok": False, "error": "not found"}), 404
    return send_file(target, as_attachment=True, download_name=os.path.basename(target))


@app.route("/api/storage/files", methods=["DELETE"])
def api_storage_delete():
    root = _get_storage_root(request.args.get("root", ""))
    if root is None:
        return jsonify({"ok": False, "error": "invalid root"}), 400
    rel = request.args.get("path", "")
    target = _validate_storage_path(rel, root)
    if target is None:
        return jsonify({"ok": False, "error": "invalid path"}), 400
    if not os.path.exists(target):
        return jsonify({"ok": False, "error": "not found"}), 404
    try:
        if os.path.isdir(target):
            os.rmdir(target)
        else:
            os.remove(target)
        return jsonify({"ok": True})
    except OSError as e:
        return jsonify({"ok": False, "error": str(e)}), 400


@app.route("/api/storage/mkdir", methods=["POST"])
def api_storage_mkdir():
    root = _get_storage_root(request.args.get("root", ""))
    if root is None:
        return jsonify({"ok": False, "error": "invalid root"}), 400
    rel = request.args.get("path", "")
    target = _validate_storage_path(rel, root)
    if target is None:
        return jsonify({"ok": False, "error": "invalid path"}), 400
    if os.path.exists(target):
        return jsonify({"ok": False, "error": "already exists"}), 409
    try:
        os.makedirs(target, exist_ok=False)
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


# ── photo-cleaner reverse proxy ─────────────────────────────────────
PHOTO_CLEANER_BASE = os.environ.get("PHOTO_CLEANER_BASE", "http://127.0.0.1:8090")


@app.route("/api/photo/<path:subpath>", methods=["GET", "POST"])
def photo_proxy(subpath):
    """转发到本机 photo-cleaner 服务,屏蔽其端口对外暴露。"""
    target = f"{PHOTO_CLEANER_BASE}/{subpath}"
    try:
        if request.method == "GET":
            r = requests.get(target, params=request.args, timeout=180, stream=True)
        else:
            files = None
            data = None
            json_payload = None
            headers = {}
            if request.files:
                # multipart: 重新组装,直接传文件流
                files = {
                    k: (f.filename, f.stream, f.mimetype)
                    for k, f in request.files.items()
                }
                # form fields 走 data
                data = {k: v for k, v in request.form.items()}
            else:
                ctype = request.headers.get("Content-Type", "")
                if ctype.startswith("application/json"):
                    json_payload = request.get_json(silent=True)
                    headers["Content-Type"] = "application/json"
                else:
                    data = request.get_data()
                    if ctype:
                        headers["Content-Type"] = ctype
            r = requests.post(
                target,
                params=request.args,
                files=files,
                data=data,
                json=json_payload,
                headers=headers,
                timeout=180,
                stream=True,
            )
        excluded = {"content-encoding", "content-length",
                    "transfer-encoding", "connection"}
        out_headers = [(k, v) for k, v in r.raw.headers.items()
                       if k.lower() not in excluded]
        return Response(r.iter_content(8192), status=r.status_code,
                        headers=out_headers)
    except requests.RequestException as e:
        return jsonify({"ok": False, "error": f"photo-cleaner 不可达: {e}"}), 503


# ── Claude History API ──────────────────────────────────────────────
CLAUDE_HISTORY_DIR = "/home/aw/vibeProjects/claude-history/data"
CLAUDE_HISTORY_FILE = os.path.join(CLAUDE_HISTORY_DIR, "history.json")
CLAUDE_DEVICES_DIR = os.path.join(CLAUDE_HISTORY_DIR, "devices")
os.makedirs(CLAUDE_DEVICES_DIR, exist_ok=True)


def _load_all_devices_data():
    """加载所有设备的历史数据并合并"""
    all_sessions = []
    all_projects = {}
    devices_info = {}
    total_messages = 0
    all_categories = {}
    all_styles = {}
    total_tokens = {"input": 0, "output": 0, "cacheRead": 0, "cacheWrite": 0, "total": 0, "estimatedCostUSD": 0.0}

    # 加载设备历史数据：合并 devices/（API 上传）和 data/ 根目录（Git 同步）
    # 同一设备取修改时间最新的文件
    candidate_files = {}  # hostname -> (fpath, mtime)

    def _scan_dir(dir_path):
        if not os.path.isdir(dir_path):
            return
        for fname in os.listdir(dir_path):
            if fname.startswith("history-") and fname.endswith(".json"):
                fpath = os.path.join(dir_path, fname)
                hostname = fname.replace("history-", "").replace(".json", "")
                mtime = os.path.getmtime(fpath)
                if hostname not in candidate_files or mtime > candidate_files[hostname][1]:
                    candidate_files[hostname] = (fpath, mtime)

    _scan_dir(CLAUDE_DEVICES_DIR)
    _scan_dir(CLAUDE_HISTORY_DIR)

    sources = [(h, candidate_files[h][0]) for h in candidate_files]

    for hostname, fpath in sources:
        try:
            with open(fpath, encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            continue

        meta = data.get("meta", {})
        machine_info = meta.get("machineInfo", {})
        device_name = machine_info.get("hostname", hostname)
        device_id = machine_info.get("machineId", hostname)

        devices_info[device_id] = {
            "hostname": device_name,
            "machineId": device_id,
            "localIp": machine_info.get("localIp", "unknown"),
            "platform": machine_info.get("platform", "unknown"),
            "lastSync": meta.get("generatedAt", ""),
            "sessions": meta.get("totalSessions", 0),
            "messages": meta.get("totalMessages", 0),
        }

        # 合并项目统计
        for proj, count in meta.get("projects", {}).items():
            all_projects[proj] = all_projects.get(proj, 0) + count

        # 合并分类和风格统计
        for cat, count in meta.get("categoryDistribution", {}).items():
            all_categories[cat] = all_categories.get(cat, 0) + count
        for style, count in meta.get("styleDistribution", {}).items():
            all_styles[style] = all_styles.get(style, 0) + count

        # 合并 token 统计
        toks = meta.get("totalTokens", {})
        for k in ["input", "output", "cacheRead", "cacheWrite", "total"]:
            total_tokens[k] += toks.get(k, 0)
        total_tokens["estimatedCostUSD"] += toks.get("estimatedCostUSD", 0)

        # 为每条会话和消息标记设备来源
        for session in data.get("sessions", []):
            session["deviceId"] = device_id
            session["deviceName"] = device_name
            for msg in session.get("messages", []):
                msg.setdefault("machineId", device_id)
                msg.setdefault("hostname", device_name)
            all_sessions.append(session)
            total_messages += session.get("messageCount", 0)

    # 按时间倒序排列
    all_sessions.sort(key=lambda x: x.get("startTimeMs", 0), reverse=True)

    return {
        "meta": {
            "generatedAt": datetime.now().isoformat(),
            "totalSessions": len(all_sessions),
            "totalMessages": total_messages,
            "projects": all_projects,
            "devices": devices_info,
            "deviceCount": len(devices_info),
            "categoryDistribution": all_categories,
            "styleDistribution": all_styles,
            "totalTokens": total_tokens,
        },
        "sessions": all_sessions,
    }


@app.route("/api/claude-history")
def claude_history():
    """返回所有设备的 Claude Code 历史会话数据（合并视图）"""
    data = _load_all_devices_data()
    return jsonify(data)


@app.route("/api/claude-history/sync", methods=["POST"])
def claude_history_sync():
    """接收其他设备上传的历史数据"""
    try:
        payload = request.get_json(force=True)
        if not payload:
            return jsonify({"ok": False, "error": "Empty payload"}), 400

        meta = payload.get("meta", {})
        machine_info = meta.get("machineInfo", {})
        hostname = machine_info.get("hostname", "unknown")
        machine_id = machine_info.get("machineId", "unknown")

        # 增量合并：如果该设备已有数据，合并新旧会话
        device_file = os.path.join(CLAUDE_DEVICES_DIR, f"history-{hostname}.json")
        merged_payload = payload
        if os.path.isfile(device_file):
            try:
                with open(device_file, encoding="utf-8") as f:
                    old_data = json.load(f)
                old_sessions = {s["sessionId"]: s for s in old_data.get("sessions", [])}
                new_sessions = {s["sessionId"]: s for s in payload.get("sessions", [])}
                # 新会话覆盖旧会话，保留旧会话中不存在的
                old_sessions.update(new_sessions)
                merged_sessions = list(old_sessions.values())
                merged_sessions.sort(key=lambda x: x.get("startTimeMs", 0), reverse=True)
                merged_payload = dict(payload)
                merged_payload["sessions"] = merged_sessions
                merged_payload["meta"] = dict(meta)
                merged_payload["meta"]["totalSessions"] = len(merged_sessions)
                merged_payload["meta"]["totalMessages"] = sum(s.get("messageCount", 0) for s in merged_sessions)
                # Token 统计也需要重新累加
                tok = {"input": 0, "output": 0, "cacheRead": 0, "cacheWrite": 0, "total": 0, "cost": 0.0}
                for s in merged_sessions:
                    t = s.get("totalTokens", {})
                    for k in tok:
                        if k == "cost":
                            tok[k] += t.get("estimatedCostUSD", 0)
                        else:
                            tok[k] += t.get(k, 0)
                merged_payload["meta"]["totalTokens"] = {
                    "input": int(tok["input"]),
                    "output": int(tok["output"]),
                    "cacheRead": int(tok["cacheRead"]),
                    "cacheWrite": int(tok["cacheWrite"]),
                    "total": int(tok["total"]),
                    "estimatedCostUSD": round(tok["cost"], 4),
                }
            except Exception:
                pass

        with open(device_file, "w", encoding="utf-8") as f:
            json.dump(merged_payload, f, ensure_ascii=False, indent=2)

        # 同时更新索引
        index_file = os.path.join(CLAUDE_DEVICES_DIR, "index.json")
        index_data = {}
        if os.path.isfile(index_file):
            try:
                with open(index_file, encoding="utf-8") as f:
                    index_data = json.load(f)
            except Exception:
                pass

        index_data[hostname] = {
            "machineId": machine_id,
            "lastSync": meta.get("generatedAt", ""),
            "sessions": meta.get("totalSessions", 0),
            "messages": meta.get("totalMessages", 0),
            "localIp": machine_info.get("localIp", "unknown"),
            "platform": machine_info.get("platform", "unknown"),
        }
        with open(index_file, "w", encoding="utf-8") as f:
            json.dump(index_data, f, ensure_ascii=False, indent=2)

        return jsonify({
            "ok": True,
            "message": f"Received {meta.get('totalSessions', 0)} sessions from {hostname}",
            "hostname": hostname,
        })
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/claude-history/devices")
def claude_history_devices():
    """返回已连接的设备列表"""
    index_file = os.path.join(CLAUDE_DEVICES_DIR, "index.json")
    if os.path.isfile(index_file):
        try:
            with open(index_file, encoding="utf-8") as f:
                return jsonify(json.load(f))
        except Exception:
            pass
    return jsonify({})


@app.route("/api/claude-history/upload", methods=["POST"])
def claude_history_upload():
    """接收其他电脑上传的 Claude 历史数据文件 (ZIP/JSON/JSONL)"""
    import zipfile
    import shutil

    if "file" not in request.files:
        return jsonify({"ok": False, "error": "no file"}), 400

    f = request.files["file"]
    if not f.filename:
        return jsonify({"ok": False, "error": "empty filename"}), 400

    hostname = request.form.get("hostname", "unknown-device")
    hostname = "".join(c for c in hostname if c.isalnum() or c in "-_").strip("-_")
    if not hostname:
        hostname = "unknown-device"

    upload_tmp = os.path.join("/tmp", f"claude-upload-{hostname}-{int(time.time())}")
    os.makedirs(upload_tmp, exist_ok=True)

    try:
        filename = f.filename.lower()

        if filename.endswith(".zip"):
            zip_path = os.path.join(upload_tmp, "upload.zip")
            f.save(zip_path)
            with zipfile.ZipFile(zip_path, 'r') as z:
                z.extractall(upload_tmp)
            os.remove(zip_path)
        elif filename.endswith(".json"):
            f.save(os.path.join(upload_tmp, "history.json"))
        elif filename.endswith(".jsonl"):
            f.save(os.path.join(upload_tmp, "history.jsonl"))
        else:
            return jsonify({"ok": False, "error": "unsupported format, use .zip/.json/.jsonl"}), 400

        def find_file(root, name):
            for dirpath, _dirnames, filenames in os.walk(root):
                if name in filenames:
                    return os.path.join(dirpath, name)
            return None

        history_file = find_file(upload_tmp, "history.json") or find_file(upload_tmp, "history.jsonl")
        if not history_file:
            return jsonify({"ok": False, "error": "no history.json/jsonl found in upload"}), 400

        dest_file = os.path.join(CLAUDE_DEVICES_DIR, f"history-{hostname}.json")
        os.makedirs(CLAUDE_DEVICES_DIR, exist_ok=True)

        if history_file.endswith(".jsonl"):
            sessions = []
            session_msgs = {}
            with open(history_file, encoding="utf-8") as fp:
                for line in fp:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        obj = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    sid = obj.get("sessionId", "unknown")
                    if sid not in session_msgs:
                        session_msgs[sid] = []
                    session_msgs[sid].append({
                        "role": "user",
                        "text": obj.get("display", ""),
                        "timestamp": datetime.fromtimestamp(obj.get("timestamp", 0) / 1000).isoformat(),
                    })
            for sid, msgs in session_msgs.items():
                if not msgs:
                    continue
                sessions.append({
                    "sessionId": sid,
                    "title": msgs[0]["text"][:60],
                    "project": "/unknown",
                    "messageCount": len(msgs),
                    "messages": msgs,
                })
            output = {
                "meta": {
                    "generatedAt": datetime.now().isoformat(),
                    "totalSessions": len(sessions),
                    "totalMessages": sum(s["messageCount"] for s in sessions),
                    "machineInfo": {"hostname": hostname, "platform": "unknown"},
                },
                "sessions": sessions,
            }
            with open(dest_file, "w", encoding="utf-8") as fp:
                json.dump(output, fp, ensure_ascii=False, indent=2)
        else:
            shutil.copy2(history_file, dest_file)

        shutil.rmtree(upload_tmp, ignore_errors=True)

        index_file = os.path.join(CLAUDE_DEVICES_DIR, "index.json")
        index_data = {}
        if os.path.isfile(index_file):
            try:
                with open(index_file, encoding="utf-8") as fp:
                    index_data = json.load(fp)
            except Exception:
                pass

        try:
            with open(dest_file, encoding="utf-8") as fp:
                saved_data = json.load(fp)
            meta = saved_data.get("meta", {})
            index_data[hostname] = {
                "lastSync": datetime.now().isoformat(),
                "sessions": meta.get("totalSessions", 0),
                "messages": meta.get("totalMessages", 0),
                "file": f"history-{hostname}.json",
            }
        except Exception:
            index_data[hostname] = {
                "lastSync": datetime.now().isoformat(),
                "sessions": 0,
                "messages": 0,
                "file": f"history-{hostname}.json",
            }

        with open(index_file, "w", encoding="utf-8") as fp:
            json.dump(index_data, fp, ensure_ascii=False, indent=2)

        return jsonify({
            "ok": True,
            "message": f"Uploaded and saved for {hostname}",
            "hostname": hostname,
            "sessions": index_data[hostname].get("sessions", 0),
        })

    except Exception as e:
        shutil.rmtree(upload_tmp, ignore_errors=True)
        return jsonify({"ok": False, "error": str(e)}), 500


# ── Claude History Scan & Process ───────────────────────────────────

CLAUDE_HISTORY_SOURCE = os.path.expanduser("~/.claude/history.jsonl")
CLAUDE_HISTORY_TOOLS_DIR = "/home/aw/vibeProjects/claude-history"


def _count_history_jsonl():
    """统计 history.jsonl 中的记录数"""
    result = {
        "exists": False,
        "filePath": CLAUDE_HISTORY_SOURCE,
        "fileSize": 0,
        "totalLines": 0,
        "validLines": 0,
        "sessionIds": set(),
        "earliestTimestamp": None,
        "latestTimestamp": None,
    }
    if not os.path.isfile(CLAUDE_HISTORY_SOURCE):
        return result

    result["exists"] = True
    result["fileSize"] = os.path.getsize(CLAUDE_HISTORY_SOURCE)

    try:
        with open(CLAUDE_HISTORY_SOURCE, encoding="utf-8") as f:
            for line in f:
                result["totalLines"] += 1
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                    result["validLines"] += 1
                    sid = obj.get("sessionId")
                    if sid:
                        result["sessionIds"].add(sid)
                    ts = obj.get("timestamp")
                    if ts:
                        if result["earliestTimestamp"] is None or ts < result["earliestTimestamp"]:
                            result["earliestTimestamp"] = ts
                        if result["latestTimestamp"] is None or ts > result["latestTimestamp"]:
                            result["latestTimestamp"] = ts
                except json.JSONDecodeError:
                    pass
    except Exception:
        pass

    return result


@app.route("/api/claude-history/scan")
def claude_history_scan():
    """扫描服务器本地的 history.jsonl，返回统计信息"""
    stats = _count_history_jsonl()
    sessions = list(stats["sessionIds"])
    sessions.sort()

    # 检查已有数据
    has_extracted = os.path.isfile(CLAUDE_HISTORY_FILE)
    has_graph = os.path.isfile(_KNOWLEDGE_GRAPH_FILE)
    has_analysis = os.path.isfile(_KNOWLEDGE_ANALYSIS_FILE)

    existing = {}
    if has_extracted:
        try:
            with open(CLAUDE_HISTORY_FILE, encoding="utf-8") as f:
                data = json.load(f)
            meta = data.get("meta", {})
            existing = {
                "totalSessions": meta.get("totalSessions", 0),
                "totalMessages": meta.get("totalMessages", 0),
                "generatedAt": meta.get("generatedAt", ""),
            }
        except Exception:
            pass

    return jsonify({
        "ok": True,
        "source": {
            "exists": stats["exists"],
            "filePath": stats["filePath"],
            "fileSize": stats["fileSize"],
            "fileSizeHuman": _fmt_bytes(stats["fileSize"]) if stats["fileSize"] else "0 B",
            "totalLines": stats["totalLines"],
            "validLines": stats["validLines"],
            "sessionCount": len(sessions),
            "sessions": sessions[:20],  # 最多返回20个会话ID
            "earliest": datetime.fromtimestamp(stats["earliestTimestamp"] / 1000).isoformat() if stats["earliestTimestamp"] else None,
            "latest": datetime.fromtimestamp(stats["latestTimestamp"] / 1000).isoformat() if stats["latestTimestamp"] else None,
        },
        "existing": existing,
        "hasExtracted": has_extracted,
        "hasGraph": has_graph,
        "hasAnalysis": has_analysis,
    })


def _fmt_bytes(n):
    """格式化字节数"""
    for unit in ["B", "KB", "MB", "GB"]:
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


@app.route("/api/claude-history/process", methods=["POST"])
def claude_history_process():
    """一键处理：提取 → 建图 → 分析"""
    import subprocess

    result = {
        "ok": True,
        "steps": [],
        "totalTimeMs": 0,
    }
    start_time = time.time()

    # Step 1: Extract
    step_start = time.time()
    try:
        extractor_path = os.path.join(CLAUDE_HISTORY_TOOLS_DIR, "extractor.py")
        if not os.path.isfile(extractor_path):
            result["steps"].append({
                "name": "extract",
                "status": "skipped",
                "message": "extractor.py not found",
            })
        else:
            proc = subprocess.run(
                [sys.executable, extractor_path],
                cwd=CLAUDE_HISTORY_TOOLS_DIR,
                capture_output=True,
                text=True,
                timeout=300,
            )
            success = proc.returncode == 0
            result["steps"].append({
                "name": "extract",
                "status": "done" if success else "error",
                "message": f"exit={proc.returncode}, sessions extracted" if success else f"exit={proc.returncode}: {proc.stderr[:200]}",
                "durationMs": round((time.time() - step_start) * 1000),
            })
    except subprocess.TimeoutExpired:
        result["steps"].append({
            "name": "extract",
            "status": "error",
            "message": "timeout after 300s",
            "durationMs": round((time.time() - step_start) * 1000),
        })
    except Exception as e:
        result["steps"].append({
            "name": "extract",
            "status": "error",
            "message": str(e),
            "durationMs": round((time.time() - step_start) * 1000),
        })

    # Step 1.5: Merge all device data into history.json for unified graph building
    step_start = time.time()
    try:
        merged = _load_all_devices_data()
        with open(CLAUDE_HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(merged, f, ensure_ascii=False, indent=2)
        result["steps"].append({
            "name": "merge",
            "status": "done",
            "message": f"Merged {merged['meta'].get('deviceCount', 0)} devices, {merged['meta'].get('totalSessions', 0)} sessions",
            "durationMs": round((time.time() - step_start) * 1000),
        })
    except Exception as e:
        result["steps"].append({
            "name": "merge",
            "status": "warn",
            "message": f"merge skipped: {str(e)[:200]}",
            "durationMs": round((time.time() - step_start) * 1000),
        })

    # Step 2: Build Graph
    step_start = time.time()
    try:
        graph_path = os.path.join(CLAUDE_HISTORY_TOOLS_DIR, "extractor_graph.py")
        if not os.path.isfile(graph_path):
            result["steps"].append({
                "name": "graph",
                "status": "skipped",
                "message": "extractor_graph.py not found",
            })
        else:
            proc = subprocess.run(
                [sys.executable, graph_path],
                cwd=CLAUDE_HISTORY_TOOLS_DIR,
                capture_output=True,
                text=True,
                timeout=300,
            )
            success = proc.returncode == 0
            result["steps"].append({
                "name": "graph",
                "status": "done" if success else "error",
                "message": f"exit={proc.returncode}, graph built" if success else f"exit={proc.returncode}: {proc.stderr[:200]}",
                "durationMs": round((time.time() - step_start) * 1000),
            })
    except subprocess.TimeoutExpired:
        result["steps"].append({
            "name": "graph",
            "status": "error",
            "message": "timeout after 300s",
            "durationMs": round((time.time() - step_start) * 1000),
        })
    except Exception as e:
        result["steps"].append({
            "name": "graph",
            "status": "error",
            "message": str(e),
            "durationMs": round((time.time() - step_start) * 1000),
        })

    # Step 3: Analyze (optional - may take long)
    step_start = time.time()
    try:
        analyzer_path = os.path.join(CLAUDE_HISTORY_TOOLS_DIR, "analyzer.py")
        if not os.path.isfile(analyzer_path):
            result["steps"].append({
                "name": "analyze",
                "status": "skipped",
                "message": "analyzer.py not found",
            })
        else:
            proc = subprocess.run(
                [sys.executable, analyzer_path],
                cwd=CLAUDE_HISTORY_TOOLS_DIR,
                capture_output=True,
                text=True,
                timeout=600,
            )
            success = proc.returncode == 0
            result["steps"].append({
                "name": "analyze",
                "status": "done" if success else "error",
                "message": f"exit={proc.returncode}, analysis complete" if success else f"exit={proc.returncode}: {proc.stderr[:200]}",
                "durationMs": round((time.time() - step_start) * 1000),
            })
    except subprocess.TimeoutExpired:
        result["steps"].append({
            "name": "analyze",
            "status": "error",
            "message": "timeout after 600s",
            "durationMs": round((time.time() - step_start) * 1000),
        })
    except Exception as e:
        result["steps"].append({
            "name": "analyze",
            "status": "error",
            "message": str(e),
            "durationMs": round((time.time() - step_start) * 1000),
        })

    result["totalTimeMs"] = round((time.time() - start_time) * 1000)

    # Check final state
    if os.path.isfile(CLAUDE_HISTORY_FILE):
        try:
            with open(CLAUDE_HISTORY_FILE, encoding="utf-8") as f:
                data = json.load(f)
            meta = data.get("meta", {})
            result["finalState"] = {
                "totalSessions": meta.get("totalSessions", 0),
                "totalMessages": meta.get("totalMessages", 0),
                "hasGraph": os.path.isfile(_KNOWLEDGE_GRAPH_FILE),
                "hasAnalysis": os.path.isfile(_KNOWLEDGE_ANALYSIS_FILE),
            }
        except Exception:
            pass

    return jsonify(result)


# ── Knowledge Base API ──────────────────────────────────────────────

# CORS headers for all knowledge API routes
@app.after_request
def add_cors_headers(response):
    """Add CORS headers to allow frontend cross-origin access."""
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
    return response


# Shared data paths
_KNOWLEDGE_DATA_DIR = "/home/aw/vibeProjects/claude-history/data"
_KNOWLEDGE_GRAPH_FILE = os.path.join(_KNOWLEDGE_DATA_DIR, "graph.json")
_KNOWLEDGE_ANALYSIS_FILE = os.path.join(_KNOWLEDGE_DATA_DIR, "analysis.json")
_KNOWLEDGE_HISTORY_FILE = os.path.join(_KNOWLEDGE_DATA_DIR, "history.json")
_KNOWLEDGE_VALUE_FILTER_FILE = os.path.join(_KNOWLEDGE_DATA_DIR, "value_filter.json")


def _load_json_safe(path, default=None):
    """Load JSON file safely, return default on any error."""
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def _load_graph():
    """Load graph.json with fallback."""
    return _load_json_safe(_KNOWLEDGE_GRAPH_FILE, {"nodes": [], "edges": []})


def _load_analysis():
    """Load analysis.json with fallback."""
    return _load_json_safe(_KNOWLEDGE_ANALYSIS_FILE, {"userProfile": {}, "sessionAnalyses": [], "meta": {}})


def _load_history():
    """Load history.json with fallback."""
    return _load_json_safe(_KNOWLEDGE_HISTORY_FILE, {"sessions": []})


@app.route("/api/knowledge/graph")
def knowledge_graph():
    """返回知识图谱数据（读取 graph.json）"""
    data = _load_graph()
    analysis = _load_analysis()
    # 合并分析元数据到图谱响应
    return jsonify({
        "ok": True,
        "meta": data.get("meta", {}),
        "stats": data.get("stats", {}),
        "nodes": data.get("nodes", []),
        "edges": data.get("edges", []),
        "analysisMeta": analysis.get("meta", {}),
    })


@app.route("/api/knowledge/profile")
def knowledge_profile():
    """返回用户画像（读取 analysis.json 的 userProfile）"""
    analysis = _load_analysis()
    profile = analysis.get("userProfile", {})
    if not profile:
        return jsonify({"ok": False, "error": "profile not found"}), 404
    return jsonify({
        "ok": True,
        "profile": profile,
        "meta": analysis.get("meta", {}),
    })


@app.route("/api/knowledge/sessions")
def knowledge_sessions():
    """按价值过滤返回会话列表

    Query params:
        value: high | medium | low | all (default: all)
    """
    value = request.args.get("value", "all").lower()

    history = _load_history()
    analysis = _load_analysis()
    sessions = history.get("sessions", [])

    # 加载价值过滤配置
    value_map = {}
    if os.path.isfile(_KNOWLEDGE_VALUE_FILTER_FILE):
        value_map = _load_json_safe(_KNOWLEDGE_VALUE_FILTER_FILE, {})

    # 从 analysis.json 构建 sessionId -> analysis 映射
    analysis_map = {}
    for sa in analysis.get("sessionAnalyses", []):
        sid = sa.get("sessionId")
        if sid:
            analysis_map[sid] = sa.get("analysis", {})

    if value != "all":
        sessions = [s for s in sessions if value_map.get(s.get("sessionId"), "medium") == value]

    # 合并返回统一格式
    result = []
    for s in sessions[:50]:
        sid = s.get("sessionId")
        ana = analysis_map.get(sid, {})
        result.append({
            "sessionId": sid,
            "title": s.get("title"),
            "project": s.get("project"),
            "startTime": s.get("startTime"),
            "messageCount": s.get("messageCount"),
            "categories": s.get("categories", []),
            "value": value_map.get(sid, "medium"),
            # 合并 LLM 分析结果
            "analysis": {
                "background": ana.get("background", ""),
                "problem": ana.get("problem", ""),
                "solution": ana.get("solution", ""),
                "mood": ana.get("mood", ""),
                "thinking": ana.get("thinking", ""),
                "style": ana.get("style", ""),
                "risk": ana.get("risk", ""),
                "tech": ana.get("tech", []),
                "role": ana.get("role", ""),
            } if ana else None,
        })

    return jsonify({"ok": True, "sessions": result, "total": len(result)})


@app.route("/api/knowledge/entities")
def knowledge_entities():
    """返回特定类型的实体列表

    Query params:
        type: 实体类型过滤，如 technology, concept, problem, decision, project, session
              不传则返回所有类型统计
    """
    entity_type = request.args.get("type", "").capitalize()
    graph = _load_graph()
    nodes = graph.get("nodes", [])
    edges = graph.get("edges", [])

    if entity_type:
        filtered = [n for n in nodes if n.get("type") == entity_type]
        # 为每个实体附加关联边信息
        node_ids = {n.get("id") for n in filtered}
        related_edges = [
            e for e in edges
            if e.get("source") in node_ids or e.get("target") in node_ids
        ]
        return jsonify({
            "ok": True,
            "type": entity_type,
            "total": len(filtered),
            "entities": filtered,
            "relatedEdges": related_edges[:200],  # 限制边数量
        })
    else:
        # 返回所有类型统计
        type_counts = {}
        for n in nodes:
            t = n.get("type", "Unknown")
            type_counts[t] = type_counts.get(t, 0) + 1
        return jsonify({
            "ok": True,
            "typeCounts": type_counts,
            "totalNodes": len(nodes),
            "totalEdges": len(edges),
        })


@app.route("/api/knowledge/search")
def knowledge_search():
    """搜索知识库内容

    Query params:
        q: 搜索关键词
    """
    query = request.args.get("q", "").lower().strip()
    if not query:
        return jsonify({"ok": True, "results": [], "total": 0})

    history = _load_history()
    graph = _load_graph()
    analysis = _load_analysis()

    results = []
    seen_ids = set()

    # 1. 搜索 history.json 中的会话
    for s in history.get("sessions", []):
        sid = s.get("sessionId")
        title = s.get("title", "")
        msgs = s.get("messages", [])
        match = False
        match_field = ""

        if query in title.lower():
            match = True
            match_field = "title"
        else:
            for m in msgs[:10]:
                text = m.get("text", "")
                if query in text.lower():
                    match = True
                    match_field = "message"
                    break

        if match and sid not in seen_ids:
            seen_ids.add(sid)
            results.append({
                "id": sid,
                "type": "session",
                "title": title,
                "project": s.get("project"),
                "preview": (msgs[0].get("text", "")[:120] + "...") if msgs and msgs[0].get("text") else "",
                "matchField": match_field,
                "messageCount": s.get("messageCount", 0),
            })

    # 2. 搜索 graph.json 中的节点
    for n in graph.get("nodes", []):
        nid = n.get("id")
        title = n.get("title", "")
        summary = n.get("summary", "")
        if query in title.lower() or query in summary.lower():
            if nid not in seen_ids:
                seen_ids.add(nid)
                results.append({
                    "id": nid,
                    "type": n.get("type", "node").lower(),
                    "title": title,
                    "summary": summary[:120] + "..." if len(summary) > 120 else summary,
                    "matchField": "title" if query in title.lower() else "summary",
                    "nodeType": n.get("type"),
                })

    # 3. 搜索 analysis.json 中的会话分析
    for sa in analysis.get("sessionAnalyses", []):
        sid = sa.get("sessionId")
        ana = sa.get("analysis", {})
        title = sa.get("title", "")
        if query in title.lower() or query in ana.get("background", "").lower():
            if sid not in seen_ids:
                seen_ids.add(sid)
                results.append({
                    "id": sid,
                    "type": "analysis",
                    "title": title,
                    "preview": ana.get("background", "")[:120] + "...",
                    "matchField": "title" if query in title.lower() else "background",
                    "mood": ana.get("mood", ""),
                    "role": ana.get("role", ""),
                })

    return jsonify({"ok": True, "results": results[:30], "total": len(results)})


# ── SDK Knowledge Graph API ─────────────────────────────────────────
_SDK_GRAPH_FILE = "/home/aw/vibeProjects/claude-history/charge-pile-graph/graph.json"


@app.route("/api/knowledge/sdk-graph")
def knowledge_sdk_graph():
    """返回充电桩 SDK 4.0 知识图谱数据"""
    data = _load_json_safe(_SDK_GRAPH_FILE, {"nodes": [], "edges": []})
    return jsonify({
        "ok": True,
        "meta": data.get("metadata", {}),
        "nodes": data.get("nodes", []),
        "edges": data.get("edges", []),
    })


# ── MCP Tools API ───────────────────────────────────────────────────
_MCP_SERVER_PATH = "/home/aw/vibeProjects/claude-history/charge-pile-graph/mcp_server.py"


@app.route("/api/mcp/<tool>")
def mcp_tool(tool):
    """执行 MCP 工具查询

    支持的工具:
        list_fault_codes, search_fault_codes, find_interface,
        query_protocol, trace_call_path, what_do_i_need,
        get_state_machine, list_modules, get_protocol_flow
    """
    import subprocess

    valid_tools = {
        "list_fault_codes", "search_fault_codes", "find_interface",
        "query_protocol", "trace_call_path", "what_do_i_need",
        "get_state_machine", "list_modules", "get_protocol_flow",
    }

    if tool not in valid_tools:
        return jsonify({"ok": False, "error": f"未知工具: {tool}"}), 400

    # Build command arguments from query params
    args = []
    for key, value in request.args.items():
        if value:
            args.append(value)

    cmd = [sys.executable, _MCP_SERVER_PATH, tool] + args

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30,
            cwd="/home/aw/vibeProjects/claude-history/charge-pile-graph",
        )
        if result.returncode != 0:
            return jsonify({"ok": False, "error": result.stderr or "执行失败"}), 500

        # Parse JSON output from mcp_server.py
        output = result.stdout.strip()
        # mcp_server.py prints JSON to stdout
        data = json.loads(output)
        return jsonify({"ok": True, "tool": tool, "data": data})
    except subprocess.TimeoutExpired:
        return jsonify({"ok": False, "error": "查询超时"}), 504
    except json.JSONDecodeError:
        return jsonify({"ok": False, "error": "解析结果失败", "raw": output}), 500
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


# ── Static Frontend (Next.js export) ────────────────────────────────
STATIC_DIR = "/home/aw/vibeProjects/NebulaShare/static"


@app.route("/<path:filename>")
def static_catchall(filename):
    """Serve Next.js exported static files; fall back to index.html for SPA routes."""
    # Skip API routes (Flask matches /api/* before this catch-all, but belt-and-suspenders)
    if filename.startswith("api/"):
        return jsonify({"error": "not found"}), 404

    # 1. Direct file match
    target = safe_join(STATIC_DIR, filename)
    if target and os.path.isfile(target):
        return send_from_directory(STATIC_DIR, filename)

    # 2. Subdirectory index.html (e.g. /files/ -> static/files/index.html)
    if filename.endswith("/"):
        index_file = filename + "index.html"
    else:
        index_file = filename + "/index.html"
    target_index = safe_join(STATIC_DIR, index_file)
    if target_index and os.path.isfile(target_index):
        return send_from_directory(STATIC_DIR, index_file)

    # 3. SPA fallback: serve root index.html for unknown paths (client-side routing)
    index_path = os.path.join(STATIC_DIR, "index.html")
    if os.path.isfile(index_path):
        return send_from_directory(STATIC_DIR, "index.html")

    # Transition fallback: if static export isn't deployed yet, serve inline page
    return index()


# ── HTML Frontend ───────────────────────────────────────────────────

HTML_PAGE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Nebula</title>
<style>
:root {
  --bg0: #050810;
  --bg1: #0a0f1e;
  --card: rgba(12, 20, 40, 0.55);
  --cyan: #00f0ff;
  --purple: #b026ff;
  --pink: #ff2a6d;
  --text: #e0e6f0;
  --muted: #8a94a8;
  --border: rgba(0, 240, 255, 0.12);
  --danger: #ff3860;
  --glass: rgba(255,255,255,0.03);
}
* { box-sizing: border-box; margin: 0; padding: 0; }
html, body {
  background: var(--bg0);
  color: var(--text);
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
  min-height: 100vh;
  overflow-x: hidden;
}

/* Canvas background */
#universe {
  position: fixed;
  top: 0; left: 0;
  width: 100%; height: 100%;
  z-index: 0;
  pointer-events: none;
}

/* Ambient glow orbs */
.orb {
  position: fixed;
  border-radius: 50%;
  filter: blur(80px);
  opacity: 0.35;
  z-index: 0;
  pointer-events: none;
  animation: orbFloat 12s ease-in-out infinite alternate;
}
.orb1 {
  width: 400px; height: 400px;
  background: radial-gradient(circle, var(--cyan), transparent 70%);
  top: -100px; left: -100px;
}
.orb2 {
  width: 500px; height: 500px;
  background: radial-gradient(circle, var(--purple), transparent 70%);
  bottom: -150px; right: -150px;
  animation-delay: -6s;
}
.orb3 {
  width: 300px; height: 300px;
  background: radial-gradient(circle, var(--pink), transparent 70%);
  top: 40%; left: 60%;
  animation-delay: -3s;
}
@keyframes orbFloat {
  0% { transform: translate(0,0) scale(1); }
  100% { transform: translate(30px, -30px) scale(1.1); }
}

.container {
  position: relative; z-index: 1;
  max-width: 960px;
  margin: 0 auto;
  padding: 24px 16px 48px;
}

/* Glass card base */
.glass {
  background: var(--card);
  backdrop-filter: blur(20px) saturate(1.3);
  -webkit-backdrop-filter: blur(20px) saturate(1.3);
  border: 1px solid var(--border);
  border-radius: 20px;
  box-shadow: 0 8px 32px rgba(0,0,0,0.3),
              inset 0 1px 0 rgba(255,255,255,0.06);
  overflow: hidden;
  position: relative;
}
.glass::before {
  content: "";
  position: absolute;
  top: 0; left: 0; right: 0; height: 1px;
  background: linear-gradient(90deg, transparent, rgba(0,240,255,0.3), transparent);
}

/* Header */
.header {
  text-align: center;
  margin-bottom: 20px;
}
.header h1 {
  font-size: 2.2rem;
  font-weight: 800;
  letter-spacing: 4px;
  background: linear-gradient(90deg, var(--cyan), var(--purple), var(--pink));
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
  text-shadow: 0 0 60px rgba(0,240,255,0.15);
}
.header h1 .dot-sep {
  margin: 0 14px;
  font-weight: 300;
  opacity: 0.55;
}
.header h1 .brand-aw {
  font-style: italic;
  font-weight: 600;
  letter-spacing: 6px;
}
.header p {
  color: var(--muted);
  font-size: 0.9rem;
  margin-top: 6px;
  letter-spacing: 1px;
}
.header .brand-sub .brand-en {
  margin-left: 8px;
  opacity: 0.55;
  font-size: 0.78rem;
  letter-spacing: 0.5px;
}
.header .quote {
  margin-top: 10px;
  letter-spacing: 0.4px;
  color: rgba(255,255,255,0.62);
  min-height: 2.4em;
  transition: opacity 0.45s ease;
  max-width: 720px;
  margin-left: auto;
  margin-right: auto;
  line-height: 1.5;
}
.header .quote .qen {
  display: block;
  font-size: 0.92rem;
  font-style: italic;
  color: rgba(255,255,255,0.78);
  margin-bottom: 4px;
}
.header .quote .qzh {
  display: block;
  font-size: 0.78rem;
  color: rgba(255,255,255,0.48);
  letter-spacing: 0.6px;
}
.header .quote .qauthor {
  margin-left: 10px;
  font-size: 0.72rem;
  color: rgba(176,38,255,0.72);
  letter-spacing: 0.5px;
  font-variant: small-caps;
}

/* Top bar */
.topbar {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 14px;
  flex-wrap: wrap;
  margin-bottom: 22px;
}
.ip-box {
  background: var(--card);
  backdrop-filter: blur(16px);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 10px 16px;
  font-family: "SF Mono", "Cascadia Mono", monospace;
  font-size: 0.82rem;
  color: var(--cyan);
  box-shadow: 0 0 24px rgba(0,240,255,0.05);
  text-shadow: 0 0 8px rgba(0,240,255,0.25);
  letter-spacing: 0.3px;
}
.qr-wrap {
  background: #fff;
  border-radius: 10px;
  padding: 6px;
  width: 76px; height: 76px;
  display: flex; align-items: center; justify-content: center;
  box-shadow: 0 0 24px rgba(0,240,255,0.1);
}
.qr-wrap img { max-width: 100%; max-height: 100%; display: block; }

/* Section title */
.section-title {
  font-size: 0.85rem;
  font-weight: 600;
  letter-spacing: 2px;
  text-transform: uppercase;
  color: var(--muted);
  margin: 28px 0 12px;
  display: flex;
  align-items: center;
  gap: 10px;
  cursor: pointer;
  user-select: none;
  transition: color 0.18s ease;
}
.section-title:hover { color: var(--cyan); }
.section-title:hover::before {
  background: linear-gradient(90deg, var(--cyan), rgba(0,240,255,0.35));
  width: 32px;
  box-shadow: 0 0 8px rgba(0,240,255,0.45);
}
.section-title:hover .caret {
  color: var(--cyan);
  text-shadow: 0 0 6px rgba(0,240,255,0.55);
}
.section-title::before {
  content: "";
  display: inline-block;
  width: 24px; height: 2px;
  background: linear-gradient(90deg, var(--cyan), transparent);
  border-radius: 1px;
  flex-shrink: 0;
  transition: width 0.22s ease, box-shadow 0.22s ease, background 0.22s ease;
}
.section-title .caret {
  display: inline-block;
  margin-left: 6px;
  font-size: 0.82rem;
  color: rgba(0,240,255,0.55);
  transition: transform 0.22s ease, color 0.18s ease, text-shadow 0.18s ease;
  transform: rotate(0deg);
}
.section.collapsed .section-title .caret { transform: rotate(-90deg); }
.section.collapsed .section-body { display: none; }
.section-body {
  animation: sectionExpand 0.25s ease-out;
}
@keyframes sectionExpand {
  from { opacity: 0; transform: translateY(-4px); }
  to   { opacity: 1; transform: translateY(0); }
}

/* Upload zone */
.dropzone {
  border: 2px dashed var(--border);
  border-radius: 20px;
  padding: 52px 24px;
  text-align: center;
  background: var(--card);
  backdrop-filter: blur(20px) saturate(1.3);
  -webkit-backdrop-filter: blur(20px) saturate(1.3);
  transition: all 0.3s ease;
  cursor: pointer;
  position: relative;
  overflow: hidden;
}
.dropzone.dragover {
  border-color: var(--cyan);
  background: rgba(0, 240, 255, 0.08);
  box-shadow: 0 0 40px rgba(0,240,255,0.1), inset 0 0 30px rgba(0,240,255,0.04);
}
.dropzone .icon {
  width: 72px; height: 72px;
  margin: 0 auto 18px;
  fill: none;
  stroke: var(--cyan);
  stroke-width: 1.2;
  opacity: 0.7;
  filter: drop-shadow(0 0 8px rgba(0,240,255,0.3));
}
.dropzone h3 {
  font-size: 1.15rem;
  font-weight: 500;
  margin-bottom: 8px;
}
.dropzone p {
  color: var(--muted);
  font-size: 0.88rem;
}
input[type="file"] { display: none; }

/* Progress */
.progress-wrap {
  margin-top: 18px;
  display: none;
}
.progress-wrap.active { display: block; }
.progress-bar-bg {
  height: 6px;
  background: rgba(255,255,255,0.05);
  border-radius: 3px;
  overflow: hidden;
}
.progress-bar-fill {
  height: 100%;
  width: 0%;
  background: linear-gradient(90deg, var(--cyan), var(--purple));
  border-radius: 3px;
  transition: width 0.2s ease;
  box-shadow: 0 0 10px rgba(0,240,255,0.4);
}
.progress-text {
  text-align: center;
  font-size: 0.8rem;
  color: var(--muted);
  margin-top: 8px;
}

/* Stats bar */
.stats {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin: 20px 0 14px;
  font-size: 0.8rem;
  color: var(--muted);
}
.stats .bar-outer {
  flex: 1;
  height: 4px;
  background: rgba(255,255,255,0.05);
  border-radius: 2px;
  margin: 0 14px;
  overflow: hidden;
}
.stats .bar-inner {
  height: 100%;
  width: 0%;
  background: linear-gradient(90deg, var(--cyan), var(--purple));
  border-radius: 2px;
  transition: width 0.4s ease;
  box-shadow: 0 0 6px rgba(0,240,255,0.3);
}

/* File list */
.file-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.file-item {
  background: var(--card);
  backdrop-filter: blur(16px);
  border: 1px solid var(--border);
  border-radius: 14px;
  padding: 14px 16px;
  display: flex;
  align-items: center;
  gap: 14px;
  transition: all 0.2s ease;
  animation: slideIn 0.35s ease both;
}
.file-item:hover {
  transform: translateY(-2px);
  box-shadow: 0 6px 24px rgba(0,240,255,0.06);
  border-color: rgba(0,240,255,0.25);
}
@keyframes slideIn {
  from { opacity: 0; transform: translateY(10px); }
  to   { opacity: 1; transform: translateY(0); }
}
.file-icon {
  width: 44px; height: 44px;
  border-radius: 12px;
  background: rgba(0,240,255,0.07);
  display: flex; align-items: center; justify-content: center;
  font-size: 1.3rem;
  flex-shrink: 0;
}
.file-info {
  flex: 1;
  min-width: 0;
}
.file-name {
  font-weight: 500;
  font-size: 0.95rem;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.file-meta {
  font-size: 0.78rem;
  color: var(--muted);
}
.file-checkbox {
  width: 18px; height: 18px;
  accent-color: var(--cyan);
  cursor: pointer;
  flex-shrink: 0;
}
.batch-bar {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 10px;
  padding: 10px 14px;
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: 12px;
}
.batch-check {
  display: flex; align-items: center; gap: 6px;
  font-size: 0.88rem; cursor: pointer;
  user-select: none;
}
.btn-mini {
  padding: 5px 12px;
  font-size: 0.82rem;
}
  margin-top: 3px;
}
.file-actions {
  display: flex;
  gap: 8px;
  flex-shrink: 0;
}

/* Buttons */
.btn {
  padding: 8px 16px;
  border-radius: 10px;
  border: none;
  font-size: 0.85rem;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s;
  text-decoration: none;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
}
.btn-primary {
  background: linear-gradient(135deg, rgba(0,240,255,0.12), rgba(176,38,255,0.12));
  color: var(--cyan);
  border: 1px solid var(--border);
}
.btn-primary:hover {
  background: linear-gradient(135deg, rgba(0,240,255,0.22), rgba(176,38,255,0.22));
  box-shadow: 0 0 16px rgba(0,240,255,0.12);
  transform: translateY(-1px);
}
.btn-danger {
  background: rgba(255,56,96,0.08);
  color: var(--danger);
  border: 1px solid rgba(255,56,96,0.18);
}
.btn-danger:hover { background: rgba(255,56,96,0.18); }
.btn-glow {
  background: linear-gradient(135deg, rgba(0,240,255,0.15), rgba(176,38,255,0.15));
  color: #fff;
  border: 1px solid rgba(0,240,255,0.25);
  font-weight: 600;
  padding: 10px 28px;
  letter-spacing: 1px;
  position: relative;
  overflow: hidden;
}
.btn-glow::after {
  content: "";
  position: absolute;
  inset: 0;
  background: linear-gradient(90deg, transparent, rgba(255,255,255,0.15), transparent);
  transform: translateX(-100%);
  transition: transform 0.5s;
}
.btn-glow:hover::after { transform: translateX(100%); }
.btn-glow:hover {
  box-shadow: 0 0 24px rgba(0,240,255,0.2);
  border-color: rgba(0,240,255,0.4);
}
.btn-glow:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.empty {
  text-align: center;
  color: var(--muted);
  padding: 48px 0;
  font-size: 0.92rem;
}

/* ── Speedtest Cards ── */
.speed-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
  gap: 16px;
}
@media (max-width: 640px) {
  .speed-grid { grid-template-columns: 1fr; }
}

.speed-card {
  padding: 24px;
  text-align: center;
}
.speed-card h3 {
  font-size: 1.05rem;
  font-weight: 600;
  margin-bottom: 4px;
  letter-spacing: 1px;
}
.speed-card .subtitle {
  font-size: 0.78rem;
  color: var(--muted);
  margin-bottom: 18px;
}

/* ── Client Reachability inside Speed Card ── */
.reach-client-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px;
  text-align: left;
  margin-bottom: 16px;
  min-height: 110px;
}
.reach-client-h {
  font-size: 0.65rem;
  color: var(--muted);
  letter-spacing: 1px;
  text-transform: uppercase;
  margin-bottom: 6px;
  border-bottom: 1px solid rgba(255,255,255,0.06);
  padding-bottom: 4px;
}
.reach-client-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 5px 8px;
  border-radius: 8px;
  font-size: 0.78rem;
  transition: background 0.15s;
}
.reach-client-item:hover { background: rgba(255,255,255,0.03); }
.rc-dot {
  width: 8px; height: 8px;
  border-radius: 50%;
  background: rgba(255,255,255,0.15);
  flex-shrink: 0;
  transition: background 0.3s, box-shadow 0.3s;
}
.rc-dot.ok {
  background: #4ade80;
  box-shadow: 0 0 8px #4ade80;
}
.rc-dot.fail {
  background: var(--danger);
  box-shadow: 0 0 8px var(--danger);
}
.rc-dot.checking {
  background: var(--cyan);
  animation: reachPulse 0.9s ease-in-out infinite;
}
.rc-name { color: rgba(255,255,255,0.75); }

.speed-values {
  display: grid;
  grid-template-columns: 1fr 1fr 1fr;
  gap: 10px;
  margin-bottom: 18px;
}
.speed-val {
  background: var(--glass);
  border-radius: 12px;
  padding: 14px 6px;
  border: 1px solid rgba(255,255,255,0.04);
}
.speed-val .num {
  font-size: 1.5rem;
  font-weight: 700;
  font-family: "SF Mono", monospace;
  background: linear-gradient(180deg, #fff, var(--cyan));
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  line-height: 1.2;
}
.speed-val .num.pink {
  background: linear-gradient(180deg, #fff, var(--pink));
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
}
.speed-val .num.purple {
  background: linear-gradient(180deg, #fff, var(--purple));
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
}
.speed-val .label {
  font-size: 0.72rem;
  color: var(--muted);
  margin-top: 4px;
  letter-spacing: 0.5px;
}
.speed-pulse {
  width: 8px; height: 8px;
  border-radius: 50%;
  background: var(--cyan);
  display: inline-block;
  margin-right: 6px;
  box-shadow: 0 0 8px var(--cyan);
  animation: pulse 1.2s ease infinite;
  vertical-align: middle;
}
@keyframes pulse {
  0%, 100% { opacity: 1; transform: scale(1); }
  50% { opacity: 0.4; transform: scale(0.7); }
}

/* ── Mihomo Gateway ── */
.gw-led {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 0.75rem;
  font-family: "SF Mono", monospace;
  letter-spacing: 1px;
  color: var(--muted);
  text-transform: uppercase;
}
.gw-led .dot {
  width: 8px; height: 8px;
  border-radius: 50%;
  background: rgba(255,255,255,0.2);
  display: inline-block;
}
.gw-led.live .dot {
  background: #4ade80;
  box-shadow: 0 0 10px #4ade80;
  animation: pulse 1.5s ease infinite;
}
.gw-led.live { color: #4ade80; }
.gw-led.dead .dot { background: var(--danger); box-shadow: 0 0 10px var(--danger); }
.gw-led.dead { color: var(--danger); }

.gw-status-row {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 10px;
  margin-bottom: 14px;
}
@media (max-width: 640px) {
  .gw-status-row { grid-template-columns: repeat(2, 1fr); }
}
.gw-pill {
  background: var(--glass);
  border: 1px solid rgba(255,255,255,0.05);
  border-radius: 12px;
  padding: 12px 14px;
}
.gw-pill .label {
  font-size: 0.72rem;
  letter-spacing: 1px;
  text-transform: uppercase;
  color: var(--muted);
  margin-bottom: 4px;
}
.gw-pill .value {
  font-size: 1.05rem;
  font-weight: 600;
  font-family: "SF Mono", monospace;
  color: var(--text);
}
.gw-pill .value.cyan { color: var(--cyan); text-shadow: 0 0 8px rgba(0,240,255,0.3); }
.gw-pill .value.purple { color: var(--purple); }
.gw-pill .value.pink { color: var(--pink); }
.gw-pill .value.green { color: #4ade80; }
.gw-pill .value.red { color: var(--danger); }

.gw-card {
  padding: 18px 18px;
  margin-bottom: 14px;
}
.gw-card h4 {
  font-size: 0.95rem;
  font-weight: 600;
  margin-bottom: 12px;
  display: flex;
  align-items: center;
  gap: 8px;
}
.gw-card h4 .accent {
  width: 6px; height: 6px; border-radius: 50%;
  background: var(--cyan);
  box-shadow: 0 0 8px var(--cyan);
}

.client-row {
  display: grid;
  grid-template-columns: 22px 1fr auto auto;
  gap: 14px;
  align-items: center;
  padding: 10px 12px;
  background: rgba(255,255,255,0.02);
  border: 1px solid rgba(255,255,255,0.04);
  border-radius: 12px;
  margin-bottom: 8px;
  font-size: 0.85rem;
}
.client-row .ic { font-size: 1.05rem; opacity: 0.8; }
.client-row .ip {
  font-family: "SF Mono", monospace;
  color: var(--cyan);
  font-weight: 600;
}
.client-row .meta {
  font-size: 0.74rem;
  color: var(--muted);
  margin-top: 3px;
  font-family: "SF Mono", monospace;
}
.client-row .meta .rule { color: rgba(176,38,255,0.85); }
.client-row .meta .chain { color: rgba(0,240,255,0.7); }
.client-row .rate,
.client-row .conns {
  font-family: "SF Mono", monospace;
  font-size: 0.78rem;
  text-align: right;
  white-space: nowrap;
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.client-row .r-line {
  display: flex;
  align-items: baseline;
  justify-content: flex-end;
  gap: 6px;
}
.client-row .r-tag {
  font-size: 0.62rem;
  color: rgba(255,255,255,0.4);
  letter-spacing: 0.5px;
  font-family: -apple-system, "PingFang SC", sans-serif;
  font-weight: 500;
}
.client-row .dn { color: #4ade80; }
.client-row .up { color: var(--pink); }
.client-row .conn-num {
  margin-top: 4px;
  padding-top: 4px;
  border-top: 1px dashed rgba(255,255,255,0.08);
  font-size: 0.7rem;
  color: var(--muted);
  text-align: right;
}
.client-row .ip-line {
  display: flex;
  align-items: center;
  gap: 8px;
}
.client-row .route-badge {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 1px 8px;
  border-radius: 999px;
  font-size: 0.65rem;
  font-weight: 600;
  letter-spacing: 0.5px;
  font-family: -apple-system, "PingFang SC", sans-serif;
  border: 1px solid transparent;
  cursor: help;
}
.client-row .route-badge.direct {
  background: rgba(74,222,128,0.12);
  color: #4ade80;
  border-color: rgba(74,222,128,0.25);
}
.client-row .route-badge.proxy {
  background: rgba(176,38,255,0.12);
  color: rgba(200,120,255,0.9);
  border-color: rgba(176,38,255,0.25);
}
.client-row .meta .chain-tip {
  cursor: help;
  border-bottom: 1px dashed rgba(0,240,255,0.3);
}
.client-row .client-name {
  display: inline-flex;
  align-items: center;
  padding: 1px 8px;
  border-radius: 6px;
  font-size: 0.72rem;
  font-weight: 500;
  color: var(--cyan);
  background: rgba(0,240,255,0.08);
  border: 1px solid rgba(0,240,255,0.15);
  cursor: pointer;
  transition: all 0.15s;
  font-family: -apple-system, "PingFang SC", sans-serif;
  white-space: nowrap;
}
.client-row .client-name:hover {
  background: rgba(0,240,255,0.15);
  border-color: rgba(0,240,255,0.3);
}
.client-row .client-name.unnamed {
  color: var(--muted);
  background: transparent;
  border: 1px dashed rgba(255,255,255,0.12);
}
.client-row .client-name.unnamed:hover {
  color: var(--cyan);
  border-color: rgba(0,240,255,0.25);
}

.group-bar {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-bottom: 12px;
}
.group-chip {
  padding: 6px 12px;
  border-radius: 999px;
  background: rgba(255,255,255,0.04);
  border: 1px solid rgba(255,255,255,0.06);
  color: var(--muted);
  font-size: 0.78rem;
  cursor: pointer;
  transition: all 0.18s;
  font-family: "SF Mono", monospace;
  white-space: nowrap;
}
.group-chip:hover {
  background: rgba(0,240,255,0.08);
  color: var(--cyan);
  border-color: rgba(0,240,255,0.2);
}
.group-chip.active {
  background: linear-gradient(135deg, rgba(0,240,255,0.18), rgba(176,38,255,0.18));
  color: #fff;
  border-color: rgba(0,240,255,0.4);
  box-shadow: 0 0 12px rgba(0,240,255,0.15);
}
.group-chip .now {
  font-size: 0.68rem;
  color: var(--muted);
  margin-left: 6px;
}
.group-chip.active .now { color: rgba(255,255,255,0.7); }

.node-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(150px, 1fr));
  gap: 8px;
  max-height: 320px;
  overflow-y: auto;
  padding: 4px 4px 4px 0;
}
.node-tile {
  background: rgba(255,255,255,0.025);
  border: 1px solid rgba(255,255,255,0.06);
  border-radius: 10px;
  padding: 10px 12px;
  cursor: pointer;
  transition: all 0.18s;
  position: relative;
  overflow: hidden;
}
.node-tile:hover {
  border-color: rgba(0,240,255,0.3);
  background: rgba(0,240,255,0.04);
  transform: translateY(-1px);
}
.node-tile.selected {
  background: linear-gradient(135deg, rgba(0,240,255,0.12), rgba(176,38,255,0.12));
  border-color: rgba(0,240,255,0.5);
  box-shadow: 0 0 14px rgba(0,240,255,0.18);
}
.node-tile .nm {
  font-size: 0.78rem;
  font-weight: 500;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  color: var(--text);
}
.node-tile .dl {
  font-size: 0.72rem;
  font-family: "SF Mono", monospace;
  margin-top: 4px;
  display: flex;
  align-items: center;
  gap: 6px;
}
.node-tile .dl .dot {
  width: 6px; height: 6px; border-radius: 50%;
  display: inline-block;
}
.dl-good { color: #4ade80; }
.dl-good .dot { background: #4ade80; box-shadow: 0 0 6px #4ade80; }
.dl-mid  { color: #fbbf24; }
.dl-mid  .dot { background: #fbbf24; box-shadow: 0 0 6px #fbbf24; }
.dl-slow { color: #fb923c; }
.dl-slow .dot { background: #fb923c; box-shadow: 0 0 6px #fb923c; }
.dl-bad  { color: var(--danger); }
.dl-bad  .dot { background: var(--danger); box-shadow: 0 0 6px var(--danger); }
.dl-none { color: var(--muted); }
.dl-none .dot { background: rgba(255,255,255,0.18); }

.gw-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
  margin-bottom: 10px;
}
.gw-row label {
  font-size: 0.78rem;
  color: var(--muted);
  letter-spacing: 0.5px;
  min-width: 64px;
}
.gw-input {
  flex: 1 1 240px;
  background: rgba(255,255,255,0.03);
  border: 1px solid rgba(255,255,255,0.08);
  border-radius: 10px;
  padding: 8px 12px;
  color: var(--text);
  font-family: "SF Mono", monospace;
  font-size: 0.82rem;
  min-width: 0;
}
.gw-input:focus {
  outline: none;
  border-color: rgba(0,240,255,0.4);
  background: rgba(0,240,255,0.04);
}

.btn-mini {
  padding: 6px 12px;
  font-size: 0.78rem;
  border-radius: 8px;
}

.mode-group {
  display: inline-flex;
  background: rgba(255,255,255,0.03);
  border: 1px solid rgba(255,255,255,0.06);
  border-radius: 10px;
  padding: 3px;
}
.mode-btn {
  padding: 6px 14px;
  font-size: 0.78rem;
  border: none;
  background: transparent;
  color: var(--muted);
  cursor: pointer;
  border-radius: 7px;
  transition: all 0.15s;
  font-family: "SF Mono", monospace;
}
.mode-btn.on {
  background: linear-gradient(135deg, rgba(0,240,255,0.18), rgba(176,38,255,0.18));
  color: #fff;
}

.conn-row {
  font-family: "SF Mono", monospace;
  font-size: 0.74rem;
  padding: 6px 10px;
  border-bottom: 1px dashed rgba(255,255,255,0.04);
  display: grid;
  grid-template-columns: 110px 1fr auto;
  gap: 10px;
  align-items: center;
}
.conn-row:last-child { border-bottom: none; }
.conn-row .src { color: var(--cyan); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.conn-row .host {
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  color: var(--text);
}
.conn-row .chain {
  color: var(--muted);
  white-space: nowrap;
  font-size: 0.7rem;
  text-align: right;
}
.conn-row .chain.direct { color: #4ade80; }

.gw-error {
  background: rgba(255,56,96,0.08);
  border: 1px solid rgba(255,56,96,0.2);
  color: var(--danger);
  padding: 12px 16px;
  border-radius: 12px;
  font-size: 0.85rem;
  text-align: center;
}

.gw-muted-hint {
  color: var(--muted);
  font-size: 0.78rem;
  margin-top: 6px;
}

/* Toast */
.toast {
  position: fixed;
  bottom: 28px;
  left: 50%;
  transform: translateX(-50%) translateY(80px);
  background: var(--card);
  backdrop-filter: blur(20px);
  border: 1px solid var(--border);
  color: var(--text);
  padding: 14px 26px;
  border-radius: 12px;
  font-size: 0.88rem;
  z-index: 100;
  opacity: 0;
  transition: all 0.4s ease;
  pointer-events: none;
  box-shadow: 0 8px 32px rgba(0,0,0,0.4);
}
.toast.show {
  transform: translateX(-50%) translateY(0);
  opacity: 1;
}

/* Reachability */
.reach-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 14px;
}
.reach-col h4 {
  font-size: 0.95rem;
  font-weight: 600;
  margin-bottom: 12px;
  display: flex;
  align-items: center;
  gap: 8px;
}
.reach-col h4 .accent {
  width: 6px; height: 6px; border-radius: 50%;
  background: var(--cyan);
  box-shadow: 0 0 8px var(--cyan);
}
.reach-col.intl h4 .accent { background: var(--purple); box-shadow: 0 0 8px var(--purple); }
.reach-tile {
  display: grid;
  grid-template-columns: 28px 1fr auto;
  align-items: center;
  gap: 10px;
  padding: 10px 12px;
  background: rgba(255,255,255,0.02);
  border: 1px solid rgba(255,255,255,0.04);
  border-radius: 12px;
  margin-bottom: 8px;
  font-size: 0.85rem;
  cursor: pointer;
  transition: all 0.18s;
}
.reach-tile:hover {
  background: rgba(255,255,255,0.04);
  border-color: rgba(0,240,255,0.18);
}
.reach-tile.checking {
  border-color: rgba(0,240,255,0.35);
  background: rgba(0,240,255,0.04);
}
.reach-tile .ricon { font-size: 1.05rem; opacity: 0.85; text-align: center; }
.reach-tile .rname { font-weight: 600; letter-spacing: 0.3px; }
.reach-tile .rmeta {
  font-family: "SF Mono", monospace;
  font-size: 0.72rem;
  color: var(--muted);
  margin-top: 2px;
  letter-spacing: 0.2px;
}
.reach-tile .rstatus {
  display: flex;
  align-items: center;
  gap: 6px;
  font-family: "SF Mono", monospace;
  font-size: 0.72rem;
  white-space: nowrap;
}
.reach-tile .rdot {
  width: 8px; height: 8px; border-radius: 50%;
  background: rgba(255,255,255,0.2);
  box-shadow: 0 0 6px rgba(255,255,255,0.1);
}
.reach-tile.ok   .rdot { background: #4ade80; box-shadow: 0 0 8px #4ade80; }
.reach-tile.warn .rdot { background: #fbbf24; box-shadow: 0 0 8px #fbbf24; }
.reach-tile.fail .rdot { background: var(--danger); box-shadow: 0 0 8px var(--danger); }
.reach-tile.ok   .rstatus { color: #4ade80; }
.reach-tile.warn .rstatus { color: #fbbf24; }
.reach-tile.fail .rstatus { color: var(--danger); }
.reach-tile.checking .rdot {
  background: var(--cyan);
  box-shadow: 0 0 8px var(--cyan);
  animation: reachPulse 0.9s ease-in-out infinite;
}
@keyframes reachPulse {
  0%, 100% { opacity: 0.4; transform: scale(0.85); }
  50%      { opacity: 1;   transform: scale(1.15); }
}
.reach-actions {
  display: flex;
  justify-content: flex-end;
  margin-bottom: 12px;
}
.reach-btn {
  background: linear-gradient(135deg, rgba(0,240,255,0.12), rgba(176,38,255,0.12));
  border: 1px solid rgba(0,240,255,0.3);
  color: var(--text);
  padding: 6px 14px;
  border-radius: 999px;
  font-size: 0.78rem;
  cursor: pointer;
  transition: all 0.2s;
  font-family: "SF Mono", monospace;
  letter-spacing: 0.3px;
}
.reach-btn:hover {
  background: linear-gradient(135deg, rgba(0,240,255,0.22), rgba(176,38,255,0.22));
  border-color: rgba(0,240,255,0.55);
}
.reach-btn:disabled { opacity: 0.5; cursor: wait; }

/* System status bar */
.sysbar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 10px;
  margin: 0 0 18px 0;
  padding: 12px 18px;
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: 16px;
  backdrop-filter: blur(12px);
  position: relative;
}
.sysbar::before {
  content: "";
  position: absolute;
  left: 18px; right: 18px; top: 0;
  height: 1px;
  background: linear-gradient(90deg, transparent, rgba(0,240,255,0.35), rgba(176,38,255,0.3), transparent);
}
.sys-chip {
  display: flex;
  align-items: center;
  gap: 9px;
  padding: 6px 14px;
  background: rgba(255,255,255,0.025);
  border: 1px solid rgba(255,255,255,0.05);
  border-radius: 999px;
  transition: all 0.18s;
  white-space: nowrap;
}
.sys-chip:hover {
  background: rgba(255,255,255,0.05);
  border-color: rgba(0,240,255,0.18);
  transform: translateY(-1px);
}
.sys-chip .icon { font-size: 1.05rem; opacity: 0.85; }
.sys-chip .stack { display: flex; flex-direction: column; gap: 0; line-height: 1.15; }
.sys-chip .label {
  font-size: 0.6rem;
  color: var(--muted);
  letter-spacing: 0.6px;
  text-transform: uppercase;
  font-family: -apple-system, "PingFang SC", sans-serif;
}
.sys-chip .value {
  font-size: 0.86rem;
  font-weight: 600;
  letter-spacing: 0.3px;
  font-family: "SF Mono", monospace;
}
.sys-chip.neutral .value { color: var(--cyan); }
.sys-chip.cool    .value { color: #4ade80; }
.sys-chip.warm    .value { color: #fbbf24; }
.sys-chip.hot     .value { color: var(--danger); }
.sys-chip.cool { border-color: rgba(74,222,128,0.18); }
.sys-chip.warm { border-color: rgba(251,191,36,0.25); }
.sys-chip.hot  { border-color: rgba(255,56,96,0.35); box-shadow: 0 0 12px rgba(255,56,96,0.18); }

.sys-warn {
  display: none;
  font-size: 0.7rem;
  color: var(--danger);
  letter-spacing: 0.3px;
  padding: 5px 12px;
  border: 1px solid rgba(255,56,96,0.4);
  background: rgba(255,56,96,0.08);
  border-radius: 999px;
  font-family: "SF Mono", monospace;
}
.sys-warn.show { display: inline-flex; align-items: center; gap: 6px; }

.sys-meta {
  margin-left: auto;
  color: rgba(255,255,255,0.32);
  font-size: 0.68rem;
  letter-spacing: 0.4px;
  font-family: "SF Mono", monospace;
}
.sys-refresh {
  background: transparent;
  border: 1px solid rgba(255,255,255,0.1);
  color: rgba(255,255,255,0.5);
  width: 30px; height: 30px;
  border-radius: 999px;
  cursor: pointer;
  font-size: 0.92rem;
  display: flex; align-items: center; justify-content: center;
  transition: color 0.2s, border-color 0.2s;
}
.sys-refresh:hover {
  border-color: rgba(0,240,255,0.5);
  color: var(--cyan);
}
.sys-refresh.spin { animation: sysSpin 0.6s linear; }
@keyframes sysSpin {
  from { transform: rotate(0); }
  to   { transform: rotate(360deg); }
}

/* Phone setup card (ph-) — info display + manual config guide */
.ph-info-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 10px;
  margin-bottom: 14px;
}
.ph-info-item {
  background: rgba(255,255,255,0.03);
  border: 1px solid rgba(0,240,255,0.1);
  border-radius: 12px;
  padding: 12px 14px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.ph-info-item .label {
  font-size: 0.7rem;
  color: var(--muted);
  letter-spacing: 0.6px;
  text-transform: uppercase;
}
.ph-info-item .row { display: flex; align-items: center; gap: 8px; }
.ph-info-item .value {
  flex: 1;
  font-family: "SF Mono", monospace;
  font-size: 0.95rem;
  color: var(--cyan);
  text-shadow: 0 0 8px rgba(0,240,255,0.25);
  word-break: break-all;
}
.ph-copy {
  background: rgba(0,240,255,0.08);
  border: 1px solid rgba(0,240,255,0.2);
  color: var(--cyan);
  font-size: 0.72rem;
  font-family: "SF Mono", monospace;
  padding: 4px 10px;
  border-radius: 6px;
  cursor: pointer;
  transition: all 0.15s;
  flex-shrink: 0;
}
.ph-copy:hover { background: rgba(0,240,255,0.15); border-color: rgba(0,240,255,0.4); }
.ph-copy.ok {
  background: rgba(74,222,128,0.15);
  border-color: rgba(74,222,128,0.4);
  color: #4ade80;
}
.ph-tabs {
  display: inline-flex;
  background: rgba(255,255,255,0.03);
  border: 1px solid rgba(255,255,255,0.06);
  border-radius: 10px;
  padding: 3px;
  margin-bottom: 12px;
}
.ph-tab {
  padding: 6px 18px;
  font-size: 0.8rem;
  border: none;
  background: transparent;
  color: var(--muted);
  cursor: pointer;
  border-radius: 7px;
  transition: all 0.15s;
  font-family: "SF Mono", monospace;
  letter-spacing: 0.5px;
}
.ph-tab.on {
  background: linear-gradient(135deg, rgba(0,240,255,0.18), rgba(176,38,255,0.18));
  color: #fff;
}
.ph-pane { display: none; }
.ph-pane.on { display: block; }
.ph-method {
  background: rgba(255,255,255,0.02);
  border: 1px solid rgba(255,255,255,0.06);
  border-radius: 12px;
  padding: 12px 14px;
  margin-bottom: 10px;
}
.ph-method-h {
  display: flex; align-items: baseline; gap: 8px; margin-bottom: 8px; flex-wrap: wrap;
}
.ph-method-h .badge {
  font-size: 0.66rem;
  padding: 2px 8px;
  border-radius: 4px;
  background: rgba(0,240,255,0.12);
  color: var(--cyan);
  letter-spacing: 0.5px;
}
.ph-method-h .name { font-size: 0.88rem; color: var(--text); font-weight: 500; }
.ph-method-h .sub { font-size: 0.74rem; color: var(--muted); margin-left: auto; }
.ph-steps { list-style: none; counter-reset: phstep; padding: 0; margin: 0; }
.ph-steps li {
  counter-increment: phstep;
  position: relative;
  padding: 4px 0 4px 28px;
  font-size: 0.84rem;
  color: var(--text);
  line-height: 1.55;
}
.ph-steps li::before {
  content: counter(phstep);
  position: absolute; left: 0; top: 4px;
  width: 20px; height: 20px;
  border-radius: 50%;
  background: rgba(0,240,255,0.12);
  border: 1px solid rgba(0,240,255,0.25);
  color: var(--cyan);
  font-size: 0.7rem;
  font-family: "SF Mono", monospace;
  display: flex; align-items: center; justify-content: center; line-height: 1;
}
.ph-steps li code {
  background: rgba(0,240,255,0.08);
  border: 1px solid rgba(0,240,255,0.15);
  border-radius: 4px;
  padding: 1px 5px;
  font-size: 0.78rem;
  color: var(--cyan);
  font-family: "SF Mono", monospace;
}
.ph-note {
  margin-top: 10px;
  padding: 10px 12px;
  border-radius: 10px;
  background: rgba(176,38,255,0.06);
  border: 1px solid rgba(176,38,255,0.18);
  font-size: 0.78rem;
  color: var(--muted);
  line-height: 1.55;
}
.ph-note strong { color: var(--purple); }

/* Responsive */
@media (max-width: 520px) {
  .header h1 { font-size: 1.6rem; letter-spacing: 2px; }
  .dropzone { padding: 36px 16px; }
  .file-item { flex-wrap: wrap; }
  .file-actions { width: 100%; justify-content: flex-end; margin-top: 6px; }
  .speed-values { grid-template-columns: 1fr; }
  .reach-grid { grid-template-columns: 1fr; }
  .sysbar { padding: 10px 12px; gap: 8px; }
  .sys-chip { padding: 5px 11px; gap: 7px; }
  .sys-chip .label { font-size: 0.55rem; }
  .sys-chip .value { font-size: 0.78rem; }
  .sys-meta { display: none; }
}

/* ── Photo Cleaner ── */
.photo-controls {
  display: flex;
  flex-wrap: wrap;
  gap: 16px;
  align-items: center;
  margin-bottom: 14px;
}
.photo-label {
  color: var(--muted);
  font-size: 0.85rem;
  display: inline-flex;
  align-items: center;
  gap: 8px;
}
.photo-label select {
  background: var(--bg1);
  color: var(--text);
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 5px 10px;
  font-size: 0.85rem;
  font-family: inherit;
  cursor: pointer;
  min-width: 200px;
}
.photo-label select:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
.photo-tabs {
  display: flex;
  gap: 6px;
  margin-left: auto;
}
.photo-tab {
  padding: 6px 14px;
  background: var(--glass);
  border: 1px solid var(--border);
  border-radius: 6px;
  color: var(--muted);
  cursor: pointer;
  font-size: 0.85rem;
  font-family: inherit;
  transition: all 0.18s;
}
.photo-tab:hover { color: var(--cyan); }
.photo-tab.active {
  border-color: var(--cyan);
  color: var(--cyan);
  background: rgba(0,240,255,0.06);
  box-shadow: 0 0 10px rgba(0,240,255,0.18);
}
.photo-dropzone {
  padding: 28px 16px;
  text-align: center;
  cursor: pointer;
}
.photo-workspace {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 14px;
  margin: 14px 0;
}
@media (max-width: 720px) {
  .photo-workspace { grid-template-columns: 1fr; }
}
.photo-pane-title {
  color: var(--muted);
  font-size: 0.82rem;
  margin-bottom: 6px;
  display: flex;
  align-items: center;
}
.photo-canvas-wrap {
  position: relative;
  border: 1px solid var(--border);
  border-radius: 10px;
  overflow: hidden;
  background: var(--bg1);
  min-height: 160px;
}
.photo-src-img {
  display: block;
  width: 100%;
  height: auto;
  user-select: none;
  -webkit-user-drag: none;
}
.photo-mask-canvas {
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  cursor: crosshair;
  touch-action: none;
}
.photo-result-wrap {
  border: 1px solid var(--border);
  border-radius: 10px;
  min-height: 160px;
  background: var(--bg1);
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
}
.photo-result-wrap img {
  display: block;
  max-width: 100%;
  height: auto;
}
.photo-placeholder {
  color: var(--muted);
  padding: 32px 20px;
  text-align: center;
  font-size: 0.88rem;
}
.photo-mask-tools {
  display: flex;
  gap: 14px;
  align-items: center;
  flex-wrap: wrap;
  margin: 10px 0;
  color: var(--muted);
  font-size: 0.82rem;
}
.photo-mask-tools label {
  display: inline-flex;
  align-items: center;
  gap: 8px;
}
.photo-mask-tools input[type=range] {
  width: 130px;
  accent-color: var(--cyan);
}
.photo-prompt-wrap { margin: 12px 0; }
.photo-prompt {
  width: 100%;
  padding: 9px 13px;
  background: var(--bg1);
  border: 1px solid var(--border);
  border-radius: 8px;
  color: var(--text);
  font-size: 0.88rem;
  font-family: inherit;
  box-sizing: border-box;
  outline: none;
  transition: border-color 0.2s;
}
.photo-prompt:focus { border-color: var(--cyan); }
.photo-step { font-size: 0.9rem; color: var(--cyan); margin-bottom: 4px; }
.photo-step-time { font-size: 0.78rem; color: var(--muted); }
.photo-presets {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  margin-top: 8px;
}
.preset-btn {
  padding: 4px 10px;
  font-size: 0.78rem;
  background: var(--bg1);
  border: 1px solid var(--border);
  color: var(--muted);
  border-radius: 6px;
  cursor: pointer;
  transition: all 0.15s;
}
.preset-btn:hover {
  border-color: var(--cyan);
  color: var(--cyan);
}
.photo-actions {
  display: flex;
  gap: 12px;
  align-items: center;
  flex-wrap: wrap;
  margin-top: 6px;
}
.photo-noprovider {
  color: var(--danger);
  background: rgba(255,56,96,0.05);
  padding: 14px 16px;
  border: 1px dashed rgba(255,56,96,0.35);
  border-radius: 10px;
  font-size: 0.88rem;
  margin-bottom: 14px;
  line-height: 1.6;
}
.photo-noprovider code {
  background: rgba(0,240,255,0.06);
  padding: 1px 6px;
  border-radius: 4px;
  color: var(--cyan);
  font-size: 0.82rem;
}

/* ── Process Monitor ── */
.mon-toolbar {
  display: flex;
  gap: 10px;
  align-items: center;
  flex-wrap: wrap;
  margin-bottom: 14px;
}
.mon-search {
  flex: 1;
  min-width: 160px;
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 8px 14px;
  color: var(--text);
  font-size: 0.85rem;
  outline: none;
}
.mon-search:focus { border-color: var(--cyan); box-shadow: 0 0 12px rgba(0,240,255,0.08); }
.mon-search::placeholder { color: var(--muted); }
.mon-badge {
  font-size: 0.7rem;
  padding: 3px 8px;
  border-radius: 6px;
  font-weight: 600;
  letter-spacing: 0.5px;
}
.mon-badge.daemon {
  background: rgba(0,240,255,0.1);
  color: var(--cyan);
  border: 1px solid rgba(0,240,255,0.18);
}
.mon-badge.restart {
  background: rgba(251,191,36,0.1);
  color: #fbbf24;
  border: 1px solid rgba(251,191,36,0.2);
}
.mon-badge.user {
  background: rgba(138,148,168,0.08);
  color: var(--muted);
  border: 1px solid rgba(138,148,168,0.12);
}

.mon-table-wrap {
  overflow-x: auto;
  border-radius: 14px;
  border: 1px solid var(--border);
  background: var(--card);
  backdrop-filter: blur(16px);
}
.mon-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.82rem;
}
.mon-table thead {
  position: sticky;
  top: 0;
  background: rgba(12,20,40,0.85);
  backdrop-filter: blur(12px);
  z-index: 2;
}
.mon-table th {
  padding: 10px 12px;
  text-align: left;
  font-weight: 600;
  color: var(--muted);
  font-size: 0.72rem;
  letter-spacing: 0.8px;
  text-transform: uppercase;
  cursor: pointer;
  user-select: none;
  white-space: nowrap;
  border-bottom: 1px solid var(--border);
}
.mon-table th:hover { color: var(--cyan); }
.mon-table th .sort-arrow {
  margin-left: 4px;
  opacity: 0.4;
  font-size: 0.65rem;
}
.mon-table th.sort-asc .sort-arrow,
.mon-table th.sort-desc .sort-arrow { opacity: 1; color: var(--cyan); }
.mon-table td {
  padding: 9px 12px;
  border-bottom: 1px solid rgba(255,255,255,0.03);
  vertical-align: middle;
  white-space: nowrap;
}
.mon-table tbody tr:hover { background: rgba(0,240,255,0.03); }
.mon-table tbody tr:last-child td { border-bottom: none; }
.mon-table .col-pid { width: 50px; color: var(--cyan); font-family: monospace; font-size: 0.78rem; }
.mon-table .col-name { max-width: 160px; overflow: hidden; text-overflow: ellipsis; }
.mon-table .col-cpu { width: 60px; text-align: right; font-family: monospace; }
.mon-table .col-mem { width: 80px; text-align: right; font-family: monospace; }
.mon-table .col-runtime { width: 80px; text-align: right; font-family: monospace; font-size: 0.78rem; }
.mon-table .col-cmd {
  max-width: 300px;
  overflow: hidden;
  text-overflow: ellipsis;
  color: var(--muted);
  font-size: 0.75rem;
  font-family: "SF Mono", "Cascadia Mono", monospace;
}
.mon-table .col-daemon { width: 100px; }
.mon-table .col-act { width: 50px; text-align: center; }
.mon-kill-btn {
  background: rgba(255,56,96,0.08);
  color: var(--danger);
  border: 1px solid rgba(255,56,96,0.18);
  border-radius: 8px;
  padding: 4px 10px;
  font-size: 0.72rem;
  cursor: pointer;
  transition: all 0.15s;
}
.mon-kill-btn:hover { background: rgba(255,56,96,0.2); }
.mon-kill-btn:disabled { opacity: 0.3; cursor: not-allowed; }
.mon-empty {
  text-align: center;
  padding: 40px;
  color: var(--muted);
  font-size: 0.9rem;
}
.mon-summary {
  display: flex;
  gap: 16px;
  flex-wrap: wrap;
  margin-bottom: 14px;
  font-size: 0.78rem;
  color: var(--muted);
}
.mon-summary span { display: flex; align-items: center; gap: 4px; }
.mon-summary .dot { width: 7px; height: 7px; border-radius: 50%; display: inline-block; }
.mon-summary .dot.daemon { background: var(--cyan); box-shadow: 0 0 6px rgba(0,240,255,0.4); }
.mon-summary .dot.restart { background: #fbbf24; box-shadow: 0 0 6px rgba(251,191,36,0.4); }
.mon-summary .dot.total { background: var(--muted); }

@media (max-width: 640px) {
  .mon-table .col-cmd { max-width: 120px; }
  .mon-table .col-name { max-width: 100px; }
  .mon-table th, .mon-table td { padding: 7px 8px; font-size: 0.75rem; }
}

/* ── PC Console ── */
.pc-card {
  padding: 20px 22px;
  background: var(--card);
  backdrop-filter: blur(16px);
  border: 1px solid var(--border);
  border-radius: 16px;
  margin-bottom: 14px;
}
.pc-main {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  flex-wrap: wrap;
}
.pc-info {
  display: flex;
  align-items: center;
  gap: 14px;
}
.pc-icon {
  width: 52px; height: 52px;
  border-radius: 14px;
  background: rgba(0,240,255,0.08);
  display: flex; align-items: center; justify-content: center;
  font-size: 1.6rem;
  flex-shrink: 0;
  transition: all 0.3s;
}
.pc-icon.online {
  background: rgba(74,222,128,0.1);
  box-shadow: 0 0 16px rgba(74,222,128,0.15);
}
.pc-icon.offline {
  background: rgba(255,56,96,0.08);
  filter: grayscale(0.6);
}
.pc-meta { display: flex; flex-direction: column; gap: 2px; }
.pc-name {
  font-size: 1.05rem;
  font-weight: 600;
  color: var(--text);
  letter-spacing: 0.5px;
}
.pc-ip {
  font-family: "SF Mono", monospace;
  font-size: 0.82rem;
  color: var(--cyan);
  letter-spacing: 0.5px;
}
.pc-mac {
  font-family: "SF Mono", monospace;
  font-size: 0.75rem;
  color: var(--muted);
  letter-spacing: 0.5px;
}
.pc-rtt {
  font-family: "SF Mono", monospace;
  font-size: 0.85rem;
  color: var(--muted);
  background: rgba(255,255,255,0.03);
  border: 1px solid rgba(255,255,255,0.06);
  padding: 6px 14px;
  border-radius: 999px;
}
.pc-rtt.online {
  color: #4ade80;
  border-color: rgba(74,222,128,0.2);
  background: rgba(74,222,128,0.06);
}
.pc-actions {
  display: flex;
  gap: 12px;
  margin-top: 16px;
}
.pc-actions .btn {
  flex: 1;
  justify-content: center;
  padding: 10px 20px;
}
.pc-actions .btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
  transform: none !important;
}

/* PC status LED in section title */
.pc-led {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 0.75rem;
  font-family: "SF Mono", monospace;
  letter-spacing: 1px;
  color: var(--muted);
  text-transform: uppercase;
}
.pc-led .dot {
  width: 8px; height: 8px;
  border-radius: 50%;
  background: rgba(255,255,255,0.2);
  display: inline-block;
}
.pc-led.online .dot {
  background: #4ade80;
  box-shadow: 0 0 10px #4ade80;
  animation: pulse 1.5s ease infinite;
}
.pc-led.online { color: #4ade80; }
.pc-led.offline .dot { background: var(--danger); box-shadow: 0 0 10px var(--danger); }
.pc-led.offline { color: var(--danger); }

/* PC help panel */
.pc-help {
  background: rgba(255,255,255,0.02);
  border: 1px solid rgba(255,255,255,0.06);
  border-radius: 12px;
  overflow: hidden;
}
.pc-help-toggle {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px;
  font-size: 0.85rem;
  color: var(--muted);
  cursor: pointer;
  transition: all 0.2s;
  user-select: none;
}
.pc-help-toggle:hover { color: var(--cyan); }
.pc-help-toggle .caret {
  font-size: 0.82rem;
  transition: transform 0.22s;
}
.pc-help.collapsed .caret { transform: rotate(-90deg); }
.pc-help.collapsed .pc-help-body { display: none; }
.pc-help-body {
  padding: 4px 16px 16px;
  animation: sectionExpand 0.25s ease-out;
}
.pc-help-step {
  display: flex;
  gap: 12px;
  margin-bottom: 12px;
}
.pc-help-num {
  width: 26px; height: 26px;
  border-radius: 50%;
  background: rgba(0,240,255,0.12);
  border: 1px solid rgba(0,240,255,0.25);
  color: var(--cyan);
  font-size: 0.78rem;
  font-weight: 600;
  font-family: "SF Mono", monospace;
  display: flex; align-items: center; justify-content: center;
  flex-shrink: 0;
}
.pc-help-content {
  flex: 1;
  font-size: 0.84rem;
  color: var(--text);
  line-height: 1.5;
}
.pc-help-content strong { color: var(--cyan); font-weight: 500; }
.pc-help-content pre {
  margin-top: 6px;
  background: rgba(0,0,0,0.3);
  border: 1px solid rgba(255,255,255,0.06);
  border-radius: 8px;
  padding: 10px 12px;
  overflow-x: auto;
}
.pc-help-content code {
  font-family: "SF Mono", "Cascadia Mono", monospace;
  font-size: 0.78rem;
  color: var(--cyan);
  white-space: pre-wrap;
  word-break: break-all;
}
.pc-help-note {
  margin-top: 10px;
  padding: 10px 12px;
  border-radius: 8px;
  background: rgba(251,191,36,0.06);
  border: 1px solid rgba(251,191,36,0.15);
  font-size: 0.8rem;
  color: var(--muted);
  line-height: 1.5;
}
.pc-help-note code {
  background: rgba(0,240,255,0.08);
  border: 1px solid rgba(0,240,255,0.15);
  border-radius: 4px;
  padding: 1px 5px;
  font-size: 0.78rem;
  color: var(--cyan);
  font-family: "SF Mono", monospace;
}

/* ── Daily News ── */
.news-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.news-item {
  background: var(--card);
  backdrop-filter: blur(16px);
  border: 1px solid var(--border);
  border-radius: 14px;
  padding: 14px 16px;
  display: flex;
  align-items: center;
  gap: 14px;
  transition: all 0.2s ease;
}
.news-item:hover {
  transform: translateY(-2px);
  box-shadow: 0 6px 24px rgba(0,240,255,0.06);
  border-color: rgba(0,240,255,0.25);
}
.news-info {
  flex: 1;
  min-width: 0;
}
.news-title {
  font-weight: 500;
  font-size: 0.95rem;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.news-meta {
  font-size: 0.78rem;
  color: var(--muted);
  margin-top: 4px;
}
.news-actions {
  display: flex;
  gap: 8px;
  flex-shrink: 0;
}

/* ── Storage File Manager ── */
.storage-bar {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 14px;
  padding: 10px 14px;
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: 12px;
  flex-wrap: wrap;
}
.storage-bar .usage-label { font-size: 0.78rem; color: var(--muted); }
.storage-bar .usage-val { font-size: 0.85rem; color: var(--cyan); font-family: monospace; }
.storage-bar .bar-outer {
  flex: 1; min-width: 80px; height: 6px;
  background: rgba(255,255,255,0.06);
  border-radius: 3px; overflow: hidden;
}
.storage-bar .bar-inner {
  height: 100%;
  background: linear-gradient(90deg, var(--cyan), var(--purple));
  border-radius: 3px;
  transition: width 0.3s ease;
}
.storage-breadcrumb {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 12px;
  font-size: 0.85rem;
  flex-wrap: wrap;
}
.storage-breadcrumb .crumb {
  color: var(--cyan);
  cursor: pointer;
  padding: 2px 6px;
  border-radius: 6px;
  transition: background 0.15s;
}
.storage-breadcrumb .crumb:hover { background: rgba(0,240,255,0.08); }
.storage-breadcrumb .sep { color: var(--muted); font-size: 0.7rem; }
.storage-breadcrumb .crumb:last-child { color: var(--text); cursor: default; }
.storage-breadcrumb .crumb:last-child:hover { background: transparent; }
.storage-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.storage-item {
  background: var(--card);
  backdrop-filter: blur(16px);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 11px 14px;
  display: flex;
  align-items: center;
  gap: 12px;
  transition: all 0.2s ease;
  cursor: pointer;
}
.storage-item:hover {
  transform: translateY(-1px);
  box-shadow: 0 4px 16px rgba(0,240,255,0.05);
  border-color: rgba(0,240,255,0.2);
}
.storage-item .s-icon {
  width: 36px; height: 36px;
  border-radius: 10px;
  background: rgba(0,240,255,0.06);
  display: flex; align-items: center; justify-content: center;
  font-size: 1.1rem;
  flex-shrink: 0;
}
.storage-item .s-icon.folder { background: rgba(251,191,36,0.08); }
.storage-item .s-info { flex: 1; min-width: 0; }
.storage-item .s-name {
  font-weight: 500; font-size: 0.9rem;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.storage-item .s-meta {
  font-size: 0.75rem; color: var(--muted);
  margin-top: 2px;
}
.storage-item .s-actions {
  display: flex; gap: 6px; flex-shrink: 0;
}
.storage-empty {
  text-align: center; padding: 36px; color: var(--muted); font-size: 0.9rem;
}
.storage-dropzone {
  border: 2px dashed var(--border);
  border-radius: 14px;
  padding: 28px 16px;
  text-align: center;
  background: var(--card);
  transition: all 0.25s ease;
  cursor: pointer;
  margin-bottom: 14px;
}
.storage-dropzone.dragover {
  border-color: var(--cyan);
  background: rgba(0,240,255,0.06);
}
.storage-dropzone .s-dz-icon {
  font-size: 1.6rem; margin-bottom: 6px; opacity: 0.7;
}
.storage-dropzone p {
  font-size: 0.85rem; color: var(--muted); margin: 0;
}
</style>
</head>
<body>
<canvas id="universe"></canvas>
<div class="orb orb1"></div>
<div class="orb orb2"></div>
<div class="orb orb3"></div>

<div class="container">
  <div class="header">
    <h1>NEBULA<span class="dot-sep">·</span><span class="brand-aw">AW</span></h1>
    <p class="brand-sub">家中网络的管家与中枢 <span class="brand-en">/ Home Network Steward</span></p>
    <p class="quote" id="quote">&nbsp;</p>
  </div>

  <!-- System status bar -->
  <div class="sysbar" id="sysbar">
    <div class="sys-chip neutral" id="chipTemp">
      <span class="icon">🌡</span>
      <div class="stack"><div class="label">温度</div><div class="value">--</div></div>
    </div>
    <div class="sys-chip neutral" id="chipCpu">
      <span class="icon">⚡</span>
      <div class="stack"><div class="label">CPU</div><div class="value">--</div></div>
    </div>
    <div class="sys-chip neutral" id="chipMem">
      <span class="icon">▦</span>
      <div class="stack"><div class="label">内存</div><div class="value">--</div></div>
    </div>
    <div class="sys-chip neutral" id="chipDisk">
      <span class="icon">◇</span>
      <div class="stack"><div class="label">磁盘</div><div class="value">--</div></div>
    </div>
    <div class="sys-chip neutral" id="chipUptime">
      <span class="icon">⏱</span>
      <div class="stack"><div class="label">运行</div><div class="value">--</div></div>
    </div>
    <div class="sys-chip neutral" id="chipHdd" style="display:none">
      <span class="icon">💾</span>
      <div class="stack"><div class="label">硬盘</div><div class="value">--</div></div>
    </div>
    <span class="sys-warn" id="sysWarn"></span>
    <span class="sys-meta" id="sysMeta"></span>
    <button class="sys-refresh" id="sysRefresh" onclick="refreshSysNow()" title="立即刷新">↻</button>
  </div>

  <!-- PC Console Section -->
  <div class="section" id="secWol">
    <div class="section-title" onclick="toggleSection('wol')">
      <span>PC控制台 · Remote Control</span>
      <span style="margin-left:auto;display:flex;align-items:center;gap:10px">
        <span class="pc-led" id="pcLed"><span class="dot"></span><span id="pcLedText">检测中...</span></span>
      </span>
    </div>
    <div class="section-body">
      <div class="pc-card">
        <div class="pc-main">
          <div class="pc-info">
            <div class="pc-icon" id="pcIcon">🖥</div>
            <div class="pc-meta">
              <div class="pc-name" id="pcName">{{PC_NAME}}</div>
              <div class="pc-ip" id="pcIp">{{PC_IP}}</div>
              <div class="pc-mac" id="pcMac">{{PC_MAC}}</div>
            </div>
          </div>
          <div class="pc-rtt" id="pcRtt">--</div>
        </div>
        <div class="pc-actions">
          <button class="btn btn-glow" id="btnWol" onclick="sendWol()">
            <span id="wolPulse" style="display:none" class="speed-pulse"></span>唤醒 PC
          </button>
          <button class="btn btn-danger" id="btnShutdown" onclick="sendShutdown()" style="background:rgba(255,56,96,0.08);color:var(--danger);border:1px solid rgba(255,56,96,0.18);">
            <span id="shutdownPulse" style="display:none" class="speed-pulse"></span>关闭 PC
          </button>
        </div>
      </div>

      <div class="pc-help" id="pcHelp">
        <div class="pc-help-toggle" onclick="togglePcHelp()">
          <span>⚙ Windows OpenSSH 配置引导</span>
          <span class="caret" id="pcHelpCaret">▾</span>
        </div>
        <div class="pc-help-body" id="pcHelpBody">
          <div class="pc-help-step">
            <div class="pc-help-num">1</div>
            <div class="pc-help-content">
              <strong>在 Windows PC 上以管理员身份打开 PowerShell，执行：</strong>
              <pre><code>Add-WindowsCapability -Online -Name OpenSSH.Server~~~~0.0.1.0
Start-Service sshd
Set-Service -Name sshd -StartupType 'Automatic'
New-NetFirewallRule -Name sshd -DisplayName 'OpenSSH Server' -Enabled True -Direction Inbound -Protocol TCP -Action Allow -LocalPort 22</code></pre>
            </div>
          </div>
          <div class="pc-help-step">
            <div class="pc-help-num">2</div>
            <div class="pc-help-content">
              <strong>在树莓派上生成 SSH 密钥并复制到 PC：</strong>
              <pre><code>ssh-keygen -t ed25519 -C "nebulashare" -f ~/.ssh/nebulashare
ssh-copy-id -i ~/.ssh/nebulashare.pub {{PC_SSH_USER}}@{{PC_IP}}</code></pre>
            </div>
          </div>
          <div class="pc-help-step">
            <div class="pc-help-num">3</div>
            <div class="pc-help-content">
              <strong>在树莓派上设置环境变量（~/.bashrc 或 ~/.profile）：</strong>
              <pre><code>export PC_SSH_KEY="$HOME/.ssh/nebulashare"
export PC_SSH_USER="{{PC_SSH_USER}}"</code></pre>
            </div>
          </div>
          <div class="pc-help-note">
            <strong>提示：</strong>如果你使用密码登录而非密钥，请在 PC 上先手动执行一次 <code>ssh {{PC_SSH_USER}}@{{PC_IP}}</code> 并接受主机密钥。
          </div>
        </div>
      </div>
    </div>
  </div>

  <!-- Process Monitor Section -->
  <div class="section" id="secMonitor">
    <div class="section-title" onclick="toggleSection('monitor')">
      <span>进程监控 · Task Manager</span>
      <span class="caret">▾</span>
    </div>
    <div class="section-body">
      <div class="mon-summary" id="monSummary">
        <span><span class="dot daemon"></span> 守护进程</span>
        <span><span class="dot restart"></span> 自动拉起</span>
        <span><span class="dot total"></span> 总进程 <strong id="monTotal">--</strong></span>
      </div>
      <div class="mon-toolbar">
        <input type="text" class="mon-search" id="monSearch" placeholder="搜索进程名 / PID / 命令行..." oninput="filterMonProcesses()">
        <button class="btn btn-primary btn-mini" id="monRefreshBtn" onclick="refreshMonNow()">
          <span id="monPulse" style="display:none" class="speed-pulse"></span>刷新
        </button>
      </div>
      <div class="mon-table-wrap">
        <table class="mon-table">
          <thead>
            <tr>
              <th class="col-pid" onclick="sortMonProcesses('pid')">PID <span class="sort-arrow">↕</span></th>
              <th class="col-name" onclick="sortMonProcesses('name')">进程 <span class="sort-arrow">↕</span></th>
              <th class="col-cpu" onclick="sortMonProcesses('cpu')">CPU <span class="sort-arrow">↕</span></th>
              <th class="col-mem" onclick="sortMonProcesses('mem')">内存 <span class="sort-arrow">↕</span></th>
              <th class="col-runtime" onclick="sortMonProcesses('runtime')">运行时间 <span class="sort-arrow">↕</span></th>
              <th class="col-cmd">命令行</th>
              <th class="col-daemon">状态</th>
              <th class="col-act">操作</th>
            </tr>
          </thead>
          <tbody id="monTbody">
            <tr><td colspan="8" class="mon-empty">点击刷新加载进程列表</td></tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>

  <div class="topbar">
    <div class="ip-box">{{PRIMARY_URL}}</div>
    <div class="qr-wrap"><img src="{{QR}}" alt="qr"></div>
  </div>

  <!-- Daily News Section -->
  <div class="section" id="secNews">
    <div class="section-title" onclick="toggleSection('news')">
      <span>每日摘要</span>
      <span class="caret">▾</span>
    </div>
    <div class="section-body">
      <div class="news-list" id="newsList">
        <div class="mon-empty">加载中...</div>
      </div>
    </div>
  </div>

  <!-- File Share Section -->
  <div class="section" id="secFile">
    <div class="section-title" onclick="toggleSection('file')">
      <span>文件互传</span>
      <span class="caret">▾</span>
    </div>
    <div class="section-body">
      <div class="dropzone glass" id="dropzone">
        <svg class="icon" viewBox="0 0 24 24"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/></svg>
        <h3>点击或拖拽文件到此处上传</h3>
        <p>支持多文件，同一局域网设备均可访问</p>
        <div class="progress-wrap" id="progressWrap">
          <div class="progress-bar-bg"><div class="progress-bar-fill" id="progressBar"></div></div>
          <div class="progress-text" id="progressText">0%</div>
        </div>
      </div>
      <input type="file" id="fileInput" multiple>

      <div class="stats" id="stats">
        <span id="statCount">0 个文件</span>
        <div class="bar-outer"><div class="bar-inner" id="usageBar"></div></div>
        <span id="statSize">0 / 10 GB</span>
      </div>

      <div class="batch-bar" id="batchBar" style="display:none">
        <label class="batch-check"><input type="checkbox" id="batchSelectAll" onchange="toggleSelectAll()"> 全选</label>
        <button class="btn btn-danger btn-mini" onclick="batchDelete()">删除选中 (<span id="batchCount">0</span>)</button>
      </div>

      <div class="file-list" id="fileList"></div>
    </div>
  </div>

  <!-- Storage File Manager Section -->
  <div class="section" id="secStorage">
    <div class="section-title" onclick="toggleSection('storage')">
      <span>文件管理 · Storage</span>
      <span class="caret">▾</span>
    </div>
    <div class="section-body">
      <div class="ph-tabs" id="storageTabs" style="margin-bottom:14px">
        <button class="ph-tab" data-root="/mnt/andrew" onclick="switchStorageRoot('/mnt/andrew')">移动硬盘</button>
        <button class="ph-tab" data-root="/" onclick="switchStorageRoot('/')">SSD</button>
      </div>
      <div class="storage-bar" id="storageBar">
        <span class="usage-label" id="storageBarLabel">--</span>
        <div class="bar-outer"><div class="bar-inner" id="storageBarInner"></div></div>
        <span class="usage-val" id="storageBarText">--</span>
      </div>
      <div class="storage-breadcrumb" id="storageBreadcrumb">
        <span class="crumb" onclick="event.stopPropagation();navStorage('')">📁 根目录</span>
      </div>
      <div class="storage-toolbar" style="display:flex;gap:8px;margin-bottom:12px;flex-wrap:wrap;">
        <button class="btn btn-primary btn-mini" onclick="document.getElementById('storageFileInput').click()">⬆ 上传文件</button>
        <button class="btn btn-primary btn-mini" onclick="mkdirStorage()">📁 新建文件夹</button>
        <button class="btn btn-mini" style="background:var(--card);border:1px solid var(--border);color:var(--muted);" onclick="loadStorage()">↻ 刷新</button>
      </div>
      <input type="file" id="storageFileInput" multiple style="display:none" onchange="handleStorageUpload(event)">
      <div id="storageDropzone" class="storage-dropzone" style="display:none">
        <div class="s-dz-icon">📂</div>
        <p>拖拽文件到此处上传</p>
      </div>
      <div class="storage-list" id="storageList">
        <div class="storage-empty">加载中…</div>
      </div>
    </div>
  </div>

  <!-- Mihomo Gateway Section -->
  <div class="section" id="secGw">
    <div class="section-title" onclick="toggleSection('gw')">
      <span>代理网关 / Gateway</span>
      <span class="caret">▾</span>
      <span style="margin-left:auto;display:flex;align-items:center;gap:10px">
        <span class="gw-led" id="gwLed" onclick="event.stopPropagation()"><span class="dot"></span><span id="gwLedText">…</span></span>
        <button class="btn btn-glow btn-mini" id="gwToggleBtn" onclick="event.stopPropagation();toggleMihomo()">--</button>
      </span>
    </div>
    <div class="section-body">
      <div id="gwInactive" class="gw-error" style="display:none">
        mihomo 服务未运行 —— 点击右上角"启动 mihomo"或检查 <code>sudo systemctl status mihomo</code>
      </div>
      <div id="gwBox">
        <div class="gw-status-row">
          <div class="gw-pill">
            <div class="label">运行时长</div>
            <div class="value cyan" id="gwUptime">--</div>
          </div>
          <div class="gw-pill">
            <div class="label">分流模式</div>
            <div class="value purple" id="gwMode">--</div>
          </div>
          <div class="gw-pill">
            <div class="label">实时下行</div>
            <div class="value green" id="gwDown">--</div>
          </div>
          <div class="gw-pill">
            <div class="label">实时上行</div>
            <div class="value pink" id="gwUp">--</div>
          </div>
          <div class="gw-pill">
            <div class="label">活跃连接</div>
            <div class="value cyan" id="gwConns">--</div>
          </div>
          <div class="gw-pill">
            <div class="label">内存</div>
            <div class="value" id="gwMem">--</div>
          </div>
          <div class="gw-pill">
            <div class="label">GeoIP 数据</div>
            <div class="value" id="gwGeoIp">--</div>
          </div>
          <div class="gw-pill">
            <div class="label">订阅</div>
            <div class="value" id="gwSubAge">--</div>
          </div>
        </div>

        <div class="glass gw-card">
          <h4><span class="accent"></span>当前客户端 <span style="margin-left:auto;color:var(--muted);font-size:0.78rem;font-weight:400" id="gwClientsHint">读取中…</span></h4>
          <div id="gwClients"></div>
        </div>

        <div class="glass gw-card">
          <h4>
            <span class="accent" style="background:var(--purple);box-shadow:0 0 8px var(--purple)"></span>
            节点健康度 / 选择
            <span style="margin-left:auto;display:flex;gap:6px">
              <button class="btn btn-primary btn-mini" onclick="testCurrentGroup()" id="btnTestGroup">测试本组</button>
            </span>
          </h4>
          <div class="group-bar" id="gwGroups"></div>
          <div class="node-grid" id="gwNodes"></div>
          <div class="gw-muted-hint">点击节点 = 切换该分组当前节点；颜色 = 延迟（绿 &lt;200 / 黄 &lt;500 / 橙 &lt;1000 / 红 不可达）</div>
        </div>

        <div class="glass gw-card">
          <h4>
            <span class="accent" style="background:var(--pink);box-shadow:0 0 8px var(--pink)"></span>
            订阅 &amp; 操作
          </h4>
          <div class="ph-tabs" style="margin-bottom:12px">
            <button class="ph-tab on" id="tabSubUrl" onclick="switchSubMode('url')">🔗 URL 订阅</button>
            <button class="ph-tab" id="tabSubYaml" onclick="switchSubMode('yaml')">📝 手动粘贴配置</button>
          </div>

          <!-- URL subscription pane -->
          <div id="subPaneUrl">
            <div class="gw-row">
              <label>订阅链接</label>
              <input class="gw-input" id="gwSubInput" placeholder="https://gateway.example.com/sub/..." spellcheck="false">
              <button class="btn btn-primary btn-mini" onclick="saveSubUrl()">保存</button>
              <button class="btn btn-glow btn-mini" onclick="refreshSub()" id="btnRefreshSub">更新订阅</button>
            </div>
          </div>

          <!-- Manual YAML paste pane -->
          <div id="subPaneYaml" style="display:none">
            <div class="gw-row" style="flex-direction:column;align-items:stretch;gap:8px">
              <textarea class="gw-input" id="gwYamlInput"
                placeholder="在此粘贴完整的 Clash YAML 配置（含 proxies / proxy-groups / rules）..."
                style="min-height:200px;resize:vertical;font-family:'SF Mono','Cascadia Mono',monospace;font-size:0.78rem;line-height:1.5"
                spellcheck="false"></textarea>
              <div style="display:flex;gap:8px;justify-content:flex-end">
                <button class="btn btn-primary btn-mini" onclick="clearSubYaml()">清空</button>
                <button class="btn btn-glow btn-mini" onclick="uploadSubYaml()" id="btnUploadYaml">✨ 应用配置</button>
              </div>
            </div>
          </div>

          <div class="gw-row">
            <label>上次更新</label>
            <span id="gwSubMeta" style="color:var(--muted);font-size:0.82rem">--</span>
          </div>
          <div class="gw-row">
            <label>分流模式</label>
            <div class="mode-group" id="gwModeGroup">
              <button class="mode-btn" data-mode="rule" onclick="setMode('rule')">Rule</button>
              <button class="mode-btn" data-mode="global" onclick="setMode('global')">Global</button>
              <button class="mode-btn" data-mode="direct" onclick="setMode('direct')">Direct</button>
            </div>
            <button class="btn btn-danger btn-mini" style="margin-left:auto" onclick="restartMihomo()">重启 mihomo</button>
          </div>
          <div class="gw-muted-hint" id="gwSubHint">订阅更新会拉取链接、覆盖 <code>/etc/mihomo/config.yaml</code> 的 <code>proxies/proxy-groups/rules</code>，并重启服务（自动备份原文件）</div>
        </div>

        <div class="glass gw-card">
          <h4>
            <span class="accent" style="background:#4ade80;box-shadow:0 0 8px #4ade80"></span>
            最近连接
          </h4>
          <div id="gwRecent"></div>
        </div>

        <div class="glass gw-card">
          <h4>
            <span class="accent" style="background:#fbbf24;box-shadow:0 0 8px #fbbf24"></span>
            手机配置 · Phone Setup
            <span style="margin-left:auto;color:var(--muted);font-size:0.78rem;font-weight:400">把网关 / DNS 指向树莓派</span>
          </h4>

          <div class="ph-info-grid">
            <div class="ph-info-item">
              <div class="label">网关 / Gateway</div>
              <div class="row">
                <span class="value">{{PI_IP}}</span>
                <button class="ph-copy" onclick="ph_copy(this, '{{PI_IP}}')">复制</button>
              </div>
            </div>
            <div class="ph-info-item">
              <div class="label">DNS</div>
              <div class="row">
                <span class="value">{{PI_IP}}</span>
                <button class="ph-copy" onclick="ph_copy(this, '{{PI_IP}}')">复制</button>
              </div>
            </div>
            <div class="ph-info-item">
              <div class="label">HTTP 代理 / Proxy</div>
              <div class="row">
                <span class="value">{{PI_IP}}:7890</span>
                <button class="ph-copy" onclick="ph_copy(this, '{{PI_IP}}:7890')">复制</button>
              </div>
            </div>
          </div>

          <div class="ph-tabs">
            <button class="ph-tab on" data-pane="ios" onclick="ph_tab('ios')">iOS</button>
            <button class="ph-tab" data-pane="android" onclick="ph_tab('android')">Android</button>
          </div>

          <div class="ph-pane on" id="phPaneIos">
            <div class="ph-method">
              <div class="ph-method-h">
                <span class="badge">方式 A</span>
                <span class="name">设为网关(全流量)</span>
                <span class="sub">改 IP / 网关 / DNS · 走 mihomo TUN 接管所有流量</span>
              </div>
              <ol class="ph-steps">
                <li>设置 → Wi-Fi → 当前网络右侧 <code>i</code></li>
                <li>"配置 IP" 改为 <code>手动</code></li>
                <li>IP 地址填一个未被占用的(如 <code>{{PHONE_IP_EXAMPLE}}</code>),子网掩码 <code>255.255.255.0</code></li>
                <li>路由器(网关)填 <code>{{PI_IP}}</code></li>
                <li>返回上一级,"配置 DNS" 改为 <code>手动</code>,添加服务器 <code>{{PI_IP}}</code></li>
              </ol>
            </div>
            <div class="ph-method">
              <div class="ph-method-h">
                <span class="badge">方式 B</span>
                <span class="name">设为代理(仅 HTTP / HTTPS)</span>
                <span class="sub">最简单 · 只代理浏览器和大多数 App</span>
              </div>
              <ol class="ph-steps">
                <li>设置 → Wi-Fi → 当前网络右侧 <code>i</code></li>
                <li>滑到底部,"配置代理" 改为 <code>手动</code></li>
                <li>服务器填 <code>{{PI_IP}}</code>,端口填 <code>7890</code>,认证关闭</li>
              </ol>
            </div>
          </div>

          <div class="ph-pane" id="phPaneAndroid">
            <div class="ph-method">
              <div class="ph-method-h">
                <span class="badge">方式 A</span>
                <span class="name">设为网关(全流量)</span>
                <span class="sub">改 IP / 网关 / DNS · 走 mihomo TUN 接管所有流量</span>
              </div>
              <ol class="ph-steps">
                <li>设置 → Wi-Fi → 长按当前网络 → <code>修改网络</code>(或点齿轮)</li>
                <li>展开"高级选项","IP 设置" 改为 <code>静态</code></li>
                <li>IP 地址填一个未被占用的(如 <code>{{PHONE_IP_EXAMPLE}}</code>),网络前缀长度 <code>24</code></li>
                <li>网关填 <code>{{PI_IP}}</code></li>
                <li>DNS 1 填 <code>{{PI_IP}}</code>,DNS 2 留空或同上</li>
              </ol>
            </div>
            <div class="ph-method">
              <div class="ph-method-h">
                <span class="badge">方式 B</span>
                <span class="name">设为代理(仅 HTTP / HTTPS)</span>
                <span class="sub">最简单 · 只代理浏览器和大多数 App</span>
              </div>
              <ol class="ph-steps">
                <li>设置 → Wi-Fi → 长按当前网络 → <code>修改网络</code></li>
                <li>展开"高级选项","代理" 改为 <code>手动</code></li>
                <li>主机名填 <code>{{PI_IP}}</code>,端口填 <code>7890</code></li>
              </ol>
            </div>
          </div>

          <div class="ph-note">
            <strong>方式 A vs B:</strong>方式 A 把所有流量(含 UDP / 游戏 / 原生 socket)都交给 Pi,依赖 mihomo TUN 模式;方式 B 只代理 HTTP / HTTPS,简单但不全。<strong>注意:</strong>多台手机不能用同一个静态 IP,各自挑不同的最后一位。离开家时记得切回"自动 / DHCP",否则连不上别的 Wi-Fi。
          </div>
        </div>
      </div>
    </div>
  </div>

  <!-- Reachability Section -->
  <div class="section" id="secReach">
    <div class="section-title" onclick="toggleSection('reach')">
      <span>网络检测 · Reachability</span>
      <span class="caret">▾</span>
    </div>
    <div class="section-body">
      <div class="reach-actions">
        <button class="reach-btn" id="reachAllBtn" onclick="event.stopPropagation(); checkAllReach();">检测全部</button>
      </div>
      <div class="reach-grid">
        <div class="glass gw-card reach-col" id="reachColDomestic">
          <h4>
            <span class="accent"></span>
            国内 · Domestic
          </h4>
          <div id="reachListDomestic"></div>
        </div>
        <div class="glass gw-card reach-col intl" id="reachColIntl">
          <h4>
            <span class="accent"></span>
            国外 · International
          </h4>
          <div id="reachListIntl"></div>
        </div>
      </div>
    </div>
  </div>

  <!-- Speedtest Section -->
  <div class="section" id="secSpeed">
    <div class="section-title" onclick="toggleSection('speed')">
      <span>网络测速</span>
      <span class="caret">▾</span>
    </div>
    <div class="section-body">
      <div class="speed-grid">
        <div class="glass speed-card">
          <h3>内网测速</h3>
          <div class="subtitle">设备 ↔ 树莓派</div>
          <div class="speed-values">
            <div class="speed-val">
              <div class="num" id="lanPing">--</div>
              <div class="label">延迟 ms</div>
            </div>
            <div class="speed-val">
              <div class="num purple" id="lanDown">--</div>
              <div class="label">下载 MB/s</div>
            </div>
            <div class="speed-val">
              <div class="num pink" id="lanUp">--</div>
              <div class="label">上传 MB/s</div>
            </div>
          </div>
          <button class="btn btn-glow" id="btnLan" onclick="testLan()">
            <span id="lanPulse" style="display:none" class="speed-pulse"></span>开始测速
          </button>
        </div>

        <div class="glass speed-card">
          <h3>外网测速</h3>
          <div class="subtitle">路由器 ↔ 互联网</div>
          <div class="speed-values">
            <div class="speed-val">
              <div class="num" id="wanPing">--</div>
              <div class="label">延迟 ms</div>
            </div>
            <div class="speed-val">
              <div class="num purple" id="wanDown">--</div>
              <div class="label">下载 Mbps</div>
            </div>
            <div class="speed-val">
              <div class="num pink" id="wanUp">--</div>
              <div class="label">上传 Mbps</div>
            </div>
          </div>
          <button class="btn btn-glow" id="btnWan" onclick="testWan()">
            <span id="wanPulse" style="display:none" class="speed-pulse"></span>开始测速
          </button>
        </div>

        <div class="glass speed-card">
          <h3>客户端连通性</h3>
          <div class="subtitle">本设备 ↔ 互联网</div>
          <div class="reach-client-grid" id="reachClientGrid">
            <div class="reach-client-col">
              <div class="reach-client-h">国内</div>
              <div class="reach-client-item" id="rc-bilibili"><span class="rc-dot"></span><span class="rc-name">B 站</span></div>
              <div class="reach-client-item" id="rc-netflix"><span class="rc-dot"></span><span class="rc-name">Netflix</span></div>
            </div>
            <div class="reach-client-col">
              <div class="reach-client-h">国外</div>
              <div class="reach-client-item" id="rc-youtube"><span class="rc-dot"></span><span class="rc-name">YouTube</span></div>
              <div class="reach-client-item" id="rc-github"><span class="rc-dot"></span><span class="rc-name">GitHub</span></div>
              <div class="reach-client-item" id="rc-x"><span class="rc-dot"></span><span class="rc-name">X</span></div>
            </div>
          </div>
          <button class="btn btn-glow" id="btnClientReach" onclick="testClientReach()">
            <span id="clientReachPulse" style="display:none" class="speed-pulse"></span>开始检测
          </button>
        </div>
      </div>
    </div>
  </div>

  <!-- Photo Cleaner Section -->
  <div class="section" id="secPhoto">
    <div class="section-title" onclick="toggleSection('photo')">
      <span>图像处理 · Photo Cleaner</span>
      <span class="caret">▾</span>
    </div>
    <div class="section-body">
      <div id="photoNoProvider" class="photo-noprovider" style="display:none">
        ⚠ 没有可用的 Provider。请在 <code>/home/aw/vibeProjects/photo-cleaner/.env</code>
        中配置 <code>GEMINI_API_KEY</code> 或 <code>DASHSCOPE_API_KEY</code>,
        然后执行 <code>systemctl --user restart photo-cleaner</code>。
      </div>

      <div class="photo-controls">
        <label class="photo-label">服务
          <select id="photoProvider"></select>
        </label>
        <div class="photo-tabs">
          <button class="photo-tab active" data-mode="auto" onclick="selectPhotoMode('auto')" type="button">一键擦除</button>
          <button class="photo-tab" data-mode="mask" onclick="selectPhotoMode('mask')" type="button">涂抹擦除</button>
        </div>
        <label class="photo-label" style="margin-left:auto">
          <input type="checkbox" id="photoOriginal" style="accent-color:var(--cyan);cursor:pointer"> 原图模式
        </label>
      </div>

      <div class="dropzone glass photo-dropzone" id="photoDropzone">
        <div class="icon">🖼</div>
        <h3>点击或拖拽图片到此处</h3>
        <p>支持 JPG / PNG / WEBP,单图最大 50MB</p>
        <input type="file" id="photoFileInput" accept="image/*" hidden>
      </div>

      <div class="photo-workspace" id="photoWorkspace" style="display:none">
        <div class="photo-pane">
          <div class="photo-pane-title">原图<span id="photoModeHint" style="margin-left:8px;color:var(--cyan);font-size:0.78rem"></span></div>
          <div class="photo-canvas-wrap">
            <img id="photoSrcImg" class="photo-src-img" alt="">
            <canvas id="photoMaskCanvas" class="photo-mask-canvas"></canvas>
          </div>
        </div>
        <div class="photo-pane">
          <div class="photo-pane-title">结果</div>
          <div class="photo-result-wrap" id="photoResultWrap">
            <div class="photo-placeholder">点击「开始处理」</div>
          </div>
        </div>
      </div>

      <div class="photo-mask-tools" id="photoMaskTools" style="display:none">
        <label>笔刷
          <input type="range" id="photoBrushSize" min="6" max="80" value="28">
          <span id="photoBrushSizeVal">28</span>px
        </label>
        <button class="btn btn-primary btn-mini" type="button" onclick="undoMask()">↶ 撤销</button>
        <button class="btn btn-primary btn-mini" type="button" onclick="clearMask()">清空涂抹</button>
      </div>

      <div class="photo-prompt-wrap" id="photoPromptWrap" style="display:none">
        <input type="text" id="photoPrompt" class="photo-prompt"
               placeholder="可选: 自定义编辑指令,留空使用默认 prompt">
        <div class="photo-presets" id="photoPresets">
          <button type="button" class="btn btn-mini preset-btn" onclick="setPreset('remove_people')">去路人</button>
          <button type="button" class="btn btn-mini preset-btn" onclick="setPreset('remove_watermark')">去水印</button>
          <button type="button" class="btn btn-mini preset-btn" onclick="setPreset('change_bg')">换背景</button>
          <button type="button" class="btn btn-mini preset-btn" onclick="setPreset('enhance')">高清增强</button>
          <button type="button" class="btn btn-mini preset-btn" onclick="setPreset('portrait')">人像精修</button>
        </div>
      </div>

      <div class="photo-actions" id="photoActions" style="display:none">
        <button class="btn btn-glow" id="photoSubmitBtn" type="button" onclick="submitPhoto()">
          <span id="photoPulse" style="display:none" class="speed-pulse"></span>开始处理
        </button>
        <button class="btn btn-primary btn-mini" id="photoDownloadBtn" type="button" onclick="downloadPhoto()" style="display:none">下载结果</button>
        <button class="btn btn-primary btn-mini" type="button" onclick="resetPhoto()">重置</button>
      </div>
    </div>
  </div>
</div>

<div class="toast" id="toast"></div>

<script>
// ── Daily quote (rotates each refresh) ──
const QUOTES = [
  // [English, 中文译, Author]
  ['No man ever steps in the same river twice.', '人不能两次踏进同一条河。', 'Heraclitus'],
  ['One must imagine Sisyphus happy.', '应当想象西西弗是幸福的。', 'Camus'],
  ['He who has a why to live for can bear almost any how.', '一个知道为什么而活的人，几乎能承受任何怎样地活。', 'Nietzsche'],
  ['And those who were seen dancing were thought to be insane by those who could not hear the music.', '那些跳舞的人，被听不见音乐的人当成了疯子。', 'Nietzsche'],
  ['We are all in the gutter, but some of us are looking at the stars.', '我们都生活在阴沟里，但仍有人仰望星空。', 'Oscar Wilde'],
  ['I can resist everything except temptation.', '我能抵抗一切，除了诱惑。', 'Oscar Wilde'],
  ['Be yourself; everyone else is already taken.', '做你自己——其他人，都已经有人在做了。', 'Oscar Wilde'],
  ['I have nothing to declare except my genius.', '除了我的天才，我无可申报。', 'Oscar Wilde'],
  ['To live is the rarest thing in the world. Most people exist, that is all.', '真正活着，是世上最罕见之事。大多数人只是存在着。', 'Oscar Wilde'],
  ["Only two things are infinite, the universe and human stupidity, and I'm not sure about the former.", '只有两样东西是无限的——宇宙，和人类的愚蠢。前者我并不确定。', 'Einstein'],
  ['Common sense is not so common.', '所谓常识，并不常见。', 'Voltaire'],
  ['The perfect is the enemy of the good.', '完美，是优秀的敌人。', 'Voltaire'],
  ['I have made this letter longer because I lacked the time to make it shorter.', '我把这封信写长了，因为我没时间把它写短。', 'Pascal'],
  ['The heart has its reasons of which reason knows nothing.', '心中自有一种道理，理智却一无所知。', 'Pascal'],
  ['You have power over your mind — not outside events. Realize this, and you will find strength.', '你能掌控的是你的心，而非外界。明白这一点，你便有了力量。', 'Marcus Aurelius'],
  ['We suffer more often in imagination than in reality.', '我们在想象中所受的苦，多于现实之中。', 'Seneca'],
  ['The limits of my language mean the limits of my world.', '我的语言之界限，即是我的世界之界限。', 'Wittgenstein'],
  ['Whereof one cannot speak, thereof one must be silent.', '凡不可言说之事，应当保持沉默。', 'Wittgenstein'],
  ['Hell is other people.', '他人，即地狱。', 'Sartre'],
  ['Man is condemned to be free.', '人，被判处自由。', 'Sartre'],
  ['Life can only be understood backwards; but it must be lived forwards.', '生活只能在回顾中被理解，却必须向前活。', 'Kierkegaard'],
  ['I have always imagined that Paradise will be a kind of library.', '我一直幻想，天堂应是图书馆的模样。', 'Borges'],
  ['A book must be the axe for the frozen sea inside us.', '书，应是劈开我们内心冰封之海的斧头。', 'Kafka'],
  ['Until you make the unconscious conscious, it will direct your life and you will call it fate.', '在你将潜意识化为意识之前，它会主宰你的人生——而你会称它为命运。', 'Carl Jung'],
  ['I love deadlines. I love the whooshing noise they make as they go by.', '我热爱截稿日，尤其爱听它们呼啸而过的声音。', 'Douglas Adams'],
  ['The Answer to the Great Question of Life, the Universe and Everything is Forty-two.', '生命、宇宙以及一切的终极答案，是 42。', 'Douglas Adams'],
  ['It is better to keep your mouth closed and let people think you are a fool than to open it and remove all doubt.', '宁可闭嘴让人怀疑你是傻瓜，也别开口证实它。', 'Mark Twain'],
  ['The reports of my death are greatly exaggerated.', '关于我已死的报道，被严重夸大了。', 'Mark Twain'],
  ['Stay hungry, stay foolish.', '求知若饥，虚心若愚。', 'Steve Jobs'],
  ['Do I contradict myself? Very well then I contradict myself. I am large, I contain multitudes.', '我自相矛盾吗？好吧，我自相矛盾——我浩瀚，我包罗万象。', 'Walt Whitman'],
  ['The world breaks everyone, and afterward, some are strong at the broken places.', '世界使每个人破碎，之后有人在破碎之处变得更为坚强。', 'Hemingway'],
  ['Everyone thinks of changing the world, but no one thinks of changing himself.', '人人都想改变世界，却无人想改变自己。', 'Tolstoy'],
  ['The mystery of human existence lies not in just staying alive, but in finding something to live for.', '人生的奥秘，不在于活着，而在于找到值得为之而活的东西。', 'Dostoevsky'],
  ['Talent hits a target no one else can hit; genius hits a target no one else can see.', '天才命中无人能见的靶心；才能不过命中无人能及的靶心。', 'Schopenhauer'],
  ['Cogito, ergo sum.  (I think, therefore I am.)', '我思故我在。', 'Descartes'],
  ['Per aspera ad astra.  (Through hardships, to the stars.)', '历尽艰辛，方至星辰。', 'Latin proverb'],
];
(function pickQuote() {
  try {
    const q = QUOTES[Math.floor(Math.random() * QUOTES.length)];
    const el = document.getElementById('quote');
    if (el) el.innerHTML =
      '<span class="qen">' + q[0] + '</span>' +
      '<span class="qzh">' + q[1] + '<span class="qauthor">— ' + q[2] + '</span></span>';
  } catch (e) {}
})();

// ── Section toggle (persist collapse state) ──
function toggleSection(key) {
  const el = document.getElementById('sec' + key.charAt(0).toUpperCase() + key.slice(1));
  if (!el) return;
  el.classList.toggle('collapsed');
  try {
    localStorage.setItem('nebula:collapse:' + key, el.classList.contains('collapsed') ? '1' : '0');
  } catch (e) {}
}
(function restoreSectionState() {
  ['file','storage','gw','reach','speed','photo','monitor','news','wol'].forEach(k => {
    try {
      if (localStorage.getItem('nebula:collapse:' + k) === '1') {
        const el = document.getElementById('sec' + k.charAt(0).toUpperCase() + k.slice(1));
        if (el) el.classList.add('collapsed');
      }
    } catch (e) {}
  });
})();

// ── Universe Particle System ──
const canvas = document.getElementById('universe');
const ctx = canvas.getContext('2d');
let W, H, particles = [];

function resize() {
  W = canvas.width = window.innerWidth;
  H = canvas.height = window.innerHeight;
}
window.addEventListener('resize', resize);
resize();

class Particle {
  constructor() {
    this.x = Math.random() * W;
    this.y = Math.random() * H;
    this.vx = (Math.random() - 0.5) * 0.3;
    this.vy = (Math.random() - 0.5) * 0.3;
    this.size = Math.random() * 1.5 + 0.5;
    this.alpha = Math.random() * 0.5 + 0.2;
    this.hue = Math.random() > 0.5 ? 180 : 270; // cyan or purple
  }
  update() {
    this.x += this.vx;
    this.y += this.vy;
    if (this.x < 0) this.x = W;
    if (this.x > W) this.x = 0;
    if (this.y < 0) this.y = H;
    if (this.y > H) this.y = 0;
  }
  draw() {
    ctx.beginPath();
    ctx.arc(this.x, this.y, this.size, 0, Math.PI * 2);
    ctx.fillStyle = `hsla(${this.hue}, 80%, 60%, ${this.alpha})`;
    ctx.fill();
  }
}

for (let i = 0; i < 80; i++) particles.push(new Particle());

let mouse = { x: null, y: null };
window.addEventListener('mousemove', e => { mouse.x = e.clientX; mouse.y = e.clientY; });
window.addEventListener('mouseleave', () => { mouse.x = null; mouse.y = null; });

function drawLines() {
  for (let i = 0; i < particles.length; i++) {
    for (let j = i + 1; j < particles.length; j++) {
      const dx = particles[i].x - particles[j].x;
      const dy = particles[i].y - particles[j].y;
      const dist = Math.sqrt(dx*dx + dy*dy);
      if (dist < 120) {
        ctx.beginPath();
        ctx.strokeStyle = `rgba(0,240,255,${0.08 * (1 - dist/120)})`;
        ctx.lineWidth = 0.5;
        ctx.moveTo(particles[i].x, particles[i].y);
        ctx.lineTo(particles[j].x, particles[j].y);
        ctx.stroke();
      }
    }
    if (mouse.x != null) {
      const dx = particles[i].x - mouse.x;
      const dy = particles[i].y - mouse.y;
      const dist = Math.sqrt(dx*dx + dy*dy);
      if (dist < 150) {
        ctx.beginPath();
        ctx.strokeStyle = `rgba(176,38,255,${0.12 * (1 - dist/150)})`;
        ctx.lineWidth = 0.5;
        ctx.moveTo(particles[i].x, particles[i].y);
        ctx.lineTo(mouse.x, mouse.y);
        ctx.stroke();
      }
    }
  }
}

function animate() {
  ctx.clearRect(0, 0, W, H);
  particles.forEach(p => { p.update(); p.draw(); });
  drawLines();
  requestAnimationFrame(animate);
}
animate();

// ── File Share ──
const dropzone = document.getElementById('dropzone');
const fileInput = document.getElementById('fileInput');
const fileList = document.getElementById('fileList');
const progressWrap = document.getElementById('progressWrap');
const progressBar = document.getElementById('progressBar');
const progressText = document.getElementById('progressText');
const toastEl = document.getElementById('toast');

let uploading = 0;

function showToast(msg) {
  toastEl.textContent = msg;
  toastEl.classList.add('show');
  setTimeout(() => toastEl.classList.remove('show'), 2500);
}

function fmtSize(n) {
  for (const u of ['B','KB','MB','GB']) { if (n < 1024) return n.toFixed(1).replace('.0','') + ' ' + u; n /= 1024; }
  return n.toFixed(1) + ' TB';
}

function getIcon(name) {
  const ext = name.split('.').pop().toLowerCase();
  const map = {
    pdf:'📄', zip:'💾', rar:'💾', '7z':'💾',
    jpg:'🖼', jpeg:'🖼', png:'🖼', gif:'🖼', webp:'🖼',
    mp4:'🎥', mkv:'🎥', mov:'🎥', avi:'🎥',
    mp3:'🎵', wav:'🎵', flac:'🎵',
    doc:'📄', docx:'📄', xls:'📊', xlsx:'📊', ppt:'📉', pptx:'📉',
    txt:'📃', md:'📃', py:'🐍', js:'📖', html:'🔧', css:'🔧'
  };
  return map[ext] || '📁';
}

async function loadFiles() {
  try {
    const r = await fetch('/api/files');
    const d = await r.json();
    render(d);
  } catch (e) { console.error(e); }
}

function render(d) {
  document.getElementById('statCount').textContent = d.files.length + ' 个文件';
  const pct = Math.min(100, (d.total_size / (10*1024*1024*1024)) * 100);
  document.getElementById('usageBar').style.width = pct + '%';
  document.getElementById('statSize').textContent = d.total_size_human + ' / ' + d.max_size_human;

  if (!d.files.length) {
    fileList.innerHTML = '<div class="empty">暂无文件，拖拽上传第一个文件</div>';
    document.getElementById('batchBar').style.display = 'none';
    return;
  }
  document.getElementById('batchBar').style.display = 'flex';
  fileList.innerHTML = d.files.map((f, i) => {
    const h = f.remain_hours;
    const timeText = h > 24 ? Math.floor(h/24) + '天后过期' : h + '小时后过期';
    return `<div class="file-item" style="animation-delay:${i*0.04}s">
      <input type="checkbox" class="file-checkbox" value="${encodeURIComponent(f.filename)}" onchange="updateBatchCount()">
      <div class="file-icon">${getIcon(f.filename)}</div>
      <div class="file-info">
        <div class="file-name" title="${f.filename}">${f.filename}</div>
        <div class="file-meta">${f.size_human} · ${f.mtime_iso} · ${timeText}</div>
      </div>
      <div class="file-actions">
        <a class="btn btn-primary" href="/api/download/${encodeURIComponent(f.filename)}" download>下载</a>
        <button class="btn btn-danger" onclick="del('${encodeURIComponent(f.filename)}')">删除</button>
      </div>
    </div>`;
  }).join('');
  updateBatchCount();
}

async function uploadFile(file) {
  uploading++;
  progressWrap.classList.add('active');
  const fd = new FormData();
  fd.append('file', file);
  const xhr = new XMLHttpRequest();
  xhr.upload.addEventListener('progress', e => {
    if (e.lengthComputable) {
      const pct = Math.round((e.loaded / e.total) * 100);
      progressBar.style.width = pct + '%';
      progressText.textContent = pct + '%';
    }
  });
  await new Promise((res, rej) => {
    xhr.addEventListener('load', () => {
      if (xhr.status >= 200 && xhr.status < 300) res();
      else rej(new Error(xhr.statusText));
    });
    xhr.addEventListener('error', rej);
    xhr.open('POST', '/api/upload');
    xhr.send(fd);
  });
  uploading--;
  if (!uploading) {
    progressBar.style.width = '100%';
    setTimeout(() => { progressWrap.classList.remove('active'); progressBar.style.width = '0%'; }, 600);
  }
}

async function handleFiles(files) {
  if (!files.length) return;
  for (const f of files) {
    try { await uploadFile(f); }
    catch (e) {
      showToast('上传失败: ' + f.name);
      uploading = Math.max(0, uploading - 1);
    }
  }
  showToast('上传完成');
  loadFiles();
}

dropzone.addEventListener('click', () => fileInput.click());
dropzone.addEventListener('dragover', e => { e.preventDefault(); dropzone.classList.add('dragover'); });
dropzone.addEventListener('dragleave', () => dropzone.classList.remove('dragover'));
dropzone.addEventListener('drop', e => {
  e.preventDefault();
  dropzone.classList.remove('dragover');
  handleFiles(e.dataTransfer.files);
});
fileInput.addEventListener('change', e => handleFiles(e.target.files));

// ── Storage File Manager ──
let _storagePath = '';
let _storageRoot = '/mnt/andrew';
let _storageUploading = 0;

function _storageQ(root, path) {
  const qs = new URLSearchParams();
  if (root) qs.set('root', root);
  if (path) qs.set('path', path);
  const s = qs.toString();
  return s ? '?' + s : '';
}

function switchStorageRoot(root) {
  _storageRoot = root;
  _storagePath = '';
  document.querySelectorAll('#storageTabs .ph-tab').forEach(t => {
    t.classList.toggle('on', t.dataset.root === root);
  });
  loadStorage();
}

async function loadStorage() {
  const list = document.getElementById('storageList');
  try {
    const r = await fetch('/api/storage/files' + _storageQ(_storageRoot, _storagePath));
    const d = await r.json();
    if (!d.ok) throw new Error(d.error || 'unknown');
    renderStorage(d);
  } catch (e) {
    if (list) list.innerHTML = '<div class="storage-empty" style="color:var(--danger)">加载失败: ' + escHtml(e.message) + '</div>';
  }
}

function renderStorage(d) {
  // device label
  const barLabel = document.getElementById('storageBarLabel');
  if (barLabel) barLabel.textContent = d.root_label || '存储';

  // usage bar
  const barInner = document.getElementById('storageBarInner');
  const barText = document.getElementById('storageBarText');
  if (barInner) barInner.style.width = Math.min(100, d.percent) + '%';
  if (barText) barText.textContent = d.used_human + ' / ' + d.total_human + ' (' + d.percent + '%)';

  // breadcrumb
  const bc = document.getElementById('storageBreadcrumb');
  if (bc) {
    const parts = _storagePath.split('/').filter(Boolean);
    let html = `<span class="crumb" onclick="event.stopPropagation();navStorage('')">📁 根目录</span>`;
    let build = '';
    for (let i = 0; i < parts.length; i++) {
      build += (build ? '/' : '') + parts[i];
      html += `<span class="sep">/</span><span class="crumb" onclick="event.stopPropagation();navStorage('${escAttr(build)}')">${escHtml(parts[i])}</span>`;
    }
    bc.innerHTML = html;
  }

  // list
  const list = document.getElementById('storageList');
  if (!list) return;
  if (!d.items || !d.items.length) {
    list.innerHTML = '<div class="storage-empty">目录为空</div>';
    return;
  }
  list.innerHTML = d.items.map((it, i) => {
    const isDir = it.type === 'dir';
    const icon = isDir ? '📁' : '📄';
    const iconCls = isDir ? 's-icon folder' : 's-icon';
    const click = isDir ? `onclick="event.stopPropagation();enterStorageDir('${escAttr(it.name)}')"` : '';
    const meta = isDir ? '文件夹' : (it.size_human + ' · ' + it.mtime_iso);
    const dlPath = encodeURIComponent(_storagePath ? _storagePath + '/' + it.name : it.name);
    const dl = isDir ? '' : `<a class="btn btn-primary btn-mini" href="/api/storage/download${_storageQ(_storageRoot, _storagePath ? _storagePath + '/' + it.name : it.name)}" download>下载</a>`;
    return `<div class="storage-item" style="animation-delay:${i*0.03}s" ${click}>
      <div class="${iconCls}">${icon}</div>
      <div class="s-info">
        <div class="s-name" title="${escAttr(it.name)}">${escHtml(it.name)}</div>
        <div class="s-meta">${escHtml(meta)}</div>
      </div>
      <div class="s-actions">
        ${dl}
        <button class="btn btn-danger btn-mini" onclick="event.stopPropagation();deleteStorageItem('${escAttr(it.name)}')">删除</button>
      </div>
    </div>`;
  }).join('');
}

function enterStorageDir(name) {
  _storagePath = _storagePath ? _storagePath + '/' + name : name;
  loadStorage();
}

function navStorage(path) {
  _storagePath = path;
  loadStorage();
}

async function deleteStorageItem(name) {
  const rel = _storagePath ? _storagePath + '/' + name : name;
  if (!confirm('确定要删除 "' + name + '" 吗？')) return;
  try {
    const r = await fetch('/api/storage/files' + _storageQ(_storageRoot, rel), { method: 'DELETE' });
    const d = await r.json();
    if (d.ok) { showToast('已删除'); loadStorage(); }
    else { showToast('删除失败: ' + (d.error || '')); }
  } catch (e) { showToast('删除失败: ' + e.message); }
}

async function mkdirStorage() {
  const name = prompt('新建文件夹名称:');
  if (!name || !name.trim()) return;
  const rel = _storagePath ? _storagePath + '/' + name.trim() : name.trim();
  try {
    const r = await fetch('/api/storage/mkdir' + _storageQ(_storageRoot, rel), { method: 'POST' });
    const d = await r.json();
    if (d.ok) { showToast('已创建'); loadStorage(); }
    else { showToast('创建失败: ' + (d.error || '')); }
  } catch (e) { showToast('创建失败: ' + e.message); }
}

async function handleStorageUpload(ev) {
  const files = ev.target.files;
  if (!files.length) return;
  for (const file of files) {
    _storageUploading++;
    const fd = new FormData();
    fd.append('file', file);
    try {
      const r = await fetch('/api/storage/upload' + _storageQ(_storageRoot, _storagePath), { method: 'POST', body: fd });
      const d = await r.json();
      if (!d.ok) throw new Error(d.error || 'HTTP ' + r.status);
    } catch (e) {
      showToast('上传失败: ' + file.name + ' - ' + e.message);
    }
    _storageUploading--;
  }
  if (!_storageUploading) { showToast('上传完成'); loadStorage(); }
  ev.target.value = '';
}

// Auto-load storage when section is expanded
document.addEventListener('click', function(e) {
  const title = e.target.closest('.section-title');
  if (!title) return;
  const section = title.closest('.section');
  if (section && section.id === 'secStorage' && !section.classList.contains('collapsed')) {
    // Ensure default tab is active on first open
    const tabs = document.querySelectorAll('#storageTabs .ph-tab');
    if (tabs.length && !Array.from(tabs).some(t => t.classList.contains('on'))) {
      tabs[0].classList.add('on');
    }
    loadStorage();
  }
});

const PRESETS = {
  remove_people: '精确擦除画面中的所有路人、游客和无关人物,保持主体人物和背景环境完全不变',
  remove_watermark: '无痕去除图片中的所有水印、文字、Logo和标记,用周围内容自然填补,保持画面完整一致',
  change_bg: '将背景替换为简洁纯色背景或自然风景,保持主体人物不变,确保边缘融合自然',
  enhance: '提升图片清晰度和细节,修复模糊区域,增强色彩饱和度和对比度,保持人物五官自然',
  portrait: '人像精修:自然美化皮肤质感,轻微提亮面部,保持五官细节和真实感,不要过度磨皮'
};

function setPreset(key) {
  const input = document.getElementById('photoPrompt');
  input.value = PRESETS[key] || '';
  input.focus();
}

window.del = async function(name) {
  if (!confirm('确定删除?')) return;
  try {
    const r = await fetch('/api/files/' + name, { method: 'DELETE' });
    if (r.ok) { showToast('已删除'); loadFiles(); }
    else showToast('删除失败');
  } catch (e) { showToast('删除失败'); }
};

function toggleSelectAll() {
  const all = document.getElementById('batchSelectAll').checked;
  document.querySelectorAll('.file-checkbox').forEach(cb => cb.checked = all);
  updateBatchCount();
}

function updateBatchCount() {
  const checked = document.querySelectorAll('.file-checkbox:checked');
  document.getElementById('batchCount').textContent = checked.length;
}

async function batchDelete() {
  const checked = Array.from(document.querySelectorAll('.file-checkbox:checked'));
  if (!checked.length) { showToast('请先选择文件'); return; }
  const names = checked.map(cb => decodeURIComponent(cb.value));
  if (!confirm('确定删除选中的 ' + names.length + ' 个文件?')) return;
  try {
    const r = await fetch('/api/files/batch-delete', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ names })
    });
    const d = await r.json();
    if (d.deleted && d.deleted.length) {
      showToast('已删除 ' + d.deleted.length + ' 个文件');
    }
    if (d.failed && d.failed.length) {
      showToast(d.failed.length + ' 个文件删除失败');
    }
    loadFiles();
  } catch (e) { showToast('批量删除失败'); }
}

document.addEventListener('dragover', e => e.preventDefault());
document.addEventListener('drop', e => e.preventDefault());

loadFiles();
setInterval(loadFiles, 15000);

// ── PC Console ──
let _pcOnline = null;
let _pcPollTimer = null;
const PC_POLL_MS = 5000;

function setPcLed(online) {
  const led = document.getElementById('pcLed');
  const text = document.getElementById('pcLedText');
  const icon = document.getElementById('pcIcon');
  const rtt = document.getElementById('pcRtt');
  if (!led) return;
  led.classList.remove('online', 'offline');
  icon.classList.remove('online', 'offline');
  rtt.classList.remove('online');
  if (online) {
    led.classList.add('online');
    icon.classList.add('online');
    rtt.classList.add('online');
    text.textContent = '在线';
  } else {
    led.classList.add('offline');
    icon.classList.add('offline');
    text.textContent = '离线';
  }
}

function setPcButtons(online) {
  const wolBtn = document.getElementById('btnWol');
  const shutdownBtn = document.getElementById('btnShutdown');
  if (wolBtn) wolBtn.disabled = online === true;
  if (shutdownBtn) shutdownBtn.disabled = online === false;
}

async function loadPcStatus() {
  try {
    const r = await fetch('/api/pc/status');
    const d = await r.json();
    if (!d.ok) throw new Error(d.error);
    _pcOnline = d.online;
    setPcLed(d.online);
    setPcButtons(d.online);
    const rttEl = document.getElementById('pcRtt');
    if (rttEl) {
      rttEl.textContent = d.online
        ? (d.rtt_ms != null ? d.rtt_ms + ' ms' : '在线')
        : '离线';
    }
  } catch (e) {
    _pcOnline = false;
    setPcLed(false);
    setPcButtons(false);
    const rttEl = document.getElementById('pcRtt');
    if (rttEl) rttEl.textContent = '检测失败';
  }
}

async function sendWol() {
  const btn = document.getElementById('btnWol');
  const pulse = document.getElementById('wolPulse');
  if (btn.disabled) return;
  btn.disabled = true;
  pulse.style.display = 'inline-block';
  const origText = btn.childNodes[btn.childNodes.length - 1].textContent;
  btn.childNodes[btn.childNodes.length - 1].textContent = ' 发送中...';
  try {
    const r = await fetch('/api/wol', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({}) });
    const d = await r.json();
    if (d.ok) {
      showToast('唤醒魔法包已发送 🖥✨');
      // Start polling more aggressively after wake
      setTimeout(loadPcStatus, 2000);
      setTimeout(loadPcStatus, 5000);
      setTimeout(loadPcStatus, 10000);
    } else {
      showToast('唤醒失败: ' + (d.error || '未知错误'));
    }
  } catch (e) {
    showToast('唤醒请求失败: ' + e.message);
  } finally {
    btn.disabled = false;
    pulse.style.display = 'none';
    btn.childNodes[btn.childNodes.length - 1].textContent = origText;
  }
}

async function sendShutdown() {
  if (!confirm('确定要远程关闭 PC 吗？')) return;
  const btn = document.getElementById('btnShutdown');
  const pulse = document.getElementById('shutdownPulse');
  if (btn.disabled) return;
  btn.disabled = true;
  pulse.style.display = 'inline-block';
  const origText = btn.childNodes[btn.childNodes.length - 1].textContent;
  btn.childNodes[btn.childNodes.length - 1].textContent = ' 发送中...';
  try {
    const r = await fetch('/api/pc/shutdown', { method: 'POST' });
    const d = await r.json();
    if (d.ok) {
      showToast('关机命令已发送 🖥💤');
      // Poll to see when it goes offline
      setTimeout(loadPcStatus, 3000);
      setTimeout(loadPcStatus, 6000);
      setTimeout(loadPcStatus, 12000);
    } else {
      showToast('关机失败: ' + (d.error || '未知错误'));
    }
  } catch (e) {
    showToast('关机请求失败: ' + e.message);
  } finally {
    btn.disabled = false;
    pulse.style.display = 'none';
    btn.childNodes[btn.childNodes.length - 1].textContent = origText;
  }
}

function togglePcHelp() {
  const help = document.getElementById('pcHelp');
  if (help) help.classList.toggle('collapsed');
}

function startPcPolling() {
  if (_pcPollTimer) return;
  loadPcStatus();
  _pcPollTimer = setInterval(loadPcStatus, PC_POLL_MS);
}
function stopPcPolling() {
  if (_pcPollTimer) { clearInterval(_pcPollTimer); _pcPollTimer = null; }
}

// Auto-start polling when PC section is visible
document.addEventListener('visibilitychange', () => {
  if (document.visibilityState === 'visible') startPcPolling();
  else stopPcPolling();
});

// ── Speedtest ──

async function testLan() {
  const btn = document.getElementById('btnLan');
  const pulse = document.getElementById('lanPulse');
  btn.disabled = true;
  pulse.style.display = 'inline-block';
  btn.childNodes[btn.childNodes.length-1].textContent = ' 测速中...';

  document.getElementById('lanPing').textContent = '--';
  document.getElementById('lanDown').textContent = '--';
  document.getElementById('lanUp').textContent = '--';

  try {
    // Ping test (small request)
    const pingStart = performance.now();
    await fetch('/api/files');
    const ping = Math.round(performance.now() - pingStart);
    document.getElementById('lanPing').textContent = ping;

    // Download test
    const downSize = 30; // MB
    const downStart = performance.now();
    await fetch(`/api/speedtest/lan?size=${downSize}`);
    const downMs = performance.now() - downStart;
    const downSpeed = ((downSize * 1024 * 1024 * 8) / (downMs / 1000) / 1024 / 1024 / 8).toFixed(1);
    document.getElementById('lanDown').textContent = downSpeed;

    // Upload test
    const upSize = 10 * 1024 * 1024; // 10MB
    const upBlob = new Blob([new Uint8Array(upSize).map(() => Math.random() * 256)]);
    const upStart = performance.now();
    await fetch('/api/speedtest/lan-upload', { method: 'POST', body: upBlob });
    const upMs = performance.now() - upStart;
    const upSpeed = ((upSize * 8) / (upMs / 1000) / 1024 / 1024 / 8).toFixed(1);
    document.getElementById('lanUp').textContent = upSpeed;

    showToast('内网测速完成');
  } catch (e) {
    showToast('内网测速失败');
    console.error(e);
  } finally {
    btn.disabled = false;
    pulse.style.display = 'none';
    btn.childNodes[btn.childNodes.length-1].textContent = '开始测速';
  }
}

async function testWan() {
  const btn = document.getElementById('btnWan');
  const pulse = document.getElementById('wanPulse');
  btn.disabled = true;
  pulse.style.display = 'inline-block';
  btn.childNodes[btn.childNodes.length-1].textContent = ' 测速中...';

  document.getElementById('wanPing').textContent = '--';
  document.getElementById('wanDown').textContent = '--';
  document.getElementById('wanUp').textContent = '--';

  try {
    const r = await fetch('/api/speedtest/wan');
    const d = await r.json();
    if (!d.ok) throw new Error(d.error);
    document.getElementById('wanPing').textContent = Math.round(d.ping);
    document.getElementById('wanDown').textContent = Math.round(d.download);
    document.getElementById('wanUp').textContent = Math.round(d.upload);
    showToast('外网测速完成');
  } catch (e) {
    showToast('外网测速失败: ' + (e.message || '未知错误'));
    console.error(e);
  } finally {
    btn.disabled = false;
    pulse.style.display = 'none';
    btn.childNodes[btn.childNodes.length-1].textContent = '开始测速';
  }
}

// ── Client Reachability (runs from browser) ──
const CLIENT_REACH_TARGETS = [
  { id: 'bilibili', name: 'B 站', group: 'domestic', url: 'https://www.bilibili.com/favicon.ico' },
  { id: 'netflix',  name: 'Netflix', group: 'domestic', url: 'https://www.netflix.com/favicon.ico' },
  { id: 'youtube',  name: 'YouTube', group: 'intl', url: 'https://www.youtube.com/favicon.ico' },
  { id: 'github',   name: 'GitHub',  group: 'intl', url: 'https://github.com/favicon.ico' },
  { id: 'x',        name: 'X',       group: 'intl', url: 'https://abs.twimg.com/favicons/twitter.2.ico' },
];

async function probeClientReach(target, timeoutMs = 6000) {
  const ctrl = new AbortController();
  const t = setTimeout(() => ctrl.abort(), timeoutMs);
  try {
    await fetch(target.url, { method: 'GET', mode: 'no-cors', signal: ctrl.signal });
    clearTimeout(t);
    return { ok: true };
  } catch (e) {
    clearTimeout(t);
    return { ok: false, reason: e.name === 'AbortError' ? 'timeout' : 'error' };
  }
}

function setReachClientUI(id, status) {
  const el = document.getElementById('rc-' + id);
  if (!el) return;
  const dot = el.querySelector('.rc-dot');
  dot.classList.remove('ok', 'fail', 'checking');
  if (status === 'checking') dot.classList.add('checking');
  else if (status === 'ok') dot.classList.add('ok');
  else dot.classList.add('fail');
}

async function testClientReach() {
  const btn = document.getElementById('btnClientReach');
  const pulse = document.getElementById('clientReachPulse');
  btn.disabled = true;
  pulse.style.display = 'inline-block';
  btn.childNodes[btn.childNodes.length-1].textContent = ' 检测中...';

  for (const t of CLIENT_REACH_TARGETS) setReachClientUI(t.id, 'checking');

  const results = await Promise.all(CLIENT_REACH_TARGETS.map(async t => {
    const r = await probeClientReach(t);
    setReachClientUI(t.id, r.ok ? 'ok' : 'fail');
    return { id: t.id, ok: r.ok };
  }));

  const okCount = results.filter(r => r.ok).length;
  showToast(`连通性检测完成: ${okCount}/${results.length} 可达`);

  btn.disabled = false;
  pulse.style.display = 'none';
  btn.childNodes[btn.childNodes.length-1].textContent = '重新检测';
}

// ── Mihomo Gateway ──
const gwState = {
  groups: [],
  selectedGroup: null,
  delays: {},      // node-name -> ms (0 = unreachable / not tested)
  lastClientsAt: 0,
  clientNames: {}, // ip -> custom name
};

function fmtRate(bps) {
  if (!bps || bps < 1) return '0';
  if (bps < 1024) return bps.toFixed(0) + ' B/s';
  if (bps < 1024*1024) return (bps/1024).toFixed(1) + ' KB/s';
  if (bps < 1024*1024*1024) return (bps/1024/1024).toFixed(1) + ' MB/s';
  return (bps/1024/1024/1024).toFixed(2) + ' GB/s';
}

function fmtBytes(b) {
  if (!b) return '0';
  for (const u of ['B','KB','MB','GB','TB']) {
    if (b < 1024) return b.toFixed(b<10?1:0) + u;
    b /= 1024;
  }
  return b.toFixed(1) + 'PB';
}

function delayClass(ms) {
  if (!ms || ms <= 0) return 'dl-none';
  if (ms < 200) return 'dl-good';
  if (ms < 500) return 'dl-mid';
  if (ms < 1000) return 'dl-slow';
  return 'dl-bad';
}

function isLocalLan(ip) {
  // exclude mihomo's own utun/loopback for client display
  if (!ip) return false;
  if (ip === '127.0.0.1' || ip === '::1') return false;
  if (ip.startsWith('198.18.')) return false;
  return true;
}

function fmtUptime(sec) {
  if (sec == null || sec < 0) return '--';
  const d = Math.floor(sec / 86400);
  const h = Math.floor((sec % 86400) / 3600);
  const m = Math.floor((sec % 3600) / 60);
  if (d) return d + 'd ' + h + 'h';
  if (h) return h + 'h ' + m + 'm';
  return m + 'm ' + (sec % 60) + 's';
}

async function loadGwStatus() {
  try {
    const r = await fetch('/api/mihomo/status');
    const d = await r.json();
    const led = document.getElementById('gwLed');
    const ledText = document.getElementById('gwLedText');
    const toggleBtn = document.getElementById('gwToggleBtn');
    const inactive = document.getElementById('gwInactive');
    const box = document.getElementById('gwBox');

    if (!d.ok || !d.active) {
      led.className = 'gw-led dead';
      ledText.textContent = 'OFFLINE';
      toggleBtn.textContent = '启动 mihomo';
      toggleBtn.dataset.action = 'start';
      inactive.style.display = 'block';
      box.style.opacity = '0.4';
      return;
    }
    led.className = 'gw-led live';
    ledText.textContent = 'LIVE · v' + (d.version || '?');
    toggleBtn.textContent = '停止 mihomo';
    toggleBtn.dataset.action = 'stop';
    inactive.style.display = 'none';
    box.style.opacity = '1';

    document.getElementById('gwUptime').textContent = fmtUptime(d.uptime_sec);
    document.getElementById('gwMode').textContent = (d.mode || '?').toUpperCase();
    document.getElementById('gwDown').textContent = fmtRate(d.traffic.down);
    document.getElementById('gwUp').textContent = fmtRate(d.traffic.up);
    document.getElementById('gwConns').textContent = d.connections || 0;
    document.getElementById('gwMem').textContent = d.memory ? fmtBytes(d.memory) : '--';

    const geoEl = document.getElementById('gwGeoIp');
    const ageDay = d.geoip_age_days;
    if (ageDay == null) { geoEl.textContent = '--'; geoEl.className = 'value'; }
    else {
      geoEl.textContent = ageDay + ' 天前';
      geoEl.className = 'value ' + (ageDay > 14 ? 'red' : (ageDay > 7 ? 'pink' : 'green'));
    }

    // mode toggle
    document.querySelectorAll('.mode-btn').forEach(b => {
      b.classList.toggle('on', b.dataset.mode === (d.mode || '').toLowerCase());
    });

    // sub info
    const sub = d.subscription || {};
    if (sub.url_full && !document.getElementById('gwSubInput').value) {
      document.getElementById('gwSubInput').value = sub.url_full;
    }
    const subAgeEl = document.getElementById('gwSubAge');
    const subMeta = document.getElementById('gwSubMeta');
    if (sub.last_update) {
      const ageSec = Math.floor(Date.now()/1000) - sub.last_update;
      const ageDays = ageSec / 86400;
      subAgeEl.textContent = ageDays < 1 ? Math.round(ageSec/3600) + 'h前' : Math.round(ageDays) + '天前';
      subAgeEl.className = 'value ' + (ageDays > 7 ? 'pink' : 'green');
      subMeta.textContent = sub.last_update_iso;
    } else if (sub.url_full) {
      subAgeEl.textContent = '未拉取'; subAgeEl.className = 'value';
      subMeta.textContent = '已保存 URL，从未拉取过';
    } else {
      subAgeEl.textContent = '未配置'; subAgeEl.className = 'value';
      subMeta.textContent = '未配置订阅链接';
    }
  } catch (e) {
    document.getElementById('gwLedText').textContent = 'ERROR';
    document.getElementById('gwLed').className = 'gw-led dead';
  }
}

async function toggleMihomo() {
  const btn = document.getElementById('gwToggleBtn');
  const action = btn.dataset.action;
  if (!action) return;
  if (action === 'stop' && !confirm('确定停止 mihomo？所有走代理的客户端将立即断网。')) return;
  btn.disabled = true;
  const old = btn.textContent;
  btn.textContent = (action === 'start' ? '启动中…' : '停止中…');
  try {
    const r = await fetch('/api/mihomo/' + action, { method: 'POST' });
    const d = await r.json();
    if (d.ok) {
      showToast('mihomo ' + (action === 'start' ? '已启动' : '已停止'));
      setTimeout(loadAllGw, 1500);
    } else {
      showToast('操作失败: ' + (d.error || ''));
    }
  } catch (e) { showToast('操作失败'); }
  btn.disabled = false;
  btn.textContent = old;
}

async function loadClients() {
  try {
    const r = await fetch('/api/mihomo/clients');
    const d = await r.json();
    const box = document.getElementById('gwClients');
    const hint = document.getElementById('gwClientsHint');
    if (!d.ok) { box.innerHTML = '<div class="empty">无法获取连接</div>'; hint.textContent = ''; return; }
    const list = (d.clients || []).filter(c => isLocalLan(c.ip));
    hint.textContent = list.length + ' 个客户端';
    if (!list.length) { box.innerHTML = '<div class="empty">当前没有走代理的客户端</div>'; return; }
    box.innerHTML = list.map(c => {
      const isTv = (c.ip === '192.168.50.141') ? '📺' : '💻';
      const rule = c.rule || '?';
      const fullChain = (c.chain || 'DIRECT').replace(/</g,'&lt;');
      const isDirect = fullChain === 'DIRECT' || /Direct/i.test(fullChain);
      const badgeCls = isDirect ? 'route-badge direct' : 'route-badge proxy';
      const badgeText = isDirect ? '● 直连' : '● 代理';
      // Simplify chain: show only final hop
      const hops = fullChain.split(' → ');
      const finalHop = hops[hops.length - 1] || fullChain;
      // Build tooltip explaining each hop
      let tooltip = fullChain;
      if (!isDirect && hops.length > 1) {
        tooltip = hops.map((h, i) => {
          if (i === 0) return h + ' (匹配规则)';
          if (i === hops.length - 1) return h + ' (出口节点)';
          return h + ' (代理策略组)';
        }).join(' → ');
      } else if (isDirect) {
        tooltip = 'DIRECT → 不经过代理，直接连接目标';
      }
      const host = c.host_recent ? ' · ' + c.host_recent : '';
      const customName = gwState.clientNames[c.ip] || '';
      const nameHtml = customName
        ? `<span class="client-name" title="点击修改名称" onclick="editClientName('${escAttr(c.ip)}')">${escHtml(customName)}</span>`
        : `<span class="client-name unnamed" title="点击命名" onclick="editClientName('${escAttr(c.ip)}')">+ 命名</span>`;
      return `<div class="client-row">
        <div class="ic">${isTv}</div>
        <div>
          <div class="ip-line">
            <div class="ip">${c.ip}</div>
            ${nameHtml}
            <span class="${badgeCls}" title="${escAttr(tooltip)}">${badgeText}</span>
          </div>
          <div class="meta"><span class="rule">${rule}</span> → <span class="chain chain-tip" title="${escAttr(tooltip)}">${escHtml(finalHop)}</span>${host}</div>
        </div>
        <div class="rate">
          <div class="r-line"><span class="r-tag">实时↓</span><span class="dn">${fmtRate(c.download_rate)}</span></div>
          <div class="r-line"><span class="r-tag">实时↑</span><span class="up">${fmtRate(c.upload_rate)}</span></div>
        </div>
        <div class="conns">
          <div class="r-line"><span class="r-tag">累计↓</span><span class="dn">${fmtBytes(c.download_bytes)}</span></div>
          <div class="r-line"><span class="r-tag">累计↑</span><span class="up">${fmtBytes(c.upload_bytes)}</span></div>
          <div class="conn-num">${c.connections} 个连接</div>
        </div>
      </div>`;
    }).join('');
  } catch (e) { console.error(e); }
}

async function loadGroups() {
  try {
    const r = await fetch('/api/mihomo/groups');
    const d = await r.json();
    if (!d.ok) return;
    gwState.groups = d.groups || [];
    if (!gwState.selectedGroup && gwState.groups.length) {
      // Prefer Proxies > YouTube > first
      const preferred = ['Proxies','YouTube','Netflix','✈️Final'];
      gwState.selectedGroup = preferred.find(p => gwState.groups.some(g => g.name === p))
                             || gwState.groups[0].name;
    }
    renderGroupChips();
    renderNodes();
  } catch (e) { console.error(e); }
}

function renderGroupChips() {
  const bar = document.getElementById('gwGroups');
  bar.innerHTML = gwState.groups.map(g => {
    const cls = g.name === gwState.selectedGroup ? 'group-chip active' : 'group-chip';
    const now = (g.now || '').length > 14 ? g.now.slice(0,13) + '…' : (g.now || '');
    return `<div class="${cls}" onclick="selectGroup('${escAttr(g.name)}')">
      ${escHtml(g.name)} <span class="now">→ ${escHtml(now)}</span>
    </div>`;
  }).join('');
}

function selectGroup(name) {
  gwState.selectedGroup = name;
  renderGroupChips();
  renderNodes();
}

function renderNodes() {
  const grid = document.getElementById('gwNodes');
  const g = gwState.groups.find(x => x.name === gwState.selectedGroup);
  if (!g) { grid.innerHTML = '<div class="empty">无可用节点</div>'; return; }
  grid.innerHTML = g.members.map(m => {
    const merged = (m.name in gwState.delays) ? gwState.delays[m.name] : m.delay;
    const cls = delayClass(merged);
    const sel = m.name === g.now ? ' selected' : '';
    const dlText = merged > 0 ? merged + ' ms' : '—';
    return `<div class="node-tile${sel}" onclick="pickNode('${escAttr(m.name)}')" title="${escAttr(m.name)}">
      <div class="nm">${escHtml(m.name)}</div>
      <div class="dl ${cls}"><span class="dot"></span>${dlText}</div>
    </div>`;
  }).join('');
}

async function pickNode(name) {
  const group = gwState.selectedGroup;
  if (!group) return;
  try {
    const r = await fetch('/api/mihomo/select', {
      method: 'POST',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify({ group, name })
    });
    const d = await r.json();
    if (d.ok) {
      showToast(group + ' → ' + name);
      // Update local state
      const g = gwState.groups.find(x => x.name === group);
      if (g) g.now = name;
      renderGroupChips(); renderNodes();
    } else {
      showToast('切换失败: ' + (d.error || ''));
    }
  } catch (e) { showToast('切换失败'); }
}

async function testCurrentGroup() {
  const group = gwState.selectedGroup;
  if (!group) return;
  const btn = document.getElementById('btnTestGroup');
  btn.disabled = true; btn.textContent = '测试中…';
  try {
    const r = await fetch('/api/mihomo/test/group/' + encodeURIComponent(group) + '?timeout=3000');
    const d = await r.json();
    if (d.ok && d.delays) {
      // merge: nodes not in result = unreachable (0)
      const g = gwState.groups.find(x => x.name === group);
      if (g) {
        for (const m of g.members) {
          gwState.delays[m.name] = (m.name in d.delays) ? d.delays[m.name] : 0;
        }
      }
      renderNodes();
      const ok = Object.values(d.delays).filter(v => v > 0).length;
      const total = (g ? g.members.length : Object.keys(d.delays).length);
      showToast('测试完成: ' + ok + '/' + total + ' 可达');
    } else {
      showToast('测试失败: ' + (d.error || ''));
    }
  } catch (e) { showToast('测试失败'); }
  btn.disabled = false; btn.textContent = '测试本组';
}

async function setMode(mode) {
  try {
    const r = await fetch('/api/mihomo/mode', {
      method: 'POST',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify({ mode })
    });
    const d = await r.json();
    if (d.ok) { showToast('模式 → ' + mode); loadGwStatus(); }
    else showToast('切换失败: ' + (d.error || ''));
  } catch (e) { showToast('切换失败'); }
}

async function saveSubUrl() {
  const url = document.getElementById('gwSubInput').value.trim();
  if (!url) { showToast('请填写订阅链接'); return; }
  try {
    const r = await fetch('/api/mihomo/sub', {
      method: 'POST',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify({ url })
    });
    const d = await r.json();
    if (d.ok) showToast('已保存 (尚未拉取)');
    else showToast('保存失败: ' + (d.error || ''));
  } catch (e) { showToast('保存失败'); }
}

async function refreshSub() {
  const url = document.getElementById('gwSubInput').value.trim();
  if (!url) { showToast('请填写订阅链接'); return; }
  if (!confirm('将 fetch 订阅 → 覆盖 mihomo 配置 → 重启服务。继续？')) return;
  const btn = document.getElementById('btnRefreshSub');
  btn.disabled = true; btn.textContent = '更新中…';
  try {
    const r = await fetch('/api/mihomo/sub/refresh', {
      method: 'POST',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify({ url })
    });
    const d = await r.json();
    if (d.ok) {
      showToast('订阅已更新: ' + d.proxy_count + ' 节点');
      setTimeout(loadAllGw, 2000);
    } else {
      const err = d.error || '';
      // If TLS/network error, nudge user toward manual paste
      if (/ssl|tls|eof|handshake|certificate|connect/i.test(err)) {
        showToast('⚠️ 自动拉取失败 (TLS/网络问题)，请切换到「手动粘贴配置」');
      } else {
        showToast('更新失败: ' + err);
      }
    }
  } catch (e) { showToast('更新失败: ' + e.message); }
  btn.disabled = false; btn.textContent = '更新订阅';
}

async function restartMihomo() {
  if (!confirm('确定重启 mihomo？短暂断网。')) return;
  try {
    const r = await fetch('/api/mihomo/restart', { method: 'POST' });
    const d = await r.json();
    if (d.ok) {
      showToast('mihomo 重启中…');
      setTimeout(loadAllGw, 3000);
    } else showToast('重启失败: ' + (d.error || ''));
  } catch (e) { showToast('重启失败'); }
}

// ── Subscription mode switcher (URL vs manual YAML paste) ──
function switchSubMode(mode) {
  document.getElementById('tabSubUrl').classList.toggle('on', mode === 'url');
  document.getElementById('tabSubYaml').classList.toggle('on', mode === 'yaml');
  document.getElementById('subPaneUrl').style.display = mode === 'url' ? 'block' : 'none';
  document.getElementById('subPaneYaml').style.display = mode === 'yaml' ? 'block' : 'none';
  const hint = document.getElementById('gwSubHint');
  if (hint) {
    hint.textContent = mode === 'url'
      ? '订阅更新会拉取链接、覆盖 /etc/mihomo/config.yaml 的 proxies/proxy-groups/rules，并重启服务（自动备份原文件）'
      : '手动粘贴会跳过 URL 拉取，直接将 YAML 内容写入配置并重启 mihomo。适用于自动拉取失败（如 TLS 握手错误）的兜底场景。';
  }
}

function clearSubYaml() {
  document.getElementById('gwYamlInput').value = '';
}

async function uploadSubYaml() {
  const yaml = document.getElementById('gwYamlInput').value.trim();
  if (!yaml) { showToast('请粘贴 YAML 配置内容'); return; }
  if (!yaml.includes('proxies:')) {
    if (!confirm('粘贴的内容中未检测到 "proxies:" 字段，可能不是有效的 Clash 配置。继续？')) return;
  }
  const btn = document.getElementById('btnUploadYaml');
  btn.disabled = true;
  const origText = btn.textContent;
  btn.textContent = '应用中…';
  try {
    const r = await fetch('/api/mihomo/sub/upload-yaml', {
      method: 'POST',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify({ yaml })
    });
    const d = await r.json();
    if (d.ok) {
      showToast('配置已应用: ' + d.proxy_count + ' 节点 · mihomo 重启中');
      document.getElementById('gwYamlInput').value = '';
      setTimeout(loadAllGw, 3000);
    } else {
      showToast('应用失败: ' + (d.error || ''));
    }
  } catch (e) { showToast('应用失败: ' + e.message); }
  btn.disabled = false;
  btn.textContent = origText;
}

async function loadRecent() {
  try {
    const r = await fetch('/api/mihomo/connections/recent?limit=12');
    const d = await r.json();
    const box = document.getElementById('gwRecent');
    if (!d.ok) { box.innerHTML = '<div class="empty">--</div>'; return; }
    const items = d.items || [];
    if (!items.length) { box.innerHTML = '<div class="empty">暂无活跃连接</div>'; return; }
    box.innerHTML = items.map(c => {
      const host = c.host + (c.port ? ':' + c.port : '');
      const isDirect = (c.chain || '').toUpperCase() === 'DIRECT' || /Direct/.test(c.chain || '');
      const chainCls = isDirect ? 'chain direct' : 'chain';
      return `<div class="conn-row">
        <span class="src">${escHtml(c.src)}</span>
        <span class="host" title="${escAttr(host)}">${escHtml(host)}</span>
        <span class="${chainCls}" title="${escAttr(c.chain)}">${escHtml(c.chain)}</span>
      </div>`;
    }).join('');
  } catch (e) { /* ignore */ }
}

function escHtml(s) {
  return String(s == null ? '' : s)
    .replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}
function escAttr(s) {
  return escHtml(s).replace(/"/g,'&quot;').replace(/'/g,'&#39;');
}

async function loadClientNames() {
  try {
    const r = await fetch('/api/clients/names');
    const d = await r.json();
    if (d.ok) gwState.clientNames = d.names || {};
  } catch (e) { /* ignore */ }
}

async function editClientName(ip) {
  const current = gwState.clientNames[ip] || '';
  const name = prompt(`为 ${ip} 设置名称:`, current);
  if (name === null) return; // cancelled
  try {
    const r = await fetch('/api/clients/names', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ip, name: name.trim() })
    });
    const d = await r.json();
    if (d.ok) {
      gwState.clientNames = d.names || {};
      loadClients();
      showToast(name.trim() ? `已保存: ${name.trim()}` : '已清除名称');
    } else {
      showToast('保存失败: ' + (d.error || ''));
    }
  } catch (e) { showToast('保存失败'); }
}

async function loadAllGw() {
  await Promise.all([loadGwStatus(), loadGroups(), loadClients(), loadRecent()]);
}

loadClientNames().then(loadAllGw);
setInterval(loadGwStatus, 3000);
setInterval(loadClients, 4000);
setInterval(loadRecent, 5000);
setInterval(loadGroups, 30000);  // groups change rarely; refresh selection state

// ── Reachability ──
let REACH_TARGETS_CACHE = [];

function reachTileHtml(t) {
  return '<div class="reach-tile" id="rt-' + t.id + '" data-id="' + t.id + '" onclick="checkOneReach(\\'' + t.id + '\\')">'
       + '<div class="ricon">' + (t.icon || '·') + '</div>'
       + '<div>'
       +   '<div class="rname">' + escHtml(t.name) + '</div>'
       +   '<div class="rmeta" id="rm-' + t.id + '">点击检测</div>'
       + '</div>'
       + '<div class="rstatus"><span class="rdot"></span><span id="rs-' + t.id + '">--</span></div>'
       + '</div>';
}

async function loadReachList() {
  try {
    const r = await fetch('/api/reach/list');
    const d = await r.json();
    if (!d.ok) return;
    REACH_TARGETS_CACHE = d.targets || [];
    const dom = REACH_TARGETS_CACHE.filter(t => t.group === 'domestic').map(reachTileHtml).join('');
    const intl = REACH_TARGETS_CACHE.filter(t => t.group === 'intl').map(reachTileHtml).join('');
    const elD = document.getElementById('reachListDomestic');
    const elI = document.getElementById('reachListIntl');
    if (elD) elD.innerHTML = dom;
    if (elI) elI.innerHTML = intl;
  } catch (e) {}
}

function applyReachResult(res) {
  if (!res || !res.id) return;
  const tile = document.getElementById('rt-' + res.id);
  const lbl  = document.getElementById('rs-' + res.id);
  const meta = document.getElementById('rm-' + res.id);
  if (!tile) return;
  tile.classList.remove('checking', 'ok', 'warn', 'fail');
  tile.classList.add(res.status);
  let txt = '';
  if (res.status === 'ok')   txt = (res.code || '200') + ' · ' + res.latency_ms + 'ms';
  else if (res.status === 'warn') txt = (res.code || '?') + ' · ' + res.latency_ms + 'ms';
  else txt = (res.error || 'fail').slice(0, 24);
  if (lbl) lbl.textContent = txt;
  if (meta) {
    const t = new Date((res.checked_at || 0) * 1000);
    const hh = String(t.getHours()).padStart(2, '0');
    const mm = String(t.getMinutes()).padStart(2, '0');
    const ss = String(t.getSeconds()).padStart(2, '0');
    meta.textContent = hh + ':' + mm + ':' + ss + ' · ' + (res.status === 'ok' ? '通' : res.status === 'warn' ? '阻' : '断');
  }
}

function setReachChecking(id) {
  const tile = document.getElementById('rt-' + id);
  const lbl  = document.getElementById('rs-' + id);
  if (tile) {
    tile.classList.remove('ok', 'warn', 'fail');
    tile.classList.add('checking');
  }
  if (lbl) lbl.textContent = '...';
}

async function checkOneReach(id) {
  setReachChecking(id);
  try {
    const r = await fetch('/api/reach/check?id=' + encodeURIComponent(id));
    const d = await r.json();
    if (d.ok) applyReachResult(d.result);
  } catch (e) {
    applyReachResult({ id: id, status: 'fail', code: 0, latency_ms: 0, error: 'request failed', checked_at: Date.now()/1000 });
  }
}

async function checkAllReach() {
  const btn = document.getElementById('reachAllBtn');
  if (btn) { btn.disabled = true; btn.textContent = '检测中...'; }
  REACH_TARGETS_CACHE.forEach(t => setReachChecking(t.id));
  try {
    const r = await fetch('/api/reach/check-all');
    const d = await r.json();
    if (d.ok) (d.results || []).forEach(applyReachResult);
  } catch (e) {}
  if (btn) { btn.disabled = false; btn.textContent = '检测全部'; }
}

// Wire up reachability: list immediately, kick off first batch shortly after.
loadReachList().then(() => { setTimeout(checkAllReach, 600); });

// ── System Stats (visibility-aware polling, no work when tab is hidden) ──
const SYS_POLL_MS = 5000;
let _sysTimer = null;
let _sysLastUpdated = 0;

function fmtUptime(s) {
  if (!s) return '--';
  const d = Math.floor(s / 86400);
  const h = Math.floor((s % 86400) / 3600);
  const m = Math.floor((s % 3600) / 60);
  if (d > 0) return d + 'd ' + h + 'h';
  if (h > 0) return h + 'h ' + m + 'm';
  return m + 'm';
}

function sysThreshold(v, warn, hot) {
  if (v == null) return 'neutral';
  if (v >= hot) return 'hot';
  if (v >= warn) return 'warm';
  return 'cool';
}

function paintSysChip(id, value, klass, tip) {
  const chip = document.getElementById(id);
  if (!chip) return;
  chip.classList.remove('cool','warm','hot','neutral');
  chip.classList.add(klass);
  const valEl = chip.querySelector('.value');
  if (valEl) valEl.textContent = value;
  if (tip != null) chip.title = tip;
}

async function loadSystemStats() {
  try {
    const r = await fetch('/api/system/stats');
    const d = await r.json();
    if (!d.ok) return;
    const s = d.stats;
    _sysLastUpdated = Date.now();

    paintSysChip('chipTemp',
      s.temp_c == null ? '--' : s.temp_c.toFixed(1) + '°C',
      sysThreshold(s.temp_c, 70, 80),
      '温度 ' + (s.temp_c == null ? 'n/a' : s.temp_c.toFixed(1) + '°C')
        + '  · throttle=' + s.throttle_raw
        + (s.throttle_history && !s.throttle_now ? '  (历史曾节流)' : '')
        + (s.throttle_now ? '  ⚠ 正在节流' : ''));

    paintSysChip('chipCpu',
      s.cpu_percent == null ? '--' : Math.round(s.cpu_percent) + '%',
      sysThreshold(s.cpu_percent, 60, 85),
      'CPU ' + (s.cpu_percent == null ? '...' : s.cpu_percent.toFixed(1) + '%')
        + '  · ' + s.cpu_count + ' 核'
        + '  · load ' + s.load_1.toFixed(2) + ' / ' + s.load_5.toFixed(2) + ' / ' + s.load_15.toFixed(2));

    paintSysChip('chipMem',
      Math.round(s.mem_percent) + '%',
      sysThreshold(s.mem_percent, 70, 90),
      '内存 ' + fmtBytes(s.mem_used) + ' / ' + fmtBytes(s.mem_total)
        + '  · 可用 ' + fmtBytes(s.mem_avail));

    paintSysChip('chipDisk',
      Math.round(s.disk_percent) + '%',
      sysThreshold(s.disk_percent, 80, 95),
      '根分区 ' + fmtBytes(s.disk_used) + ' / ' + fmtBytes(s.disk_total)
        + '  · 剩余 ' + fmtBytes(s.disk_free));

    paintSysChip('chipUptime',
      fmtUptime(s.uptime_s),
      'neutral',
      '已运行 ' + fmtUptime(s.uptime_s)
        + '  · 开机 ' + new Date(s.boot_at * 1000).toLocaleString('zh-CN'));

    // External HDD chip
    const hddChip = document.getElementById('chipHdd');
    if (hddChip) {
      if (s.hdd_mounted) {
        hddChip.style.display = '';
        paintSysChip('chipHdd',
          Math.round(s.hdd_percent) + '%',
          sysThreshold(s.hdd_percent, 80, 95),
          '移动硬盘 ' + fmtBytes(s.hdd_used) + ' / ' + fmtBytes(s.hdd_total)
            + '  · 剩余 ' + fmtBytes(s.hdd_free));
      } else {
        hddChip.style.display = 'none';
      }
    }

    const w = document.getElementById('sysWarn');
    if (w) {
      if (s.throttle_now || s.throttle_history) {
        w.textContent = '⚠ ' + (s.throttle_now ? '正在节流' : '历史曾节流') + ' (' + s.throttle_raw + ')';
        w.classList.add('show');
      } else {
        w.classList.remove('show');
      }
    }
    const m = document.getElementById('sysMeta');
    if (m) m.textContent = new Date(s.updated * 1000).toLocaleTimeString('zh-CN', { hour12: false });
  } catch (e) {}
}

function startSysPolling() {
  if (_sysTimer) return;
  loadSystemStats();
  _sysTimer = setInterval(loadSystemStats, SYS_POLL_MS);
}
function stopSysPolling() {
  if (_sysTimer) { clearInterval(_sysTimer); _sysTimer = null; }
}
document.addEventListener('visibilitychange', () => {
  if (document.visibilityState === 'visible') {
    // If we've been hidden long enough, refresh immediately
    if (Date.now() - _sysLastUpdated > SYS_POLL_MS) loadSystemStats();
    startSysPolling();
  } else {
    stopSysPolling();
  }
});

function refreshSysNow() {
  const btn = document.getElementById('sysRefresh');
  if (btn) {
    btn.classList.remove('spin');
    void btn.offsetWidth;  // restart animation
    btn.classList.add('spin');
  }
  loadSystemStats();
}

// ── Process Monitor ──
let _monProcesses = [];
let _monSortKey = 'cpu';
let _monSortDesc = true;
let _monLoading = false;

function fmtRuntime(sec) {
  if (sec == null || sec < 0) return '--';
  if (sec < 60) return sec + 's';
  const m = Math.floor(sec / 60);
  if (m < 60) return m + 'm';
  const h = Math.floor(m / 60);
  const rm = m % 60;
  if (h < 24) return h + 'h ' + rm + 'm';
  const d = Math.floor(h / 24);
  const rh = h % 24;
  return d + 'd ' + rh + 'h';
}

function renderMonTable(list) {
  const tbody = document.getElementById('monTbody');
  if (!tbody) return;
  if (!list || list.length === 0) {
    tbody.innerHTML = '<tr><td colspan="8" class="mon-empty">无匹配进程</td></tr>';
    return;
  }
  const html = list.map(p => {
    const daemonBadge = p.is_daemon
      ? (p.auto_restart
          ? '<span class="mon-badge restart" title="守护进程 · 关闭后自动拉起">守护 · 自动</span>'
          : '<span class="mon-badge daemon" title="守护进程">守护</span>')
      : '<span class="mon-badge user">普通</span>';
    const svc = p.service_name ? `<br><span style="color:var(--muted);font-size:0.68rem">${escHtml(p.service_name)}</span>` : '';
    const cmd = escHtml(p.cmdline || '');
    const name = escHtml(p.name || '');
    const cpu = p.cpu_percent != null ? p.cpu_percent.toFixed(1) + '%' : '--';
    const mem = fmtBytes(p.mem_bytes);
    const runtime = fmtRuntime(p.runtime_seconds);
    const canKill = p.pid > 1 && !p.is_daemon;
    return `<tr>
      <td class="col-pid">${p.pid}</td>
      <td class="col-name" title="${name}">${name}${svc}</td>
      <td class="col-cpu">${cpu}</td>
      <td class="col-mem">${mem}</td>
      <td class="col-runtime" title="${p.runtime_seconds != null ? p.runtime_seconds + ' 秒' : ''}">${runtime}</td>
      <td class="col-cmd" title="${cmd}">${cmd || '-'}</td>
      <td class="col-daemon">${daemonBadge}</td>
      <td class="col-act">
        <button class="mon-kill-btn" ${canKill ? '' : 'disabled'} onclick="killMonProcess(${p.pid}, '${escAttr(name)}')" title="${canKill ? '终止进程' : '系统进程/守护进程不可终止'}">Kill</button>
      </td>
    </tr>`;
  }).join('');
  tbody.innerHTML = html;
}

async function loadMonProcesses() {
  if (_monLoading) return;
  _monLoading = true;
  const pulse = document.getElementById('monPulse');
  const btn = document.getElementById('monRefreshBtn');
  if (pulse) pulse.style.display = 'inline-block';
  if (btn) btn.disabled = true;
  try {
    const r = await fetch('/api/system/processes');
    const d = await r.json();
    if (!d.ok) throw new Error(d.error || 'unknown');
    _monProcesses = d.processes || [];
    const totalEl = document.getElementById('monTotal');
    if (totalEl) totalEl.textContent = d.count || 0;
    applyMonSortAndFilter();
  } catch (e) {
    const tbody = document.getElementById('monTbody');
    if (tbody) tbody.innerHTML = `<tr><td colspan="8" class="mon-empty" style="color:var(--danger)">加载失败: ${escHtml(e.message)}</td></tr>`;
  } finally {
    _monLoading = false;
    if (pulse) pulse.style.display = 'none';
    if (btn) btn.disabled = false;
  }
}

function applyMonSortAndFilter() {
  let list = _monProcesses.slice();
  // filter
  const q = (document.getElementById('monSearch')?.value || '').trim().toLowerCase();
  if (q) {
    list = list.filter(p =>
      (p.name || '').toLowerCase().includes(q) ||
      String(p.pid).includes(q) ||
      (p.cmdline || '').toLowerCase().includes(q)
    );
  }
  // sort
  list.sort((a, b) => {
    let av, bv;
    switch (_monSortKey) {
      case 'pid': av = a.pid; bv = b.pid; break;
      case 'name': av = (a.name || '').toLowerCase(); bv = (b.name || '').toLowerCase(); break;
      case 'cpu': av = a.cpu_percent != null ? a.cpu_percent : -1; bv = b.cpu_percent != null ? b.cpu_percent : -1; break;
      case 'mem': av = a.mem_bytes || 0; bv = b.mem_bytes || 0; break;
      case 'runtime': av = a.runtime_seconds != null ? a.runtime_seconds : -1; bv = b.runtime_seconds != null ? b.runtime_seconds : -1; break;
      default: av = a.pid; bv = b.pid;
    }
    if (av < bv) return _monSortDesc ? 1 : -1;
    if (av > bv) return _monSortDesc ? -1 : 1;
    return 0;
  });
  renderMonTable(list);
  // update header arrows
  document.querySelectorAll('.mon-table th').forEach(th => {
    th.classList.remove('sort-asc', 'sort-desc');
  });
  const map = { pid: 0, name: 1, cpu: 2, mem: 3, runtime: 4 };
  const idx = map[_monSortKey];
  if (idx != null) {
    const th = document.querySelectorAll('.mon-table th')[idx];
    if (th) th.classList.add(_monSortDesc ? 'sort-desc' : 'sort-asc');
  }
}

function sortMonProcesses(key) {
  if (_monSortKey === key) {
    _monSortDesc = !_monSortDesc;
  } else {
    _monSortKey = key;
    _monSortDesc = true;
  }
  applyMonSortAndFilter();
}

function filterMonProcesses() {
  applyMonSortAndFilter();
}

async function killMonProcess(pid, name) {
  if (!confirm(`确定要终止进程 ${name} (PID ${pid}) 吗？`)) return;
  try {
    const r = await fetch(`/api/system/process/${pid}/kill`, { method: 'POST' });
    const d = await r.json();
    if (d.ok) {
      showToast(`已发送终止信号给 ${name}`);
      setTimeout(loadMonProcesses, 500);
    } else {
      showToast(`终止失败: ${d.error || '未知错误'}`);
    }
  } catch (e) {
    showToast(`终止失败: ${e.message}`);
  }
}

function refreshMonNow() {
  loadMonProcesses();
}

// Auto-refresh monitor when section is expanded
document.addEventListener('click', function(e) {
  const title = e.target.closest('.section-title');
  if (!title) return;
  const section = title.closest('.section');
  if (section && section.id === 'secMonitor' && !section.classList.contains('collapsed')) {
    if (_monProcesses.length === 0) loadMonProcesses();
  }
});

// ── Phone setup card helpers (ph_) ────────────────────────────────
async function ph_copy(btn, text) {
  let ok = false;
  try {
    await navigator.clipboard.writeText(text);
    ok = true;
  } catch (e) {
    const ta = document.createElement('textarea');
    ta.value = text;
    ta.style.position = 'fixed';
    ta.style.left = '-9999px';
    document.body.appendChild(ta);
    ta.select();
    try { ok = document.execCommand('copy'); } catch (_) {}
    document.body.removeChild(ta);
  }
  const orig = btn.textContent;
  if (ok) {
    btn.classList.add('ok');
    btn.textContent = '已复制';
    setTimeout(() => { btn.classList.remove('ok'); btn.textContent = orig; }, 1200);
    if (typeof showToast === 'function') showToast('已复制 ' + text);
  } else if (typeof showToast === 'function') {
    showToast('复制失败,请长按手动复制');
  }
}

function ph_tab(name) {
  document.querySelectorAll('.ph-tab').forEach(t => {
    t.classList.toggle('on', t.dataset.pane === name);
  });
  const targetId = 'phPane' + name.charAt(0).toUpperCase() + name.slice(1);
  document.querySelectorAll('.ph-pane').forEach(p => {
    p.classList.toggle('on', p.id === targetId);
  });
}

// ── Photo Cleaner Module ──────────────────────────────────────────
const PhotoState = {
  mode: 'auto',
  imageBlob: null,
  resultBlob: null,
  maskHistory: [],
  maskInited: false,
  drawing: false,
  lastX: 0, lastY: 0,
  controller: null,
};

async function loadPhotoProviders() {
  const sel = document.getElementById('photoProvider');
  if (!sel) return;
  const warn = document.getElementById('photoNoProvider');
  try {
    const r = await fetch('/api/photo/providers');
    if (!r.ok) throw new Error('HTTP ' + r.status);
    const arr = await r.json();
    sel.innerHTML = '';
    let firstAvail = null;
    arr.forEach(p => {
      const opt = document.createElement('option');
      opt.value = p.name;
      opt.textContent = p.label + (p.available ? '' : ' (未配置)');
      opt.disabled = !p.available;
      if (p.available && !firstAvail) firstAvail = p.name;
      sel.appendChild(opt);
    });
    if (firstAvail) sel.value = firstAvail;
    if (!firstAvail) {
      warn.style.display = 'block';
      sel.disabled = true;
    } else {
      warn.style.display = 'none';
      sel.disabled = false;
    }
  } catch (e) {
    sel.innerHTML = '<option>加载失败</option>';
    warn.textContent = '⚠ 无法连接 photo-cleaner 服务: ' + e.message;
    warn.style.display = 'block';
  }
}

function selectPhotoMode(m) {
  PhotoState.mode = m;
  document.querySelectorAll('.photo-tab').forEach(t => {
    t.classList.toggle('active', t.dataset.mode === m);
  });
  const tools = document.getElementById('photoMaskTools');
  const canvas = document.getElementById('photoMaskCanvas');
  const hint = document.getElementById('photoModeHint');
  const hasImage = !!PhotoState.imageBlob;
  if (m === 'mask') {
    if (hasImage) tools.style.display = 'flex';
    canvas.style.pointerEvents = 'auto';
    if (hint) hint.textContent = '在原图上涂抹要擦除的区域';
    if (hasImage) initMaskCanvasIfNeeded();
  } else {
    tools.style.display = 'none';
    canvas.style.pointerEvents = 'none';
    if (hint) hint.textContent = '';
  }
}

// ── Daily News ──
async function loadDailyNews() {
  const list = document.getElementById('newsList');
  if (!list) return;
  try {
    const r = await fetch('/api/daily-news');
    const data = await r.json();
    if (!data.items || data.items.length === 0) {
      list.innerHTML = '<div class="mon-empty">暂无每日摘要</div>';
      return;
    }
    list.innerHTML = data.items.map(item => {
      const date = item.date;
      return `<div class="news-item">
        <div class="news-info">
          <div class="news-title">${item.title}</div>
          <div class="news-meta">${date} · ${item.category || '综合'}</div>
        </div>
        <div class="news-actions">
          <button class="btn btn-mini" onclick="viewDailyNews('${item.filename}')">查看</button>
          <a class="btn btn-mini" href="/api/daily-news/download/${item.filename}" download>下载</a>
        </div>
      </div>`;
    }).join('');
  } catch (e) {
    list.innerHTML = '<div class="mon-empty">加载失败</div>';
  }
}

function viewDailyNews(filename) {
  window.open('/api/daily-news/view/' + filename, '_blank');
}

function setupPhotoUpload() {
  const dz = document.getElementById('photoDropzone');
  const fi = document.getElementById('photoFileInput');
  if (!dz || !fi) return;
  dz.addEventListener('click', () => fi.click());
  fi.addEventListener('change', () => {
    if (fi.files && fi.files[0]) loadPhotoFile(fi.files[0]);
  });
  ['dragenter','dragover'].forEach(ev => dz.addEventListener(ev, e => {
    e.preventDefault(); dz.classList.add('dragover');
  }));
  ['dragleave','drop'].forEach(ev => dz.addEventListener(ev, e => {
    e.preventDefault(); dz.classList.remove('dragover');
  }));
  dz.addEventListener('drop', e => {
    e.preventDefault();
    if (e.dataTransfer.files && e.dataTransfer.files[0]) loadPhotoFile(e.dataTransfer.files[0]);
  });
}

function loadPhotoFile(file) {
  if (!file.type || !file.type.startsWith('image/')) {
    showToast('只支持图片文件');
    return;
  }
  if (file.size > 50 * 1024 * 1024) {
    showToast('图片超过 50MB 限制');
    return;
  }
  const reader = new FileReader();
  reader.onload = e => {
    PhotoState.imageBlob = file;
    PhotoState.resultBlob = null;
    PhotoState.maskHistory = [];
    PhotoState.maskInited = false;
    document.getElementById('photoSrcImg').src = e.target.result;
    document.getElementById('photoWorkspace').style.display = 'grid';
    document.getElementById('photoResultWrap').innerHTML = '<div class="photo-placeholder">点击「开始处理」</div>';
    document.getElementById('photoDownloadBtn').style.display = 'none';
    document.getElementById('photoActions').style.display = 'flex';
    document.getElementById('photoPromptWrap').style.display = 'block';
    if (PhotoState.mode === 'mask') {
      document.getElementById('photoMaskTools').style.display = 'flex';
      initMaskCanvasIfNeeded();
    }
  };
  reader.readAsDataURL(file);
}

function initMaskCanvasIfNeeded() {
  const img = document.getElementById('photoSrcImg');
  const canvas = document.getElementById('photoMaskCanvas');
  if (!img.src || !img.complete || !img.naturalWidth) {
    img.addEventListener('load', () => initMaskCanvasIfNeeded(), {once: true});
    return;
  }
  if (canvas.width !== img.naturalWidth || canvas.height !== img.naturalHeight) {
    canvas.width = img.naturalWidth;
    canvas.height = img.naturalHeight;
  }
  const ctx = canvas.getContext('2d');
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  PhotoState.maskHistory = [ctx.getImageData(0, 0, canvas.width, canvas.height)];
  if (!PhotoState.maskInited) {
    bindMaskCanvas();
    PhotoState.maskInited = true;
  }
  const sizeIn = document.getElementById('photoBrushSize');
  const sizeVal = document.getElementById('photoBrushSizeVal');
  sizeIn.oninput = () => { sizeVal.textContent = sizeIn.value; };
}

function _maskPos(canvas, e) {
  const rect = canvas.getBoundingClientRect();
  const sx = canvas.width / rect.width;
  const sy = canvas.height / rect.height;
  const cx = (e.touches ? e.touches[0].clientX : e.clientX) - rect.left;
  const cy = (e.touches ? e.touches[0].clientY : e.clientY) - rect.top;
  return [cx * sx, cy * sy];
}

function bindMaskCanvas() {
  const canvas = document.getElementById('photoMaskCanvas');
  const start = e => {
    if (PhotoState.mode !== 'mask') return;
    e.preventDefault();
    PhotoState.drawing = true;
    [PhotoState.lastX, PhotoState.lastY] = _maskPos(canvas, e);
    const ctx = canvas.getContext('2d');
    PhotoState.maskHistory.push(ctx.getImageData(0, 0, canvas.width, canvas.height));
    if (PhotoState.maskHistory.length > 24) PhotoState.maskHistory.shift();
    drawDot(ctx, PhotoState.lastX, PhotoState.lastY);
  };
  const move = e => {
    if (!PhotoState.drawing || PhotoState.mode !== 'mask') return;
    e.preventDefault();
    const [x, y] = _maskPos(canvas, e);
    const ctx = canvas.getContext('2d');
    const sizeCss = parseInt(document.getElementById('photoBrushSize').value, 10);
    const rect = canvas.getBoundingClientRect();
    const lw = sizeCss * (canvas.width / Math.max(1, rect.width));
    ctx.strokeStyle = 'rgba(255,40,80,0.55)';
    ctx.fillStyle = 'rgba(255,40,80,0.55)';
    ctx.lineWidth = lw;
    ctx.lineCap = 'round';
    ctx.lineJoin = 'round';
    ctx.beginPath();
    ctx.moveTo(PhotoState.lastX, PhotoState.lastY);
    ctx.lineTo(x, y);
    ctx.stroke();
    PhotoState.lastX = x; PhotoState.lastY = y;
  };
  const end = () => { PhotoState.drawing = false; };
  canvas.addEventListener('mousedown', start);
  canvas.addEventListener('mousemove', move);
  canvas.addEventListener('mouseup', end);
  canvas.addEventListener('mouseleave', end);
  canvas.addEventListener('touchstart', start, {passive: false});
  canvas.addEventListener('touchmove', move, {passive: false});
  canvas.addEventListener('touchend', end);
}

function drawDot(ctx, x, y) {
  const sizeCss = parseInt(document.getElementById('photoBrushSize').value, 10);
  const canvas = document.getElementById('photoMaskCanvas');
  const rect = canvas.getBoundingClientRect();
  const r = (sizeCss * (canvas.width / Math.max(1, rect.width))) / 2;
  ctx.fillStyle = 'rgba(255,40,80,0.55)';
  ctx.beginPath();
  ctx.arc(x, y, r, 0, Math.PI * 2);
  ctx.fill();
}

function undoMask() {
  if (PhotoState.maskHistory.length <= 1) return;
  PhotoState.maskHistory.pop();
  const last = PhotoState.maskHistory[PhotoState.maskHistory.length - 1];
  const canvas = document.getElementById('photoMaskCanvas');
  canvas.getContext('2d').putImageData(last, 0, 0);
}

function clearMask() {
  const canvas = document.getElementById('photoMaskCanvas');
  const ctx = canvas.getContext('2d');
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  PhotoState.maskHistory = [ctx.getImageData(0, 0, canvas.width, canvas.height)];
}

function buildMaskBlob() {
  return new Promise(resolve => {
    const src = document.getElementById('photoMaskCanvas');
    const w = src.width, h = src.height;
    const off = document.createElement('canvas');
    off.width = w; off.height = h;
    const ctx = off.getContext('2d');
    ctx.fillStyle = '#000';
    ctx.fillRect(0, 0, w, h);
    const srcCtx = src.getContext('2d');
    const data = srcCtx.getImageData(0, 0, w, h).data;
    const out = ctx.getImageData(0, 0, w, h);
    let painted = 0;
    for (let i = 0; i < data.length; i += 4) {
      if (data[i+3] > 12) {
        out.data[i] = 255; out.data[i+1] = 255;
        out.data[i+2] = 255; out.data[i+3] = 255;
        painted++;
      }
    }
    ctx.putImageData(out, 0, 0);
    if (painted < 30) { resolve(null); return; }
    off.toBlob(b => resolve(b), 'image/png');
  });
}

async function submitPhoto() {
  if (!PhotoState.imageBlob) {
    showToast('请先选择图片');
    return;
  }
  const sel = document.getElementById('photoProvider');
  const provider = sel.value;
  if (!provider || sel.disabled) {
    showToast('没有可用的 Provider,请先配置 API Key');
    return;
  }
  const fd = new FormData();
  fd.append('image', PhotoState.imageBlob);
  fd.append('mode', PhotoState.mode);
  fd.append('provider', provider);
  const prompt = document.getElementById('photoPrompt').value.trim();
  if (prompt) fd.append('prompt', prompt);
  const original = document.getElementById('photoOriginal').checked;
  if (original) fd.append('compress', 'false');
  if (PhotoState.mode === 'mask') {
    const maskBlob = await buildMaskBlob();
    if (!maskBlob) {
      showToast('请先涂抹要擦除的区域');
      return;
    }
    fd.append('mask', maskBlob, 'mask.png');
  }
  const btn = document.getElementById('photoSubmitBtn');
  let pulse = document.getElementById('photoPulse');
  const resultWrap = document.getElementById('photoResultWrap');

  if (PhotoState.controller) {
    PhotoState.controller.abort();
    PhotoState.controller = null;
    btn.innerHTML = '<span id="photoPulse" style="display:none" class="speed-pulse"></span>开始处理';
    pulse = document.getElementById('photoPulse');
    btn.disabled = false;
    showToast('已取消');
    return;
  }

  PhotoState.controller = new AbortController();
  const ctrl = PhotoState.controller;
  btn.innerHTML = '<span id="photoPulse" style="display:inline-block" class="speed-pulse"></span>停止';
  btn.disabled = false;
  resultWrap.innerHTML =
    '<div class="photo-placeholder" id="photoTimer"><div class="photo-step">1/4 上传图片…</div><div class="photo-step-time">0s</div></div>';
  document.getElementById('photoDownloadBtn').style.display = 'none';

  const timerEl = document.getElementById('photoTimer');
  let elapsed = 0;
  const STEPS = [
    { t: 0,  text: '1/4 上传图片…' },
    { t: 3,  text: '2/4 分析画面内容…' },
    { t: 8,  text: '3/4 生成编辑结果…' },
    { t: 18, text: '4/4 优化细节…' },
  ];
  const timerId = setInterval(() => {
    elapsed++;
    const step = STEPS.slice().reverse().find(s => elapsed >= s.t);
    if (timerEl) {
      timerEl.innerHTML = '<div class="photo-step">' + (step ? step.text : '处理中…') + '</div><div class="photo-step-time">' + elapsed + 's</div>';
    }
  }, 1000);

  const timeoutId = setTimeout(() => ctrl.abort(), 120000);

  try {
    const r = await fetch('/api/photo/edit', { method: 'POST', body: fd, signal: ctrl.signal });
    clearTimeout(timeoutId);
    clearInterval(timerId);
    if (!r.ok) {
      let msg = 'HTTP ' + r.status;
      try {
        const ct = r.headers.get('content-type') || '';
        if (ct.includes('json')) {
          const j = await r.json();
          msg = j.error || msg;
        } else {
          msg = await r.text();
        }
      } catch (_) {}
      throw new Error(msg);
    }
    const blob = await r.blob();
    PhotoState.resultBlob = blob;
    const url = URL.createObjectURL(blob);
    resultWrap.innerHTML = '<img src="' + url + '" alt="result">';
    document.getElementById('photoDownloadBtn').style.display = 'inline-flex';
    showToast('处理完成');
  } catch (e) {
    clearTimeout(timeoutId);
    clearInterval(timerId);
    if (e.name === 'AbortError') {
      resultWrap.innerHTML = '<div class="photo-placeholder">已取消</div>';
    } else {
      resultWrap.innerHTML =
        '<div class="photo-placeholder" style="color:var(--danger)">失败: ' +
        String(e.message).replace(/[<>&]/g, c => ({'<':'&lt;','>':'&gt;','&':'&amp;'}[c])) +
        '</div>';
      showToast('处理失败: ' + e.message);
    }
  } finally {
    PhotoState.controller = null;
    btn.innerHTML = '<span id="photoPulse" style="display:none" class="speed-pulse"></span>开始处理';
  }
}

function downloadPhoto() {
  if (!PhotoState.resultBlob) return;
  const url = URL.createObjectURL(PhotoState.resultBlob);
  const a = document.createElement('a');
  a.href = url;
  a.download = 'cleaned-' + Date.now() + '.png';
  document.body.appendChild(a);
  a.click();
  setTimeout(() => { URL.revokeObjectURL(url); a.remove(); }, 1500);
}

function resetPhoto() {
  PhotoState.imageBlob = null;
  PhotoState.resultBlob = null;
  PhotoState.maskHistory = [];
  PhotoState.maskInited = false;
  document.getElementById('photoFileInput').value = '';
  document.getElementById('photoSrcImg').src = '';
  document.getElementById('photoWorkspace').style.display = 'none';
  document.getElementById('photoMaskTools').style.display = 'none';
  document.getElementById('photoActions').style.display = 'none';
  document.getElementById('photoPromptWrap').style.display = 'none';
  document.getElementById('photoDownloadBtn').style.display = 'none';
  document.getElementById('photoPrompt').value = '';
  selectPhotoMode('auto');
}

loadPhotoProviders();
setupPhotoUpload();
loadDailyNews();

if (document.visibilityState === 'visible') {
  startSysPolling();
  startPcPolling();
}
</script>
</body>
</html>"""

# ── Main ────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 50)
    print("LAN Share Server - Startup Check")
    print("=" * 50)
    ok, checks = self_check()
    for name, status, detail in checks:
        icon = "[OK]" if status == "OK" else ("[WARN]" if status == "WARN" else "[FAIL]")
        print(f"  {icon} {name:6s} {status:5s} {detail}")
    if not ok:
        print("Startup checks FAILED. Exiting.")
        sys.exit(1)

    t = threading.Thread(target=cleaner_loop, daemon=True)
    t.start()

    # Start the per-client byte tracker so cumulative numbers are accurate
    # from the moment NebulaShare comes online (not just after the first
    # /api/mihomo/clients call).
    _ensure_clients_poller()

    ips = get_local_ips()
    print("-" * 50)
    print("Server running at:")
    for ip in ips:
        print(f"  http://{ip}:{PORT}")
    print("-" * 50)
    print("Press Ctrl+C to stop.")

    app.run(host="0.0.0.0", port=PORT, threaded=True)
