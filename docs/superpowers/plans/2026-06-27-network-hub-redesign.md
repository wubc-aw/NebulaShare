# 网络枢纽节点选择重构实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 重构 NebulaShare 网络枢纽的节点选择 UI：修复顶部生效节点显示错误，新增按大洲折叠的平面节点选择器，将订阅商分组配置默认折叠，并新增实时链路日志验证分流是否生效。

**Architecture:** 保持现有 Flask 后端 `/api/mihomo/*` 端点不变，主要改动集中在 Next.js 前端。新增纯函数工具 `lib/proxy-regions.ts` 负责按节点名归类大洲；新增 `components/network-hub/chain-log.tsx` 负责链路日志展示；在 `components/network-hub.tsx` 内重组网关控制页布局、修复生效节点显示、替换分组选择器为平面列表、折叠订阅商配置。

**Tech Stack:** Next.js 16 + React 19 + TypeScript + Tailwind CSS + Lucide React（前端）；Flask + mihomo API（后端，无改动）。

## Global Constraints

- 节点延迟显示规则：绿 <100ms / 黄 <200ms / 红 ≥200ms / 灰色未测
- 地区按大洲划分：亚洲、欧洲、北美洲、南美洲、大洋洲、非洲、其他
- 链路日志去重键：**客户端 IP + 目标域名/IP**，仅链路链变化时更新
- 直连模式下点击节点 → 自动切换为“规则分流”模式并设置该节点为 GLOBAL 选择
- 顶部“生效节点”始终显示 `GLOBAL.now` 或“直连”，不再显示 `groups[0].now`

---

## File Map

| 文件 | 职责 |
|------|------|
| `nebula-share-frontend/lib/proxy-regions.ts` | 根据节点名关键词返回大洲分类 |
| `nebula-share-frontend/lib/proxy-regions.test.mjs` | 用 Node.js assert 对地区分类做单元测试 |
| `nebula-share-frontend/components/network-hub/chain-log.tsx` | 链路日志组件：轮询连接、去重、展示 |
| `nebula-share-frontend/components/network-hub.tsx` | 主组件：重组布局、生效节点卡片、平面节点选择器、订阅商配置折叠 |

---

## Task 1: 地区分类工具 + 测试

**Files:**
- Create: `nebula-share-frontend/lib/proxy-regions.ts`
- Create: `nebula-share-frontend/lib/proxy-regions.test.mjs`

**Interfaces:**
- Produces: `classifyRegion(name: string): string` → 返回 `"亚洲" | "欧洲" | "北美洲" | "南美洲" | "大洋洲" | "非洲" | "其他"`
- Produces: `CONTINENT_ORDER: string[]` → 大洲排序数组

- [ ] **Step 1: 编写地区分类工具**

Create `nebula-share-frontend/lib/proxy-regions.ts`:

