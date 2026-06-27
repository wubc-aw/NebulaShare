# 客户端级代理规则覆盖 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 Network Hub 增加按客户端展示真实链路的面板，并支持客户端级规则覆盖（全局规则为默认，客户端覆盖优先级更高）。

**Architecture:** 后端读取 mihomo 活跃连接按 sourceIP 聚合出每个客户端的主链路与规则命中；客户端覆盖规则以 `AND,((SRC-IP-CIDR,<ip>/32),(DOMAIN-SUFFIX,<pattern>)),<target>` 形式注入 `/etc/mihomo/config.yaml` 的 rules 列表最前；前端新增折叠面板展示并编辑覆盖规则。

**Tech Stack:** Python Flask (backend), React + TypeScript + Tailwind (frontend), PyYAML, mihomo external-controller API.

## Global Constraints

- mihomo 当前版本 v1.19.24，运行在 `rule` 模式，TUN 开启。
- 覆盖规则仅使用 `DOMAIN-SUFFIX` 类型，生成 `AND` 逻辑规则并插入全局规则之前。
- 配置修改前必须备份 `/etc/mihomo/config.yaml`；失败自动回滚。
- 与现有代码风格保持一致：`app.py` 中复用 `load_mihomo_state` / `save_mihomo_state`。
- 前端组件放在 `nebula-share-frontend/components/network-hub/` 目录下。
- 每次任务结束提交一次，commit message 遵循现有风格。

---

## File Structure

| 文件 | 责任 |
|---|---|
| `app.py` | 新增状态读写、配置注入、备份/重载、两个新 API 端点 |
| `tests/test_client_routes.py` | `_inject_client_overrides` 等纯函数的单元测试 |
| `nebula-share-frontend/components/network-hub/client-routes.tsx` | 客户端路由折叠面板组件 |
| `nebula-share-frontend/components/network-hub.tsx` | 集成 ClientRoutes，新增状态和 API 调用 |

---

### Task 1: 添加客户端覆盖规则的状态存储

**Files:**
- Modify: `app.py`（在 `load_mihomo_state` / `save_mihomo_state` 附近）
- Test: `tests/test_client_routes.py`（新增）

**Interfaces:**
- Consumes: 现有 `MIHOMO_STATE_FILE` 路径和 JSON 文件格式。
- Produces: `client_route_overrides` 作为 state dict 的键，默认值 `{}`。

- [ ] **Step 1: 写失败测试**

```python
# tests/test_client_routes.py
import os
import json
import tempfile
from pathlib import Path


def test_load_mihomo_state_initializes_client_route_overrides():
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        f.write('{}')
        path = f.name
    try:
        os.environ['NEBULA_STATE_DIR'] = str(Path(path).parent)
        from app import load_mihomo_state, save_mihomo_state
        state = load_mihomo_state()
        assert state.get('client_route_overrides') == {}
        state['client_route_overrides'] = {'192.168.50.141': {'plex.tv': 'AI'}}
        save_mihomo_state(state)
        with open(path, 'r', encoding='utf-8') as f:
            saved = json.load(f)
        assert saved['client_route_overrides']['192.168.50.141']['plex.tv'] == 'AI'
    finally:
        os.unlink(path)
```

- [ ] **Step 2: 运行测试，确认失败**

```bash
cd /home/aw/vibeProjects/NebulaShare
python -m pytest tests/test_client_routes.py -v
```

Expected: FAIL（`client_route_overrides` 不存在或 load_mihomo_state 没有默认初始化）。

- [ ] **Step 3: 实现最小改动**

在 `app.py` 中找到 `load_mihomo_state()` 函数，在返回前初始化缺省字段：

```python
def load_mihomo_state():
    ...  # 保持原有实现
    state.setdefault("client_names", {})
    state.setdefault("client_route_overrides", {})  # 新增
    return state
```

- [ ] **Step 4: 运行测试，确认通过**

