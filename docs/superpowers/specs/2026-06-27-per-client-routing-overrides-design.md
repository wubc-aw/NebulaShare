# 客户端级代理规则覆盖设计

**日期**: 2026-06-27  
**主题**: Network Hub 新增客户端级路由覆盖面板  
**状态**: 待实施

---

## 1. 目标

解决当前 Network Hub 在「规则分流」模式下 misleading 的问题：
- 前端「生效节点」显示的是 `GLOBAL` 选择器状态，而不是客户端实际走的节点。
- 用户无法直观看到每个设备/APP 当前走哪条链。
- 用户无法针对单个客户端调整路由（例如：电视看 Pluto 走 US 节点，手机 YouTube 走 HK 节点）。

本次改造目标：
1. 在 Network Hub 增加「客户端路由」折叠面板，按客户端展示当前真实链路。
2. 支持「全局规则为默认 + 客户端单独覆盖」的二级路由策略。
3. 覆盖规则优先级高于全局规则，仅对指定客户端生效。

---

## 2. 背景与约束

### 2.1 mihomo 当前行为

- 当前运行模式为 `rule`（规则分流）。
- `GLOBAL` 选择器在 `rule` 模式下不生效，仅作为全局模式的备用。
- 规则匹配自上而下；电视流量未命中特定规则时落入最后的 `MATCH,✈️Final`。
- 当前链：
  ```
  ✈️Final → Proxies → 🌸 Flower → [Flower] 🇭🇰 香港实验性 IEPL 专线 1
  ```

### 2.2 现有代码

- 后端 `app.py` 已有 `/api/mihomo/clients`，按 `sourceIP` 聚合活跃连接，暴露 `top_rule`、`top_chain`。
- 前端 `network-hub.tsx` 已有「客户端」列表，但只显示直连/代理二元和速率。
- 前端 `chain-log.tsx` 已展示每条连接的 `chain`。

### 2.3 技术约束

- mihomo v1.19.24 支持逻辑规则（AND / OR / NOT），可用于构造「源 IP + 域名」联合条件。
- mihomo 规则是全局的，不存在原生「每客户端规则」概念；需通过 `SRC-IP-CIDR` + `DOMAIN-SUFFIX` 的 AND 规则模拟。
- 规则修改需写回 `/etc/mihomo/config.yaml` 并热重载。

---

## 3. 设计概览

### 3.1 用户体验

在 Network Hub 「网关控制」标签页，「路由」区块下方新增可折叠面板「客户端路由」。

每个客户端一张折叠卡片：
- **卡片头**：IP / 别名 + 当前主链路 + 连接数
- **展开后**：
  1. **当前状态**：主链路、活跃规则命中分布、最近访问的域名
  2. **全局规则**：默认规则组列表（如 Google / AI / Final / Direct）及其当前目标组
  3. **客户端覆盖规则**：仅对该客户端生效的规则，支持增删改

### 3.2 数据模型

新增 NebulaShare 状态字段 `client_route_overrides`：

```json
{
  "client_route_overrides": {
    "192.168.50.141": {
      "plex.tv": "AI",
      "youtube.com": "Google"
    }
  }
}
```

- Key：客户端 IP
- Value：`{ 域名后缀模式: 目标代理组名 }`
- 与 `client_names` 同文件存储（`mihomo.json`）。

### 3.3 规则生成逻辑

保存覆盖规则时，后端生成 AND 逻辑规则并注入配置：

```yaml
rules:
  # 客户端覆盖规则（插在最前面，优先级最高）
  - 'AND,((SRC-IP-CIDR,192.168.50.141/32),(DOMAIN-SUFFIX,plex.tv)),AI'
  - 'AND,((SRC-IP-CIDR,192.168.50.141/32),(DOMAIN-SUFFIX,youtube.com)),Google'

  # 原有全局规则
  - ...
  - 'MATCH,✈️Final'
```

生成规则时：
- 每个覆盖规则生成一条 AND 规则。
- 所有覆盖规则按客户端分组后统一插入到全局规则 **之前**。
- 删除覆盖时，从配置中移除对应 AND 规则。

### 3.4 后端 API

新增两个接口：

#### `GET /api/clients/routes`

返回每个客户端的路由视图：

```json
{
  "ok": true,
  "clients": [
    {
      "ip": "192.168.50.141",
      "name": "电视",
      "primary_chain": "✈️Final → Proxies → 🌸 Flower → [Flower] 🇭🇰 香港实验性 IEPL 专线 1",
      "primary_node": "[Flower] 🇭🇰 香港实验性 IEPL 专线 1",
      "connections": 12,
      "rules_hit": {
        "Final": 8,
        "Google": 3,
        "DIRECT": 1
      },
      "overrides": {
        "plex.tv": "AI"
      }
    }
  ],
  "global_rules": [
    { "name": "Google", "target": "🌸 Flower", "type": "Selector" },
    { "name": "AI", "target": "🇺🇸 US | 美国 02", "type": "Selector" },
    { "name": "✈️Final", "target": "Proxies", "type": "Selector" }
  ]
}
```