```typescript
export const CONTINENTS = [
  "亚洲",
  "欧洲",
  "北美洲",
  "南美洲",
  "大洋洲",
  "非洲",
  "其他",
] as const

export type Continent = (typeof CONTINENTS)[number]

const RULES: { continent: Continent; keywords: string[] }[] = [
  {
    continent: "亚洲",
    keywords: [
      "香港", "台湾", "日本", "新加坡", "韩国", "泰国", "马来西亚", "越南",
      "印度", "菲律宾", "印尼", "印度尼西亚", "中国", "上海", "北京", "广州",
      "深圳", "澳门", "HK", "TW", "JP", "SG", "KR", "TH", "MY", "VN", "IN",
      "PH", "ID", "HONGKONG", "TAIWAN", "JAPAN", "KOREA",
    ],
  },
  {
    continent: "欧洲",
    keywords: [
      "英国", "德国", "法国", "意大利", "荷兰", "西班牙", "瑞士", "瑞典",
      "俄罗斯", "波兰", "土耳其", "芬兰", "挪威", "丹麦", "比利时", "奥地利",
      "爱尔兰", "葡萄牙", "希腊", "罗马尼亚", "保加利亚", "塞尔维亚", "匈牙利",
      "捷克", "斯洛伐克", "乌克兰", "白俄罗斯", "爱沙尼亚", "拉脱维亚", "立陶宛",
      "UK", "GB", "DE", "FR", "IT", "NL", "ES", "CH", "SE", "RU", "PL", "TR",
      "FI", "NO", "DK", "BE", "AT", "IE", "PT", "GR", "RO", "BG", "RS", "HU",
      "CZ", "SK", "UA", "BY", "EE", "LV", "LT",
    ],
  },
  {
    continent: "北美洲",
    keywords: [
      "美国", "加拿大", "美國", "USA", "US", "CA", "CANADA", "AMERICA",
    ],
  },
  {
    continent: "南美洲",
    keywords: [
      "巴西", "阿根廷", "智利", "秘鲁", "哥伦比亚", "乌拉圭", "巴拉圭",
      "玻利维亚", "厄瓜多尔", "委内瑞拉", "BR", "AR", "CL", "PE", "CO", "UY",
      "PY", "BO", "EC", "VE", "BRAZIL", "ARGENTINA",
    ],
  },
  {
    continent: "大洋洲",
    keywords: [
      "澳大利亚", "新西兰", "澳洲", "AU", "NZ", "AUSTRALIA", "NEW ZEALAND",
    ],
  },
  {
    continent: "非洲",
    keywords: [
      "南非", "埃及", "尼日利亚", "肯尼亚", "摩洛哥", "阿尔及利亚", "突尼斯",
      "加纳", "坦桑尼亚", "乌干达", "埃塞俄比亚", "ZA", "EG", "NG", "KE", "MA",
      "DZ", "TN", "GH", "TZ", "UG", "ET", "SOUTH AFRICA", "EGYPT", "NIGERIA",
    ],
  },
]

export function classifyRegion(name: string): Continent {
  const upper = name.toUpperCase()
  for (const rule of RULES) {
    for (const kw of rule.keywords) {
      if (upper.includes(kw.toUpperCase())) {
        return rule.continent
      }
    }
  }
  return "其他"
}

export const CONTINENT_ORDER: Continent[] = [
  "亚洲",
  "欧洲",
  "北美洲",
  "南美洲",
  "大洋洲",
  "非洲",
  "其他",
]
```

- [ ] **Step 2: 编写测试**

Create `nebula-share-frontend/lib/proxy-regions.test.mjs`:

```javascript
import assert from "node:assert"
import { classifyRegion } from "./proxy-regions.ts"

const cases = [
  ["日本 03", "亚洲"],
  ["HK-01", "亚洲"],
  ["美国 IEPL", "北美洲"],
  ["USA LA", "北美洲"],
  ["英国 01", "欧洲"],
  ["UK London", "欧洲"],
  ["巴西 01", "南美洲"],
  ["澳大利亚 Sydney", "大洋洲"],
  ["南非 01", "非洲"],
  ["Unknown Node", "其他"],
]

for (const [name, expected] of cases) {
  const actual = classifyRegion(name)
  assert.strictEqual(actual, expected, `classifyRegion(${JSON.stringify(name)}) expected ${expected}, got ${actual}`)
}

console.log("All region classification tests passed.")
```

- [ ] **Step 3: 运行测试**

Run:

```bash
cd /home/aw/vibeProjects/NebulaShare/nebula-share-frontend
node --experimental-strip-types lib/proxy-regions.test.mjs
```

Expected output:

```
All region classification tests passed.
```

- [ ] **Step 4: 提交**

```bash
cd /home/aw/vibeProjects/NebulaShare
git add nebula-share-frontend/lib/proxy-regions.ts nebula-share-frontend/lib/proxy-regions.test.mjs
git commit -m "feat(network-hub): add continent classification for proxy nodes

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 2: 修复顶部生效节点显示

**Files:**
- Modify: `nebula-share-frontend/components/network-hub.tsx:169-189`（状态区）
- Modify: `nebula-share-frontend/components/network-hub.tsx:476-494`（当前节点卡片）

**Interfaces:**
- Consumes: `groups`（`ProxyGroup[]`）, `status`（`MihomoStatus | null`）, `gatewayEnabled`
- Produces: 计算属性 `globalGroup: ProxyGroup | undefined` 和 `effectiveNodeName: string`

- [ ] **Step 1: 添加生效节点计算辅助**

在 `NetworkHub` 组件内、其他 `useCallback` 之后添加：

```typescript
  const globalGroup = groups.find((g) => g.name === "GLOBAL")
  const effectiveNodeName = !gatewayEnabled
    ? "服务未运行"
    : routingMode === "direct"
    ? "直连"
    : globalGroup?.now || "未选择"