```bash
python -m pytest tests/test_client_routes.py::test_load_mihomo_state_initializes_client_route_overrides -v
```

Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add app.py tests/test_client_routes.py
git commit -m "feat(client-routes): initialize client_route_overrides in state"
```

---

### Task 2: 实现配置注入函数 `_inject_client_overrides`

**Files:**
- Modify: `app.py`
- Test: `tests/test_client_routes.py`

**Interfaces:**
- Consumes: `client_route_overrides` dict；config dict（从 yaml 加载）。
- Produces: 修改后的 config dict，rules 列表最前插入 AND 规则。

- [ ] **Step 1: 写失败测试**

```python
# tests/test_client_routes.py
from app import _inject_client_overrides


def test_inject_client_overrides_creates_rules():
    config = {'rules': ['DOMAIN-SUFFIX,google.com,Proxy', 'MATCH,Final']}
    overrides = {'192.168.50.141': {'plex.tv': 'AI'}}
    result = _inject_client_overrides(config, overrides)
    assert len(result['rules']) == 3
    assert result['rules'][0] == 'AND,((SRC-IP-CIDR,192.168.50.141/32),(DOMAIN-SUFFIX,plex.tv)),AI'
    assert result['rules'][1] == 'DOMAIN-SUFFIX,google.com,Proxy'
    assert result['rules'][2] == 'MATCH,Final'


def test_inject_client_overrides_creates_rules_list_if_missing():
    config = {}
    overrides = {'192.168.50.141': {'plex.tv': 'AI'}}
    result = _inject_client_overrides(config, overrides)
    assert result['rules'][0] == 'AND,((SRC-IP-CIDR,192.168.50.141/32),(DOMAIN-SUFFIX,plex.tv)),AI'


def test_inject_client_overrides_removes_old_and_rules():
    config = {'rules': [
        'AND,((SRC-IP-CIDR,192.168.50.141/32),(DOMAIN-SUFFIX,old.tv)),Old',
        'MATCH,Final'
    ]}
    overrides = {'192.168.50.141': {'plex.tv': 'AI'}}
    result = _inject_client_overrides(config, overrides)
    assert all('old.tv' not in r for r in result['rules'])
    assert result['rules'][0] == 'AND,((SRC-IP-CIDR,192.168.50.141/32),(DOMAIN-SUFFIX,plex.tv)),AI'
```

- [ ] **Step 2: 运行测试，确认失败**

```bash
python -m pytest tests/test_client_routes.py -v
```

Expected: FAIL（`_inject_client_overrides` 未定义）。

- [ ] **Step 3: 实现函数**

在 `app.py` 中新增：

```python
import yaml


def _inject_client_overrides(config, overrides):
    """把 client_route_overrides 转成 AND 逻辑规则，插到 rules 最前面。

    overrides: { ip: { pattern: target_group, ... }, ... }
    """
    rules = config.get("rules") or []
    cleaned = [
        r for r in rules
        if not (isinstance(r, str) and r.startswith("AND,((SRC-IP-CIDR,"))
    ]
    injected = []
    for ip, patterns in overrides.items():
        for pattern, target in patterns.items():
            injected.append(
                f"AND,((SRC-IP-CIDR,{ip}/32),(DOMAIN-SUFFIX,{pattern})),{target}"
            )
    config["rules"] = injected + cleaned
    return config
```

- [ ] **Step 4: 运行测试，确认通过**

```bash
python -m pytest tests/test_client_routes.py -v
```

Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add app.py tests/test_client_routes.py
git commit -m "feat(client-routes): add _inject_client_overrides helper"
```

---

### Task 3: 实现配置备份与热重载 `_apply_mihomo_config`

**Files:**
- Modify: `app.py`
- Test: `tests/test_client_routes.py`

**Interfaces:**
- Consumes: config dict；`MIHOMO_CONFIG` 路径；`mihomo_put` 辅助函数。
- Produces: 成功时无返回值；失败时抛出异常并恢复备份。

- [ ] **Step 1: 写失败测试**