#### `POST /api/clients/routes`

保存某个客户端的覆盖规则：

```json
{
  "ip": "192.168.50.141",
  "overrides": {
    "plex.tv": "AI",
    "youtube.com": "Google"
  }
}
```

后端行为：
1. 校验 IP 和 target 组名。
2. 更新 `client_route_overrides`。
3. 备份 `/etc/mihomo/config.yaml`。
4. 重写配置：注入所有客户端的 AND 覆盖规则。
5. 调用 mihomo 热重载（`PUT /configs` 或 `mihomo_post("/configs/reload")`，以实际可用为准）。
6. 重载失败则回滚备份。

---

## 4. 前端改动

### 4.1 新增组件

创建 `components/network-hub/client-routes.tsx`：

- 接收 `clients` 数组和 `groups` 数组。
- 每个客户端一个折叠卡片（使用与现有 UI 一致的 `card-premium` 风格）。
- 覆盖规则编辑区：
  - 输入框：域名后缀（如 `plex.tv`）
  - 下拉框：目标代理组（从 `/api/mihomo/groups` 获取）
  - 删除按钮 + 添加按钮
  - 保存按钮（仅该客户端）

### 4.2 NetworkHub 集成

- 在「路由」区块下方插入 `<ClientRoutes />`。
- 复用现有的 `groups` 状态和 `fetchNodes` 结果。
- 新增 `fetchClientRoutes` 用于获取路由视图。
- 保存成功后刷新 `fetchClientRoutes` 和 `fetchClients`。

### 4.3 UI 文案

- 面板标题：「客户端路由」
- 副标题：「全局规则为默认，客户端覆盖规则优先级更高」
- 空状态：「暂无覆盖规则」

---

## 5. 后端改动

### 5.1 新增 API 处理函数

在 `app.py` 中新增：

- `mihomo_client_routes()` → `GET /api/clients/routes`
- `mihomo_client_routes_post()` → `POST /api/clients/routes`

### 5.2 配置重写逻辑

新增辅助函数：

```python
def _inject_client_overrides(config: dict, overrides: dict) -> dict:
    """把 client_route_overrides 转成 AND 规则并插入 config['rules'] 最前。"""
    ...

def _reload_mihomo_config():
    """写回 config.yaml 并热重载，失败抛异常。"""
    ...
```

### 5.3 备份与回滚

- 备份命名：`/etc/mihomo/config.yaml.bak.YYYYMMDD-HHMMSS`
- 重载失败时从备份恢复。
- 保留最近 10 个备份，旧备份自动清理。

---

## 6. 风险与缓解

| 风险 | 影响 | 缓解措施 |
|---|---|---|
| 重写配置搞坏 mihomo | 代理不可用 | 写前备份，失败自动回滚；先在测试环境验证 |
| AND 规则不被当前 mihomo 支持 | 规则不生效 | 实施前在 config.yaml 手动加一条 AND 规则测试重载 |
| 覆盖规则与全局规则冲突 | 预期外路由 | UI 明确标注「覆盖规则优先级高于全局规则」 |
| 客户端 IP 变动 | 覆盖失效 | DHCP 建议绑定；未来可考虑按 MAC/设备名绑定 |
| 前端显示「当前主链路」与覆盖规则不同步 | 用户困惑 | 保存后立刻刷新连接和路由数据 |

---

## 7. 测试计划

1. **单元测试**：
   - `_inject_client_overrides` 正确生成 AND 规则并插入顶部。
   - `_reload_mihomo_config` 失败时回滚备份。

2. **集成测试**：
   - 为电视添加 `plex.tv → AI` 覆盖，验证 mihomo 配置包含对应 AND 规则。
   - 从电视访问 `plex.tv`，确认链变为 `AI → 🇺🇸 US 02`。
   - 从其他设备访问 `plex.tv`，确认仍走原全局规则。

3. **UI 测试**：
   - 折叠/展开客户端卡片。
   - 添加、编辑、删除覆盖规则。
   - 保存失败显示错误信息。

---

## 8. 后续可扩展

- 支持更多匹配类型：`DOMAIN-KEYWORD`、`IP-CIDR`、`GEOIP`、`GEOSITE`。
- 支持按 MAC 地址或设备名绑定（需 DHCP 静态分配或 ARP 表）。
- 规则优先级拖拽排序。
- 在「生效节点」卡片上增加提示：规则模式下显示的是 `GLOBAL` 备用节点，不是实际流量节点。

---

## 9. 决策记录

- **覆盖规则作用域**：第一期仅支持 `DOMAIN-SUFFIX`，因为这是最常见的需求（Pluto/YouTube/Netflix 等流媒体域名）。
- **规则位置**：覆盖规则插入全局规则之前，确保优先级最高。
- **配置热重载 vs 重启**：优先使用 mihomo 热重载 API；如不可用再降级为 `systemctl restart mihomo`。
- **存储位置**：覆盖规则存于 `mihomo.json`（与 `client_names` 一致），而非直接解析 config.yaml，避免订阅更新时丢失 NebulaShare 的自定义配置。