```

- [ ] **Step 2: 替换顶部“当前节点”卡片**

替换 `nebula-share-frontend/components/network-hub.tsx` 中第 476-494 行：

Old:

```tsx
            {/* Current Node */}
            <div className="card-premium p-4">
              <div className="flex items-center gap-2 mb-3">
                <Globe className="w-4 h-4 text-muted-foreground" strokeWidth={1.5} />
                <span className="text-sm font-semibold">当前节点</span>
              </div>
              {groups.length > 0 ? (
                <div className="flex items-center gap-2">
                  <p className="text-base font-semibold">{groups[0]?.now || "未选择"}</p>
                  {groups[0]?.members.find(m => m.name === groups[0]?.now)?.delay && (
                    <span className="text-xs text-muted-foreground font-mono bg-secondary/60 px-1.5 py-0.5 rounded">
                      {groups[0]?.members.find(m => m.name === groups[0]?.now)?.delay}ms
                    </span>
                  )}
                </div>
              ) : (
                <p className="text-sm text-muted-foreground">未选择</p>
              )}
            </div>
```

New:

```tsx
            {/* Effective Node */}
            <button
              onClick={() => {
                const el = document.getElementById("node-selector")
                el?.scrollIntoView({ behavior: "smooth", block: "start" })
              }}
              className="card-premium p-4 text-left w-full hover:shadow-md transition-shadow"
            >
              <div className="flex items-center justify-between mb-3">
                <div className="flex items-center gap-2">
                  <Globe className="w-4 h-4 text-muted-foreground" strokeWidth={1.5} />
                  <span className="text-sm font-semibold">生效节点</span>
                </div>
                <span className="text-xs text-muted-foreground font-mono bg-secondary/60 px-2 py-0.5 rounded">
                  {routingMode === "direct" ? "直连模式" : routingMode === "global" ? "全局代理" : "规则分流"}
                </span>
              </div>
              <div className="flex items-center gap-2">
                <p className="text-base font-semibold">{effectiveNodeName}</p>
                {effectiveNodeName !== "服务未运行" && effectiveNodeName !== "直连" && effectiveNodeName !== "未选择" && globalGroup && (
                  <span className={cn(
                    "text-xs font-mono bg-secondary/60 px-1.5 py-0.5 rounded",
                    (() => {
                      const delay = globalGroup.members.find(m => m.name === globalGroup.now)?.delay
                      if (!delay || delay <= 0) return "text-muted-foreground"
                      if (delay < 100) return "text-emerald-400"
                      if (delay < 200) return "text-amber-400"
                      return "text-red-400"
                    })()
                  )}>
                    {globalGroup.members.find(m => m.name === globalGroup.now)?.delay || "--"}ms
                  </span>
                )}
              </div>
            </button>
```

- [ ] **Step 3: 运行开发服务器验证**

```bash
cd /home/aw/vibeProjects/NebulaShare/nebula-share-frontend
npm run dev
```

打开浏览器访问 `http://localhost:3000`，确认顶部卡片显示的是 `GLOBAL` 当前节点，而不是 AI 分组节点。

- [ ] **Step 4: 提交**

```bash
cd /home/aw/vibeProjects/NebulaShare
git add nebula-share-frontend/components/network-hub.tsx
git commit -m "fix(network-hub): show effective GLOBAL node instead of first group

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 3: 平面节点选择器（按大洲折叠）

**Files:**
- Modify: `nebula-share-frontend/components/network-hub.tsx:169-189`（新增状态）
- Modify: `nebula-share-frontend/components/network-hub.tsx:219-240`（调整 fetchNodes）
- Modify: `nebula-share-frontend/components/network-hub.tsx:345-361`（调整 handleNodeSwitch）
- Modify: `nebula-share-frontend/components/network-hub.tsx:660-731`（替换分组选择器）

**Interfaces:**
- Consumes: `groups`（`ProxyGroup[]`）, `classifyRegion`, `CONTINENT_ORDER`
- Produces: `flatNodes`（去重后的 `ProxyNode[]`）, `nodesByContinent`（按大洲分组）

- [ ] **Step 1: 导入地区工具**

在 `nebula-share-frontend/components/network-hub.tsx` 顶部导入：

```typescript
import { classifyRegion, CONTINENT_ORDER } from "@/lib/proxy-regions"
```

- [ ] **Step 2: 添加大洲折叠状态**

在 `NetworkHub` 的状态区添加：

```typescript
  const [expandedContinents, setExpandedContinents] = useState<Set<string>>(new Set(CONTINENT_ORDER))