```python
# tests/test_client_routes.py
from unittest.mock import patch
import tempfile
from pathlib import Path


def test_apply_mihomo_config_backup_and_writes():
    with tempfile.TemporaryDirectory() as tmp:
        config_path = Path(tmp) / 'config.yaml'
        config_path.write_text('rules:\n  - MATCH,Final\n', encoding='utf-8')
        config = {'rules': ['AND,((SRC-IP-CIDR,192.168.50.141/32),(DOMAIN-SUFFIX,plex.tv)),AI', 'MATCH,Final']}
        with patch('app.MIHOMO_CONFIG', str(config_path)):
            with patch('app.mihomo_put') as mock_put:
                from app import _apply_mihomo_config
                _apply_mihomo_config(config)
                assert 'DOMAIN-SUFFIX,plex.tv' in config_path.read_text(encoding='utf-8')
                backups = list(Path(tmp).glob('config.yaml.bak.*'))
                assert len(backups) == 1
                assert 'MATCH,Final' in backups[0].read_text(encoding='utf-8')
                mock_put.assert_called_once()


def test_apply_mihomo_config_rollback_on_failure():
    with tempfile.TemporaryDirectory() as tmp:
        config_path = Path(tmp) / 'config.yaml'
        original = 'rules:\n  - MATCH,Final\n'
        config_path.write_text(original, encoding='utf-8')
        config = {'rules': ['AND,((SRC-IP-CIDR,192.168.50.141/32),(DOMAIN-SUFFIX,plex.tv)),AI', 'MATCH,Final']}
        with patch('app.MIHOMO_CONFIG', str(config_path)):
            with patch('app.mihomo_put', side_effect=RuntimeError('reload failed')):
                from app import _apply_mihomo_config
                try:
                    _apply_mihomo_config(config)
                except RuntimeError:
                    pass
                assert config_path.read_text(encoding='utf-8') == original
```

- [ ] **Step 2: 运行测试，确认失败**

```bash
python -m pytest tests/test_client_routes.py -v
```

Expected: FAIL（`_apply_mihomo_config` 未定义）。

- [ ] **Step 3: 实现函数**

在 `app.py` 中新增：

```python
import shutil
from datetime import datetime


def _apply_mihomo_config(config):
    """备份、写入、热重载 mihomo 配置；失败则回滚。"""
    path = MIHOMO_CONFIG
    backup_path = f"{path}.bak.{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    shutil.copy2(path, backup_path)
    try:
        with open(path, 'w', encoding='utf-8') as f:
            yaml.safe_dump(config, f, sort_keys=False, allow_unicode=True)
        try:
            mihomo_put("/configs/reload", {})
        except Exception:
            mihomo_put("/configs", {})
    except Exception:
        shutil.copy2(backup_path, path)
        raise
```

- [ ] **Step 4: 运行测试，确认通过**