```

- [ ] **Step 3: 计算平面节点列表**

在组件渲染区、return 之前添加：

```typescript
  const GROUP_TYPES = new Set(["Selector", "URLTest", "Fallback", "LoadBalance", "Direct", "Reject"])

  const flatNodes = groups
    .flatMap((g) => g.members)
    .filter((m) => m.name && !GROUP_TYPES.has(m.type || ""))
    .reduce<ProxyNode[]>((acc, node) => {
      if (!acc.some((n) => n.name === node.name)) {
        acc.push(node)
      }
      return acc
    }, [])
    .sort((a, b) => a.name.localeCompare(b.name))

  const nodesByContinent = CONTINENT_ORDER.map((continent) => ({
    continent,
    nodes: flatNodes.filter((n) => classifyRegion(n.name) === continent),
  })).filter((c) => c.nodes.length > 0)
```

- [ ] **Step 4: 调整 handleNodeSwitch 支持直连自动切规则模式**

替换 `handleNodeSwitch`：

```typescript
  const handleNodeSwitch = async (nodeName: string) => {
    const groupName = "GLOBAL"
    const targetMode: "rule" | "global" = routingMode === "global" ? "global" : "rule"

    // If currently direct, switch to rule first so the node actually takes effect
    if (gatewayEnabled && routingMode === "direct") {
      setRoutingMode(targetMode)
      try {
        const modeRes = await fetch("/api/mihomo/mode", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ mode: targetMode }),
        })
        if (!modeRes.ok) throw new Error(`HTTP ${modeRes.status}`)
        const modeData = await modeRes.json()
        if (!modeData.ok) throw new Error("Mode switch failed")
      } catch (err) {
        console.error("Mode switch failed:", err)
      }
    }

    setSelectedNode(`${groupName}::${nodeName}`)
    try {
      const res = await fetch("/api/mihomo/select", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ group: groupName, name: nodeName }),
      })
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      const data = await res.json()
      if (!data.ok) throw new Error("Switch failed")
      await fetchNodes()
      await fetchStatus()
    } catch (err) {
      console.error("Node switch failed:", err)
    }
  }
```

- [ ] **Step 5: 替换“代理节点”区域为平面选择器**

替换 `nebula-share-frontend/components/network-hub.tsx` 中第 660-731 行的“代理节点”区域：

```tsx
          {/* ── 3. Node Selector ── */}
          <div id="node-selector" className="flex-1">
            <div className="flex items-center justify-between mb-3">
              <h3 className="section-header">节点选择</h3>
              <button
                onClick={async () => {
                  setIsRefreshing(true)
                  try {
                    const res = await fetch("/api/mihomo/test/group/GLOBAL?timeout=3000")
                    if (!res.ok) throw new Error(`HTTP ${res.status}`)
                    await fetchNodes()
                  } catch (err) {
                    console.error("Latency refresh failed:", err)
                  } finally {
                    setIsRefreshing(false)
                  }
                }}
                disabled={isRefreshing || nodesLoading}
                className="flex items-center gap-1.5 px-3 py-1.5 bg-primary text-primary-foreground rounded-lg text-xs font-semibold hover:opacity-90 transition-opacity disabled:opacity-50"
              >
                <RefreshCw className={cn("w-3 h-3", isRefreshing && "animate-spin")} strokeWidth={1.5} />
                {isRefreshing ? "测速中" : "刷新延迟"}
              </button>
            </div>

            {nodesLoading ? (
              <p className="text-sm text-muted-foreground px-1">加载节点中...</p>
            ) : nodesError ? (
              <p className="text-sm text-destructive px-1">{nodesError}</p>
            ) : flatNodes.length === 0 ? (
              <p className="text-sm text-muted-foreground px-1">暂无可用节点</p>
            ) : (
              <div className="flex flex-col gap-3">
                {nodesByContinent.map(({ continent, nodes }) => {
                  const isExpanded = expandedContinents.has(continent)
                  return (
                    <div key={continent} className="card-premium overflow-hidden">
                      <button
                        onClick={() => {
                          const next = new Set(expandedContinents)
                          if (next.has(continent)) next.delete(continent)
                          else next.add(continent)
                          setExpandedContinents(next)
                        }}
                        className="w-full flex items-center gap-3 px-4 py-3 text-left hover:bg-secondary/20 transition-colors"
                      >
                        <ChevronDown
                          className={cn(
                            "w-4 h-4 text-muted-foreground shrink-0 transition-transform duration-200",
                            !isExpanded && "-rotate-90"
                          )}
                          strokeWidth={1.5}
                        />
                        <span className="text-sm font-semibold">{continent}</span>
                        <span className="text-xs text-muted-foreground font-mono bg-secondary/50 px-2 py-0.5 rounded-md">
                          {nodes.length}
                        </span>
                      </button>

                      {isExpanded && (
                        <div className="px-4 pb-4">
                          <div className="flex flex-wrap gap-2">
                            {nodes.map((node) => {
                              const isActive = globalGroup?.now === node.name
                              const delay = node.delay || 0
                              return (
                                <button
                                  key={node.name}
                                  onClick={() => handleNodeSwitch(node.name)}
                                  className={cn("node-chip", isActive && "active")}
                                  title={node.name}
                                >
                                  <span className="truncate max-w-[140px]">{node.name}</span>
                                  {delay > 0 ? (
                                    <span className={cn(
                                      "text-xs font-mono tabular-nums opacity-80",
                                      delay < 100 ? "text-emerald-400" : delay < 200 ? "text-amber-400" : "text-red-400"
                                    )}>
                                      {delay}ms
                                    </span>
                                  ) : (
                                    <span className="text-xs font-mono opacity-50">--</span>
                                  )}
                                </button>
                              )
                            })}
                          </div>
                        </div>
                      )}
                    </div>
                  )
                })}
              </div>
            )}
          </div>
```

- [ ] **Step 6: 运行开发服务器验证**

确认：
- 节点按大洲分组显示
- 每个大洲可折叠/展开
- 点击节点后顶部“生效节点”更新
- “刷新延迟”按钮触发测速

- [ ] **Step 7: 提交**

```bash
cd /home/aw/vibeProjects/NebulaShare
git add nebula-share-frontend/components/network-hub.tsx
git commit -m "feat(network-hub): flat continent-based node selector

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 4: 订阅商配置默认折叠

**Files:**
- Modify: `nebula-share-frontend/components/network-hub.tsx:169-189`（新增状态）
- Modify: `nebula-share-frontend/components/network-hub.tsx:623-657`（替换订阅区域）

**Interfaces:**
- Consumes: `groups`（`ProxyGroup[]`）, `handleNodeSwitch` 原始逻辑
- Produces: `providerConfigExpanded` 状态，折叠/展开 UI

- [ ] **Step 1: 添加折叠状态**

在 `NetworkHub` 状态区添加：

```typescript
  const [providerConfigExpanded, setProviderConfigExpanded] = useState(false)
```

- [ ] **Step 2: 替换“订阅”区域为“订阅商配置”折叠面板**

替换 `nebula-share-frontend/components/network-hub.tsx` 中第 623-657 行的订阅区域：