```bash
python -m pytest tests/test_client_routes.py -v
```

Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add app.py tests/test_client_routes.py
git commit -m "feat(client-routes): add config backup/reload helper"
```

---

### Task 4: 实现 GET /api/clients/routes

**Files:**
- Modify: `app.py`

**Interfaces:**
- Consumes: mihomo `/connections`，`/proxies`；`client_route_overrides`；`client_names`。
- Produces: JSON `{ ok: true, clients: [...], global_rules: [...] }`。

- [ ] **Step 1: 实现端点**

在 `app.py` 中，放在 `/api/mihomo/clients` 之后：

```python
@app.route("/api/clients/routes")
def client_routes():
    """Return per-client routing view: current chains, global rules, and overrides."""
    snap = mihomo_get("/connections", timeout=3)
    conns = (snap or {}).get("connections") or []

    meta_by_ip = {}
    for c in conns:
        meta = c.get("metadata") or {}
        ip = meta.get("sourceIP") or "?"
        e = meta_by_ip.setdefault(ip, {
            "count": 0, "rules": {}, "chains": {}, "host_recent": "",
        })
        e["count"] += 1
        rk = c.get("rule") or "?"
        e["rules"][rk] = e["rules"].get(rk, 0) + 1
        ch = " -> ".join(reversed(c.get("chains") or [])) or "DIRECT"
        e["chains"][ch] = e["chains"].get(ch, 0) + 1
        host = meta.get("host") or meta.get("destinationIP") or ""
        if host and not e["host_recent"]:
            e["host_recent"] = host

    state = load_mihomo_state()
    overrides = state.get("client_route_overrides") or {}
    names = state.get("client_names") or {}

    proxies_data = mihomo_get("/proxies", timeout=4) or {}
    proxies = proxies_data.get("proxies") or {}
    global_rules = []
    for name, v in proxies.items():
        t = v.get("type")
        if t not in ("Selector", "URLTest", "Fallback", "LoadBalance"):
            continue
        global_rules.append({
            "name": name,
            "type": t,
            "target": v.get("now") or "-",
        })

    clients_out = []
    for ip in set(meta_by_ip.keys()):
        m = meta_by_ip[ip]
        top_chain = max(m["chains"].items(), key=lambda x: x[1])[0] if m["chains"] else "?"
        top_node = top_chain.split(" -> ")[-1] if " -> " in top_chain else top_chain
        clients_out.append({
            "ip": ip,
            "name": names.get(ip) or "",
            "primary_chain": top_chain,
            "primary_node": top_node,
            "connections": m["count"],
            "rules_hit": m["rules"],
            "host_recent": m["host_recent"],
            "overrides": overrides.get(ip) or {},
        })
    clients_out.sort(key=lambda x: -x["connections"])

    return jsonify({"ok": True, "clients": clients_out, "global_rules": global_rules})
```

- [ ] **Step 2: 手动测试**

```bash
curl -s http://127.0.0.1:5000/api/clients/routes | python3 -m json.tool
```

Expected: 返回 JSON，包含电视 IP（192.168.50.141）的 `primary_chain`、`overrides` 为空、`global_rules` 包含 ✈️Final、AI 等组。

- [ ] **Step 3: 提交**

```bash
git add app.py
git commit -m "feat(client-routes): add GET /api/clients/routes endpoint"
```

---

### Task 5: 实现 POST /api/clients/routes

**Files:**
- Modify: `app.py`

**Interfaces:**
- Consumes: JSON `{ ip, overrides }`；`_inject_client_overrides`；`_apply_mihomo_config`。
- Produces: JSON `{ ok: true }` 或 `{ ok: false, error: ... }`。

- [ ] **Step 1: 实现端点**

在 `app.py` 中，放在 GET `/api/clients/routes` 之后：

```python
@app.route("/api/clients/routes", methods=["POST"])
def client_routes_post():
    body = request.get_json(silent=True) or {}
    ip = (body.get("ip") or "").strip()
    overrides = body.get("overrides") or {}

    if not ip:
        return jsonify({"ok": False, "error": "ip required"}), 400
    if not isinstance(overrides, dict):
        return jsonify({"ok": False, "error": "overrides must be an object"}), 400

    for pattern, target in overrides.items():
        if not pattern or not isinstance(target, str) or not target.strip():
            return jsonify({"ok": False, "error": f"invalid override for {pattern}"}), 400

    state = load_mihomo_state()
    state.setdefault("client_route_overrides", {})
    if overrides:
        state["client_route_overrides"][ip] = overrides
    else:
        state["client_route_overrides"].pop(ip, None)
    save_mihomo_state(state)

    try:
        with open(MIHOMO_CONFIG, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f) or {}
        config = _inject_client_overrides(config, state["client_route_overrides"])
        _apply_mihomo_config(config)
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

    return jsonify({"ok": True})
```

- [ ] **Step 2: 手动测试（先读配置确认无覆盖）**

```bash
curl -s -X POST http://127.0.0.1:5000/api/clients/routes \
  -H 'Content-Type: application/json' \
  -d '{"ip":"192.168.50.141","overrides":{"plex.tv":"AI"}}' | python3 -m json.tool

grep -n "SRC-IP-CIDR" /etc/mihomo/config.yaml
```

Expected: 配置顶部出现 `AND,((SRC-IP-CIDR,192.168.50.141/32),(DOMAIN-SUFFIX,plex.tv)),AI`。

- [ ] **Step 3: 提交**

```bash
git add app.py
git commit -m "feat(client-routes): add POST /api/clients/routes endpoint"
```

---

### Task 6: 创建前端 ClientRoutes 组件

**Files:**
- Create: `nebula-share-frontend/components/network-hub/client-routes.tsx`

**Interfaces:**
- Consumes: `clients`（来自 `/api/mihomo/clients`）、`groups`（来自 `/api/mihomo/groups`）、`routesData`（来自 `/api/clients/routes`）、`onSave(ip, overrides)`。
- Produces: 折叠面板 UI，触发保存时调用 `onSave`。

- [ ] **Step 1: 创建组件**

```tsx
"use client"

import { useState } from "react"
import { ChevronDown, Plus, Trash2, Save } from "lucide-react"
import { cn } from "@/lib/utils"

interface ClientRouteData {
  ip: string
  name: string
  primary_chain: string
  primary_node: string
  connections: number
  rules_hit: Record<string, number>
  host_recent: string
  overrides: Record<string, string>
}

interface GlobalRule {
  name: string
  type: string
  target: string
}

interface ClientRoutesProps {
  clients: any[]
  groups: any[]
  routesData: { clients: ClientRouteData[]; global_rules: GlobalRule[] } | null
  onSave: (ip: string, overrides: Record<string, string>) => Promise<void>
}

function getNodeColor(name: string) {
  if (name.includes("DIRECT")) return "text-success"
  if (name.includes("🇭🇰")) return "text-amber-400"
  if (name.includes("🇸🇬")) return "text-emerald-400"
  if (name.includes("🇺🇸")) return "text-blue-400"
  return "text-primary"
}