```tsx
          {/* ── 2. Provider Configuration ── */}
          <div>
            <button
              onClick={() => setProviderConfigExpanded((v) => !v)}
              className="w-full flex items-center justify-between mb-3 group"
            >
              <h3 className="section-header mb-0">订阅商配置</h3>
              <ChevronDown
                className={cn(
                  "w-4 h-4 text-muted-foreground transition-transform duration-200",
                  providerConfigExpanded && "rotate-180"
                )}
                strokeWidth={1.5}
              />
            </button>

            {providerConfigExpanded && (
              <div className="flex flex-col gap-3">
                {/* Subscription URL + refresh */}
                <div className="card-premium p-4">
                  <div className="flex items-center justify-between mb-3">
                    <div className="flex items-center gap-2">
                      <Globe className="w-4 h-4 text-muted-foreground" strokeWidth={1.5} />
                      <span className="text-sm font-semibold">订阅链接</span>
                    </div>
                    <div className="flex items-center gap-3">
                      <span className="text-xs text-muted-foreground font-mono">
                        {subInfo ? `${subInfo.proxyCount} 节点` : `${totalNodes} 节点`}
                      </span>
                      <button
                        onClick={handleSubRefresh}
                        disabled={subRefreshing}
                        className="flex items-center gap-1.5 px-3 py-1.5 bg-primary text-primary-foreground rounded-lg text-xs font-semibold hover:opacity-90 transition-opacity disabled:opacity-50"
                      >
                        <RefreshCw className={cn("w-3 h-3", subRefreshing && "animate-spin")} strokeWidth={1.5} />
                        {subRefreshing ? "更新中" : "刷新订阅"}
                      </button>
                    </div>
                  </div>
                  {subError && <p className="text-sm text-destructive mb-2">{subError}</p>}
                  <input
                    type="text"
                    placeholder="订阅链接"
                    className="w-full px-3 py-2 bg-secondary/40 rounded-lg text-sm font-mono text-muted-foreground"
                    defaultValue={status?.subscription?.url || ""}
                    readOnly
                  />
                </div>

                {groups
                  .filter((g) => g.name !== "GLOBAL")
                  .map((group) => {
                    const isExpanded = expandedGroups.has(group.name)
                    return (
                      <div key={group.name} className="card-premium overflow-hidden">
                        <button
                          onClick={() => {
                            const next = new Set(expandedGroups)
                            if (next.has(group.name)) next.delete(group.name)
                            else next.add(group.name)
                            setExpandedGroups(next)
                          }}
                          className="w-full flex items-center gap-3 px-4 py-3 text-left hover:bg-secondary/20 transition-colors"
                        >
                          <ChevronDown
                            className={cn(
                              "w-4 h-4 text-muted-foreground shrink-0 transition-transform duration-200",
                              !isExpanded && "-rotate-90"
                            )}
                            strokeWidth={1.5}
                          />
                          <span className="text-sm font-semibold">{group.name}</span>
                          <span className="text-xs text-muted-foreground font-mono bg-secondary/50 px-2 py-0.5 rounded-md">
                            {group.type}
                          </span>
                          <span className="text-xs text-muted-foreground ml-auto">
                            {group.now}
                          </span>
                        </button>

                        {isExpanded && (
                          <div className="px-4 pb-4">
                            <div className="flex flex-wrap gap-2">
                              {group.members.map((node) => {
                                const isActive = group.now === node.name
                                return (
                                  <button
                                    key={`${group.name}::${node.name}`}
                                    onClick={() => handleProviderNodeSwitch(group.name, node.name)}
                                    className={cn("node-chip", isActive && "active")}
                                    title={node.name}
                                  >
                                    <span className="truncate max-w-[120px]">{node.name}</span>
                                    {node.delay !== null && node.delay > 0 ? (
                                      <span className={cn(
                                        "text-xs font-mono tabular-nums opacity-80",
                                        node.delay < 100 ? "text-emerald-400" : node.delay < 200 ? "text-amber-400" : "text-red-400"
                                      )}>
                                        {node.delay}ms
                                      </span>
                                    ) : (
                                      <span className="text-xs font-mono opacity-50">--</span>
                                    )}
                                  </button>
                                )
                              })}
                            </div>
                          </div>
                        )}
                      </div>
                    )
                  })}
              </div>
            )}
          </div>
```

- [ ] **Step 3: 添加 provider 节点切换函数**

在 `handleNodeSwitch` 之后添加：

```typescript
  const handleProviderNodeSwitch = async (groupName: string, nodeName: string) => {
    try {
      const res = await fetch("/api/mihomo/select", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ group: groupName, name: nodeName }),
      })
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      const data = await res.json()
      if (!data.ok) throw new Error("Switch failed")
      await fetchNodes()
    } catch (err) {
      console.error("Provider node switch failed:", err)
    }
  }
```

- [ ] **Step 4: 运行开发服务器验证**

确认：
- “订阅商配置”默认折叠
- 点击标题可展开
- 展开后能看到原分组并可切换

- [ ] **Step 5: 提交**

```bash
cd /home/aw/vibeProjects/NebulaShare
git add nebula-share-frontend/components/network-hub.tsx
git commit -m "feat(network-hub): collapse provider config by default

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 5: 实时链路日志

**Files:**
- Create: `nebula-share-frontend/components/network-hub/chain-log.tsx`
- Modify: `nebula-share-frontend/components/network-hub.tsx`（集成 ChainLog）

**Interfaces:**
- Consumes: `/api/mihomo/connections/recent` 返回的 `items`
- Produces: `ChainLog` 组件，props: `className?: string`

- [ ] **Step 1: 创建链路日志组件**

Create `nebula-share-frontend/components/network-hub/chain-log.tsx`:

```tsx
"use client"

import { useState, useEffect, useCallback, useRef } from "react"
import { cn } from "@/lib/utils"
import { Activity, Trash2, RefreshCw } from "lucide-react"

interface ChainLogItem {
  id: string
  time: string
  src: string
  host: string
  port: string
  rule: string
  rule_payload: string
  chain: string
}

interface RawConnection {
  src: string
  host: string
  port: string
  rule: string
  rule_payload: string
  chain: string
  start: string
}

function makeKey(item: ChainLogItem) {
  return `${item.src}::${item.host}:${item.port}`
}

function formatTime(iso: string) {
  const d = new Date(iso)
  return d.toLocaleTimeString("zh-CN", { hour12: false })
}