export function ClientRoutes({ clients, groups, routesData, onSave }: ClientRoutesProps) {
  const [expanded, setExpanded] = useState<Set<string>>(new Set())
  const [editing, setEditing] = useState<Record<string, Record<string, string>>>({})
  const [saving, setSaving] = useState<string | null>(null)

  const toggle = (ip: string) => {
    const next = new Set(expanded)
    if (next.has(ip)) next.delete(ip)
    else next.add(ip)
    setExpanded(next)
  }

  const handleAdd = (ip: string) => {
    setEditing((prev) => ({
      ...prev,
      [ip]: { ...prev[ip], "": groups[0]?.name || "" },
    }))
  }

  const handleChange = (ip: string, oldPattern: string, field: "pattern" | "target", value: string) => {
    setEditing((prev) => {
      const copy = { ...prev[ip] }
      if (field === "pattern") {
        const target = copy[oldPattern]
        delete copy[oldPattern]
        copy[value] = target
      } else {
        copy[oldPattern] = value
      }
      return { ...prev, [ip]: copy }
    })
  }

  const handleDelete = (ip: string, pattern: string) => {
    setEditing((prev) => {
      const copy = { ...prev[ip] }
      delete copy[pattern]
      return { ...prev, [ip]: copy }
    })
  }

  const handleSave = async (ip: string, currentOverrides: Record<string, string>) => {
    setSaving(ip)
    try {
      const overrides = editing[ip] ?? currentOverrides
      const cleaned: Record<string, string> = {}
      for (const [k, v] of Object.entries(overrides)) {
        if (k.trim() && v.trim()) cleaned[k.trim()] = v.trim()
      }
      await onSave(ip, cleaned)
      setEditing((prev) => ({ ...prev, [ip]: {} }))
    } finally {
      setSaving(null)
    }
  }

  const clientMap = new Map((routesData?.clients || []).map((c) => [c.ip, c]))

  return (
    <div className="card-premium p-4">
      <div className="flex items-center gap-2 mb-4">
        <h3 className="text-sm font-semibold">客户端路由</h3>
        <span className="text-xs text-muted-foreground font-mono bg-secondary/50 px-2 py-0.5 rounded-md">
          {routesData?.clients.length || 0}
        </span>
      </div>
      <p className="text-xs text-muted-foreground mb-4">
        全局规则为默认；客户端覆盖规则优先级更高，仅对指定设备生效。
      </p>

      <div className="flex flex-col gap-3">
        {clients.length === 0 ? (
          <p className="text-sm text-muted-foreground">暂无活动客户端</p>
        ) : (
          clients.map((client) => {
            const ip = client.ip
            const route = clientMap.get(ip)
            const isExpanded = expanded.has(ip)
            const overrides = editing[ip] ?? route?.overrides ?? {}
            return (
              <div key={ip} className="rounded-xl bg-secondary/20 overflow-hidden">
                <button
                  onClick={() => toggle(ip)}
                  className="w-full flex items-center justify-between px-4 py-3 text-left hover:bg-secondary/30 transition-colors"
                >
                  <div className="flex items-center gap-3 min-w-0">
                    <div className="w-8 h-8 rounded-lg bg-secondary/50 flex items-center justify-center shrink-0">
                      <span className="text-xs font-mono font-semibold">{ip.split('.').pop()}</span>
                    </div>
                    <div className="min-w-0">
                      <div className="flex items-center gap-2">
                        <span className="text-sm font-medium font-mono">{ip}</span>
                        {client.name && <span className="text-xs text-muted-foreground">{client.name}</span>}
                      </div>
                      <div className="flex items-center gap-2 mt-0.5">
                        <span className={cn("text-xs font-mono", getNodeColor(route?.primary_node || ""))}>
                          {route?.primary_node || "-"}
                        </span>
                        <span className="text-xs text-muted-foreground">{client.connections} 连接</span>
                      </div>
                    </div>
                  </div>
                  <ChevronDown
                    className={cn(
                      "w-4 h-4 text-muted-foreground shrink-0 transition-transform",
                      isExpanded && "rotate-180"
                    )}
                    strokeWidth={1.5}
                  />
                </button>

                {isExpanded && route && (
                  <div className="px-4 pb-4 flex flex-col gap-4">
                    <div>
                      <h4 className="text-xs font-medium text-muted-foreground mb-2">当前主链路</h4>
                      <p className="text-sm font-mono break-all">{route.primary_chain}</p>
                    </div>

                    <div>
                      <div className="flex items-center justify-between mb-2">
                        <h4 className="text-xs font-medium text-muted-foreground">客户端覆盖规则</h4>
                        <button
                          onClick={() => handleAdd(ip)}
                          className="flex items-center gap-1 text-xs text-primary hover:text-primary/80"
                        >
                          <Plus className="w-3 h-3" />
                          添加
                        </button>
                      </div>

                      {Object.keys(overrides).length === 0 ? (
                        <p className="text-xs text-muted-foreground">暂无覆盖规则</p>
                      ) : (
                        <div className="flex flex-col gap-2">
                          {Object.entries(overrides).map(([pattern, target]) => (
                            <div key={pattern} className="flex items-center gap-2">
                              <input
                                type="text"
                                value={pattern}
                                onChange={(e) => handleChange(ip, pattern, "pattern", e.target.value)}
                                placeholder="域名后缀，如 plex.tv"
                                className="flex-1 min-w-0 px-2 py-1.5 bg-secondary/50 rounded text-sm font-mono"
                              />
                              <select
                                value={target}
                                onChange={(e) => handleChange(ip, pattern, "target", e.target.value)}
                                className="px-2 py-1.5 bg-secondary/50 rounded text-sm"
                              >
                                {groups.map((g) => (
                                  <option key={g.name} value={g.name}>{g.name}</option>
                                ))}
                              </select>
                              <button
                                onClick={() => handleDelete(ip, pattern)}
                                className="p-1.5 text-muted-foreground hover:text-destructive"
                              >
                                <Trash2 className="w-3.5 h-3.5" />
                              </button>
                            </div>
                          ))}
                        </div>
                      )}

                      <button
                        onClick={() => handleSave(ip, route.overrides)}
                        disabled={saving === ip}
                        className="mt-3 flex items-center gap-1.5 px-3 py-1.5 bg-primary text-primary-foreground rounded-lg text-xs font-semibold hover:opacity-90 disabled:opacity-50"
                      >
                        <Save className="w-3 h-3" />
                        {saving === ip ? "保存中..." : "保存覆盖规则"}
                      </button>
                    </div>

                    <div>
                      <h4 className="text-xs font-medium text-muted-foreground mb-2">全局规则（默认）</h4>
                      <div className="flex flex-wrap gap-2">
                        {(routesData?.global_rules || []).map((rule) => (
                          <span
                            key={rule.name}
                            className="text-xs px-2 py-1 rounded-md bg-secondary/50 font-mono"
                            title={rule.type}
                          >
                            {rule.name} → {rule.target}
                          </span>
                        ))}
                      </div>
                    </div>
                  </div>
                )}
              </div>
            )
          })
        )}
      </div>
    </div>
  )
}
```

- [ ] **Step 2: 提交**

```bash
git add nebula-share-frontend/components/network-hub/client-routes.tsx
git commit -m "feat(client-routes): add ClientRoutes panel component"
```

---

### Task 7: 在 NetworkHub 中集成 ClientRoutes

**Files:**
- Modify: `nebula-share-frontend/components/network-hub.tsx`

**Interfaces:**
- Consumes: `ClientRoutes` 组件；`/api/clients/routes`。
- Produces: 在「路由」区块下方渲染 ClientRoutes，支持保存覆盖规则。

- [ ] **Step 1: 导入组件并新增状态**

在 `network-hub.tsx` 顶部：

```tsx
import { ClientRoutes } from "./network-hub/client-routes"
```

在 `NetworkHub` 组件 state 区新增：

```tsx
const [clientRoutes, setClientRoutes] = useState<{ clients: any[]; global_rules: any[] } | null>(null)
```

- [ ] **Step 2: 新增 fetch 和保存函数**

在 `fetchClients` 附近加入：

```tsx
const fetchClientRoutes = useCallback(async () => {
  try {
    const res = await fetch("/api/clients/routes")
    if (!res.ok) throw new Error(`HTTP ${res.status}`)
    const data = await res.json()
    if (!data.ok) throw new Error("Backend returned ok: false")
    setClientRoutes(data)
  } catch (err) {
    console.error("Failed to fetch client routes:", err)
  }
}, [])

const saveClientRoutes = useCallback(async (ip: string, overrides: Record<string, string>) => {
  try {
    const res = await fetch("/api/clients/routes", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ip, overrides }),
    })
    if (!res.ok) throw new Error(`HTTP ${res.status}`)
    const data = await res.json()
    if (!data.ok) throw new Error(data.error || "save failed")
    await fetchClientRoutes()
    await fetchClients()
  } catch (err) {
    console.error("Failed to save client routes:", err)
    alert("保存失败: " + (err instanceof Error ? err.message : "未知错误"))
  }
}, [fetchClientRoutes, fetchClients])
```

- [ ] **Step 3: 在 gateway tab effect 中调用 fetchClientRoutes**

找到：

```tsx
useEffect(() => {
  if (activeTab === "gateway") {
    fetchStatus()
    fetchNodes()
    fetchClients()
    fetchClientNames()
    const interval = setInterval(fetchClients, 3000)
    return () => clearInterval(interval)
  }
}, [activeTab, fetchStatus, fetchNodes, fetchClients, fetchClientNames])
```

改为：

```tsx
useEffect(() => {
  if (activeTab === "gateway") {
    fetchStatus()
    fetchNodes()
    fetchClients()
    fetchClientNames()
    fetchClientRoutes()
    const interval = setInterval(() => {
      fetchClients()
      fetchClientRoutes()
    }, 3000)
    return () => clearInterval(interval)
  }
}, [activeTab, fetchStatus, fetchNodes, fetchClients, fetchClientNames, fetchClientRoutes])
```

- [ ] **Step 4: 在「路由」区块下方插入 ClientRoutes**

找到路由区块结束处（`</div>` 闭合后），添加：

```tsx
{/* ── 6. Client Routes ── */}
<div>
  <h3 className="section-header">客户端路由</h3>
  <ClientRoutes
    clients={clients}
    groups={groups}
    routesData={clientRoutes}
    onSave={saveClientRoutes}
  />