export function ChainLog({ className }: { className?: string }) {
  const [items, setItems] = useState<ChainLogItem[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const seenRef = useRef<Record<string, string>>({})

  const fetchConnections = useCallback(async () => {
    try {
      const res = await fetch("/api/mihomo/connections/recent?limit=50")
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      const data = await res.json()
      if (!data.ok) throw new Error("Backend returned ok: false")

      const incoming: RawConnection[] = data.items || []
      const updates: ChainLogItem[] = []

      for (const c of incoming) {
        const item: ChainLogItem = {
          id: `${c.src}-${c.host}-${c.port}-${Date.now()}`,
          time: formatTime(c.start || new Date().toISOString()),
          src: c.src,
          host: c.host,
          port: c.port,
          rule: c.rule || "-",
          rule_payload: c.rule_payload || "",
          chain: c.chain || "DIRECT",
        }
        const key = makeKey(item)
        const previous = seenRef.current[key]
        if (previous !== item.chain) {
          seenRef.current[key] = item.chain
          updates.push(item)
        }
      }

      if (updates.length > 0) {
        setItems((prev) => {
          const map = new Map(prev.map((i) => [makeKey(i), i]))
          for (const u of updates) {
            map.set(makeKey(u), u)
          }
          return Array.from(map.values()).sort((a, b) => b.id.localeCompare(a.id)).slice(0, 100)
        })
      }
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to fetch connections")
    }
  }, [])

  const handleRefresh = async () => {
    setLoading(true)
    await fetchConnections()
    setLoading(false)
  }

  const handleClear = () => {
    setItems([])
    seenRef.current = {}
  }

  useEffect(() => {
    fetchConnections()
    const interval = setInterval(fetchConnections, 3000)
    return () => clearInterval(interval)
  }, [fetchConnections])

  return (
    <div className={cn("card-premium p-4", className)}>
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <Activity className="w-4 h-4 text-muted-foreground" strokeWidth={1.5} />
          <h3 className="text-sm font-semibold">链路日志</h3>
          <span className="text-xs text-muted-foreground font-mono bg-secondary/50 px-2 py-0.5 rounded-md">
            {items.length}
          </span>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={handleClear}
            className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg bg-secondary/50 text-xs text-muted-foreground hover:text-foreground transition-colors"
          >
            <Trash2 className="w-3 h-3" strokeWidth={1.5} />
            清空
          </button>
          <button
            onClick={handleRefresh}
            disabled={loading}
            className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg bg-secondary/50 text-xs text-muted-foreground hover:text-foreground transition-colors disabled:opacity-50"
          >
            <RefreshCw className={cn("w-3 h-3", loading && "animate-spin")} strokeWidth={1.5} />
            刷新
          </button>
        </div>
      </div>

      {error && (
        <p className="text-sm text-destructive mb-3">{error}</p>
      )}

      {items.length === 0 ? (
        <p className="text-sm text-muted-foreground">暂无链路变化记录</p>
      ) : (
        <div className="flex flex-col gap-2 max-h-[360px] overflow-auto pr-1">
          {items.map((item) => (
            <div
              key={item.id}
              className="flex flex-col gap-1 px-3 py-2 rounded-xl bg-secondary/20"
            >
              <div className="flex items-center justify-between gap-3">
                <div className="flex items-center gap-2 min-w-0">
                  <span className="text-xs text-muted-foreground font-mono shrink-0">{item.time}</span>
                  <span className="text-xs font-medium truncate">{item.host}:{item.port}</span>
                </div>
                <span className="text-[11px] text-muted-foreground font-mono shrink-0">{item.src}</span>
              </div>
              <div className="flex items-center justify-between gap-3">
                <span className="text-xs text-muted-foreground font-mono truncate">
                  {item.rule_payload ? `${item.rule} / ${item.rule_payload}` : item.rule}
                </span>
                <span className={cn(
                  "text-xs font-mono shrink-0",
                  item.chain.includes("DIRECT") ? "text-success" : "text-primary"
                )}>
                  {item.chain}
                </span>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
```

- [ ] **Step 2: 集成到 NetworkHub**

在 `nebula-share-frontend/components/network-hub.tsx` 顶部导入：

```typescript
import { ChainLog } from "./network-hub/chain-log"
```

在“客户端”区域之后（约第 801 行 `</div>` 之后）添加链路日志：

```tsx
          {/* ── 6. Chain Log ── */}
          <div>
            <ChainLog />
          </div>
```

- [ ] **Step 3: 运行开发服务器验证**

确认：
- 页面最下方出现“链路日志”卡片
- 有流量时显示连接记录
- 同一客户端+域名链路变化时才会更新
- 清空按钮有效

- [ ] **Step 4: 提交**

```bash
cd /home/aw/vibeProjects/NebulaShare
git add nebula-share-frontend/components/network-hub/chain-log.tsx nebula-share-frontend/components/network-hub.tsx
git commit -m "feat(network-hub): add real-time chain log

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 6: 生产构建验证

**Files:**
- Modify: none（仅验证）

- [ ] **Step 1: 运行 TypeScript 检查**

```bash
cd /home/aw/vibeProjects/NebulaShare/nebula-share-frontend
npx tsc --noEmit
```

Expected: no errors.

- [ ] **Step 2: 运行构建**

```bash
cd /home/aw/vibeProjects/NebulaShare/nebula-share-frontend
npm run build
```

Expected: build succeeds.

- [ ] **Step 3: 最终提交（如构建产生新的 dist）**

```bash
cd /home/aw/vibeProjects/NebulaShare
git add -A
git commit -m "chore(network-hub): build frontend after redesign

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Spec Coverage Check

| 规格要求 | 对应任务 |
|----------|----------|
| 顶部“生效节点”显示 GLOBAL.now 或“直连” | Task 2 |
| 平面节点选择器，按大洲折叠 | Task 1（工具）、Task 3（UI） |
| 点击节点切换 GLOBAL | Task 3 |
| 刷新延迟按钮 | Task 3 |
| 订阅商配置默认折叠 | Task 4 |
| 链路日志轮询 + 去重 | Task 5 |
| 直连模式点击节点自动切规则模式 | Task 3 |

## Placeholder Scan

- 无 TBD / TODO。
- 所有代码步骤均含完整代码。
- 所有命令均含预期输出或验证点。

## Type Consistency

- `ProxyNode` / `ProxyGroup` 类型沿用 `network-hub.tsx` 已有定义。
- `ChainLog` 组件 props 为 `{ className?: string }`。
- `classifyRegion` 返回 `Continent`，与 `CONTINENT_ORDER` 一致。