</div>
```

- [ ] **Step 5: 提交**

```bash
git add nebula-share-frontend/components/network-hub.tsx
git commit -m "feat(client-routes): integrate ClientRoutes into NetworkHub"
```

---

### Task 8: 端到端验证

**Files:** 无新增文件。

**Interfaces:**
- 使用浏览器 + curl 验证新增 UI 和 API。

- [ ] **Step 1: 启动 Flask 后端（如未运行）**

```bash
cd /home/aw/vibeProjects/NebulaShare
source venv/bin/activate
python app.py
```

- [ ] **Step 2: 访问 Network Hub 页面**

浏览器打开 `http://<pi-ip>:5000/`，进入「网络枢纽」→「网关控制」。

Expected:
- 看到新增「客户端路由」折叠面板。
- 电视 192.168.50.141 显示当前主链路为香港节点。

- [ ] **Step 3: 为电视添加覆盖规则并保存**

在电视卡片覆盖规则区：
- 域名：`plex.tv`
- 目标组：`AI`
- 点击「保存覆盖规则」

Expected: 保存成功，页面刷新后电视 overrides 显示 `{ "plex.tv": "AI" }`。

- [ ] **Step 4: 验证配置已注入 mihomo**

```bash
grep -n "SRC-IP-CIDR" /etc/mihomo/config.yaml
```

Expected: 顶部出现 `AND,((SRC-IP-CIDR,192.168.50.141/32),(DOMAIN-SUFFIX,plex.tv)),AI`。

- [ ] **Step 5: 验证电视访问 plex.tv 走 AI 组**

在电视上打开 Pluto TV，同时观察：

```bash
curl -s http://127.0.0.1:9090/connections | python3 -c "
import sys, json
d = json.load(sys.stdin)
for c in d.get('connections', []):
    m = c.get('metadata', {})
    if m.get('sourceIP') == '192.168.50.141' and 'plex' in (m.get('host') or '').lower():
        print(m.get('host'), '->', ' -> '.join(c.get('chains', [])))
"
```

Expected: plex.tv 相关连接的 chain 出现 `AI` 而不是 `✈️Final`。

- [ ] **Step 6: 验证其他设备不受影响**

从另一台设备访问 plex.tv 或 YouTube，确认其链路不变。

- [ ] **Step 7: 提交验证结果（如无问题）**

```bash
git commit --allow-empty -m "test(client-routes): e2e verified on TV 192.168.50.141"
```

---

## Self-Review

### Spec Coverage

| Spec 需求 | 对应 Task |
|---|---|
| 按客户端展示当前主链路 | Task 4 (backend) + Task 6/7 (frontend) |
| 展示全局规则 | Task 4 + Task 6 |
| 客户端覆盖规则增删改 | Task 1/2/3 (backend state/inject/reload) + Task 5 (API) + Task 6 (UI) |
| 覆盖规则优先级高于全局 | Task 2（注入到 rules 最前） |
| 配置备份与回滚 | Task 3 |

### Placeholder Scan

- 无 TBD/TODO。
- 所有步骤包含实际代码和命令。
- 测试断言明确。

### Type Consistency

- `client_route_overrides` 在 backend 为 `dict[str, dict[str, str]]`。
- `overrides` 在 frontend 为 `Record<string, string>`。
- API 路径 `/api/clients/routes` 前后端一致。

### Known Caveats

- `_inject_client_overrides` 通过字符串前缀 `AND,((SRC-IP-CIDR,` 识别旧注入规则。如果用户自己写了同样前缀的 AND 规则，会被误删。第一期可接受；后续可通过注释标记或独立 rule-provider 改进。
- mihomo `/configs/reload` 是否可用取决于具体编译版本；fallback 到 `/configs` PUT。
