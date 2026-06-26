"use client"

import { useState, useEffect, useCallback } from "react"
import {
  Power,
  Wifi,
  Globe,
  ArrowUpDown,
  RefreshCw,
  Zap,
  Activity,
  Users,
  ChevronRight,
  ChevronDown,
} from "lucide-react"
import { cn } from "@/lib/utils"

interface ProxyNode {
  name: string
  type: string
  delay: number | null
}

interface ProxyGroup {
  name: string
  type: string
  now: string
  udp: boolean
  members: ProxyNode[]
}

interface ServiceStatus {
  name: string
  status: "online" | "offline" | "slow"
  latency: number | null
  httpCode: number | null
}

interface MihomoStatus {
  ok: boolean
  active: boolean
  uptime_sec: number
  version: string
  mode: string
  tun: { enable: boolean }
  memory: number
  traffic: { up: number; down: number }
  connections: number
  upload_total: number
  download_total: number
  subscription: { url: string; last_update: number; last_update_iso: string }
}

interface ReachResult {
  id: string
  status: "ok" | "warn" | "fail"
  code: number | null
  latency_ms: number | null
  error: string
}

interface ClientInfo {
  ip: string
  connections: number
  upload_bytes: number
  download_bytes: number
  upload_rate: number
  download_rate: number
  rule: string
  chain: string
  host_recent: string
}

interface WanSpeedResult {
  ok: boolean
  ping: number
  download: number
  upload: number
}

const SERVICE_NAME_MAP: Record<string, string> = {
  wechat: "微信",
  bilibili: "哔哩哔哩",
  taobao: "淘宝",
  baidu: "百度",
  douyin: "抖音",
  google: "Google",
  youtube: "YouTube",
  github: "GitHub",
  twitter: "X/Twitter",
  chatgpt: "ChatGPT",
}

function Tabs({
  tabs,
  active,
  onChange,
}: {
  tabs: { id: string; label: string }[]
  active: string
  onChange: (id: string) => void
}) {
  return (
    <div className="inline-flex items-center gap-0.5 rounded-xl bg-secondary/60 p-1">
      {tabs.map((tab) => (
        <button
          key={tab.id}
          onClick={() => onChange(tab.id)}
          className={cn(
            "px-3.5 py-1.5 text-sm rounded-lg transition-colors",
            active === tab.id
              ? "bg-card text-foreground shadow-card"
              : "text-muted-foreground hover:text-foreground",
          )}
        >
          {tab.label}
        </button>
      ))}
    </div>
  )
}

function Panel({ children, className }: { children: React.ReactNode; className?: string }) {
  return <div className={cn("p-4 rounded-xl bg-secondary/30", className)}>{children}</div>
}

function formatBytes(bytes: number): string {
  if (bytes === 0) return "0 B"
  const k = 1024
  const sizes = ["B", "KB", "MB", "GB", "TB"]
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + " " + sizes[i]
}

function formatBytesPerSec(bytes: number): string {
  return formatBytes(bytes) + "/s"
}

function formatDuration(seconds: number): string {
  const h = Math.floor(seconds / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  if (h > 0) return `${h}h ${m}m`
  return `${m}m`
}

export function NetworkHub() {
  const [activeTab, setActiveTab] = useState<"gateway" | "monitor" | "speed">("gateway")
  const [gatewayEnabled, setGatewayEnabled] = useState(true)
  const [routingMode, setRoutingMode] = useState<"rule" | "global" | "direct">("rule")
  const [selectedNode, setSelectedNode] = useState("")
  const [isRefreshing, setIsRefreshing] = useState(false)
  const [groups, setGroups] = useState<ProxyGroup[]>([])
  const [nodesLoading, setNodesLoading] = useState(false)
  const [nodesError, setNodesError] = useState<string | null>(null)
  const [status, setStatus] = useState<MihomoStatus | null>(null)
  const [statusLoading, setStatusLoading] = useState(false)
  const [statusError, setStatusError] = useState<string | null>(null)
  const [reachResults, setReachResults] = useState<ServiceStatus[]>([])
  const [reachLoading, setReachLoading] = useState(false)
  const [reachError, setReachError] = useState<string | null>(null)
  const [subRefreshing, setSubRefreshing] = useState(false)
  const [subError, setSubError] = useState<string | null>(null)
  const [subInfo, setSubInfo] = useState<{ lastUpdate: string; proxyCount: number } | null>(null)
  const [clients, setClients] = useState<ClientInfo[]>([])
  const [clientsLoading, setClientsLoading] = useState(false)
  const [clientNames, setClientNames] = useState<Record<string, string>>({})
  const [expandedGroups, setExpandedGroups] = useState<Set<string>>(new Set())

  const fetchStatus = useCallback(async () => {
    setStatusLoading(true)
    setStatusError(null)
    try {
      const res = await fetch("/api/mihomo/status")
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      const data = await res.json()
      if (!data.ok) throw new Error("Backend returned ok: false")
      setStatus(data)
      setGatewayEnabled(data.active)
      const mode = data.mode as "rule" | "global" | "direct"
      if (["rule", "global", "direct"].includes(mode)) {
        setRoutingMode(mode)
      }
    } catch (err) {
      setStatusError(err instanceof Error ? err.message : "Failed to fetch status")
    } finally {
      setStatusLoading(false)
    }
  }, [])

  const fetchNodes = useCallback(async () => {
    setNodesLoading(true)
    setNodesError(null)
    try {
      const res = await fetch("/api/mihomo/groups")
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      const data = await res.json()
      if (!data.ok) throw new Error("Backend returned ok: false")
      setGroups(data.groups || [])
      // Set selected node from first group's current selection
      if (data.groups && data.groups.length > 0 && !selectedNode) {
        const firstGroup = data.groups[0]
        if (firstGroup.now) {
          setSelectedNode(`${firstGroup.name}::${firstGroup.now}`)
        }
      }
    } catch (err) {
      setNodesError(err instanceof Error ? err.message : "Failed to fetch nodes")
    } finally {
      setNodesLoading(false)
    }
  }, [selectedNode])

  const fetchReach = useCallback(async () => {
    setReachLoading(true)
    setReachError(null)
    try {
      const res = await fetch("/api/reach/check-all")
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      const data = await res.json()
      if (!data.ok) throw new Error("Backend returned ok: false")
      const mapped: ServiceStatus[] = data.results.map((r: ReachResult) => ({
        name: SERVICE_NAME_MAP[r.id] || r.id,
        status: r.status === "ok" ? "online" : r.status === "warn" ? "slow" : "offline",
        latency: r.latency_ms,
        httpCode: r.code,
      }))
      setReachResults(mapped)
    } catch (err) {
      setReachError(err instanceof Error ? err.message : "Failed to fetch reachability")
    } finally {
      setReachLoading(false)
    }
  }, [])

  const fetchClients = useCallback(async () => {
    setClientsLoading(true)
    try {
      const res = await fetch("/api/mihomo/clients")
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      const data = await res.json()
      if (!data.ok) throw new Error("Backend returned ok: false")
      setClients(data.clients || [])
    } catch (err) {
      console.error("Failed to fetch clients:", err)
    } finally {
      setClientsLoading(false)
    }
  }, [])

  const fetchClientNames = useCallback(async () => {
    try {
      const res = await fetch("/api/clients/names")
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      const data = await res.json()
      if (!data.ok) throw new Error("Backend returned ok: false")
      setClientNames(data.names || {})
    } catch (err) {
      console.error("Failed to fetch client names:", err)
    }
  }, [])

  useEffect(() => {
    if (activeTab === "gateway") {
      fetchStatus()
      fetchNodes()
      fetchClients()
      fetchClientNames()
      // Poll clients every 3s
      const interval = setInterval(fetchClients, 3000)
      return () => clearInterval(interval)
    }
  }, [activeTab, fetchStatus, fetchNodes, fetchClients, fetchClientNames])

  useEffect(() => {
    if (activeTab === "monitor") {
      fetchReach()
    }
  }, [activeTab, fetchReach])

  const handleRefresh = async () => {
    setIsRefreshing(true)
    await Promise.all([fetchStatus(), fetchNodes(), fetchClients()])
    setIsRefreshing(false)
  }

  const handleNodeSwitch = async (groupName: string, nodeName: string) => {
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
      // Refresh to get updated selection
      await fetchNodes()
    } catch (err) {
      console.error("Node switch failed:", err)
    }
  }

  const handleModeSwitch = async (mode: "rule" | "global" | "direct") => {
    setRoutingMode(mode)
    try {
      const res = await fetch("/api/mihomo/mode", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ mode }),
      })
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      const data = await res.json()
      if (!data.ok) throw new Error("Mode switch failed")
    } catch (err) {
      console.error("Mode switch failed:", err)
    }
  }

  const handleSubRefresh = async () => {
    setSubRefreshing(true)
    setSubError(null)
    try {
      const res = await fetch("/api/mihomo/sub/refresh", { method: "POST" })
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      const data = await res.json()
      if (!data.ok) throw new Error("Refresh failed")
      setSubInfo({ lastUpdate: "刚刚", proxyCount: data.proxy_count })
      await fetchNodes()
    } catch (err) {
      setSubError(err instanceof Error ? err.message : "Refresh failed")
    } finally {
      setSubRefreshing(false)
    }
  }

  const domesticServices = reachResults.filter((s) =>
    ["微信", "哔哩哔哩", "淘宝", "百度", "抖音"].includes(s.name)
  )
  const internationalServices = reachResults.filter((s) =>
    ["Google", "YouTube", "GitHub", "X/Twitter", "ChatGPT"].includes(s.name)
  )

  const totalNodes = groups.reduce((sum, g) => sum + g.members.length, 0)

  return (
    <div className="h-full flex flex-col">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h2 className="text-lg font-semibold tracking-tight">网络枢纽</h2>
          <p className="text-sm text-muted-foreground mt-1">网关、连通性与测速</p>
        </div>
        <Tabs
          tabs={[
            { id: "gateway", label: "网关控制" },
            { id: "monitor", label: "连通监测" },
            { id: "speed", label: "测速" },
          ]}
          active={activeTab}
          onChange={(id) => setActiveTab(id as "gateway" | "monitor" | "speed")}
        />
      </div>

      {activeTab === "gateway" && (
        <div className="flex-1 flex flex-col gap-5 overflow-auto cascade">
          {/* ── 1. Overall Status ── */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
            {/* Service Status */}
            <div className="card-premium p-4">
              <div className="flex items-center justify-between mb-3">
                <div className="flex items-center gap-2">
                  <div className={cn("w-2 h-2 rounded-full", gatewayEnabled ? "bg-success" : "bg-muted-foreground")} />
                  <span className="text-sm font-semibold">代理服务</span>
                </div>
                <span className={cn("text-xs font-medium px-2 py-0.5 rounded-full", gatewayEnabled ? "bg-success/10 text-success" : "bg-muted/50 text-muted-foreground")}>
                  {gatewayEnabled ? "运行中" : "已停止"}
                </span>
              </div>
              {status && (
                <p className="text-sm text-muted-foreground font-mono">
                  {status.version}
                </p>
              )}
            </div>

            {/* Traffic */}
            <div className="card-premium p-4">
              <div className="flex items-center gap-2 mb-3">
                <ArrowUpDown className="w-4 h-4 text-muted-foreground" strokeWidth={1.5} />
                <span className="text-sm font-semibold">实时流量</span>
              </div>
              {status ? (
                <div className="flex items-center gap-4">
                  <div>
                    <p className="text-xs text-muted-foreground mb-0.5">上传</p>
                    <p className="text-base font-mono font-semibold">{formatBytes(status.traffic.up)}<span className="text-xs text-muted-foreground ml-1">/s</span></p>
                  </div>
                  <div className="w-px h-8 bg-border" />
                  <div>
                    <p className="text-xs text-muted-foreground mb-0.5">下载</p>
                    <p className="text-base font-mono font-semibold">{formatBytes(status.traffic.down)}<span className="text-xs text-muted-foreground ml-1">/s</span></p>
                  </div>
                </div>
              ) : (
                <p className="text-sm text-muted-foreground">--</p>
              )}
            </div>

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
          </div>

          {/* ── 2. Subscription ── */}
          <div>
            <h3 className="section-header">订阅</h3>
            <div className="card-premium p-4">
              <div className="flex items-center justify-between mb-3">
                <div className="flex items-center gap-2">
                  <Globe className="w-4 h-4 text-muted-foreground" strokeWidth={1.5} />
                  <span className="text-sm font-semibold">订阅链接</span>
                </div>
                <div className="flex items-center gap-3">
                  <span className="text-xs text-muted-foreground font-mono">
                    {subInfo
                      ? `${subInfo.proxyCount} 节点`
                      : `${totalNodes} 节点`}
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
          </div>

          {/* ── 3. Node Groups ── */}
          <div className="flex-1">
            <h3 className="section-header">代理节点</h3>
            {nodesLoading ? (
              <p className="text-sm text-muted-foreground px-1">加载节点中...</p>
            ) : nodesError ? (
              <p className="text-sm text-destructive px-1">{nodesError}</p>
            ) : groups.length === 0 ? (
              <p className="text-sm text-muted-foreground px-1">暂无节点</p>
            ) : (
              <div className="flex flex-col gap-3">
                {groups.map((group) => {
                  const isExpanded = expandedGroups.has(group.name)
                  return (
                    <div key={group.name} className="card-premium overflow-hidden">
                      {/* Group header */}
                      <button
                        onClick={() => {
                          const next = new Set(expandedGroups)
                          if (next.has(group.name)) next.delete(group.name)
                          else next.add(group.name)
                          setExpandedGroups(next)
                        }}
                        className="w-full flex items-center gap-3 px-4 py-3 text-left hover:bg-secondary/20 transition-colors"
                      >
                        <ChevronDown className={cn(
                          "w-4 h-4 text-muted-foreground shrink-0 transition-transform duration-200",
                          !isExpanded && "-rotate-90"
                        )} strokeWidth={1.5} />
                        <span className="text-sm font-semibold">{group.name}</span>
                        <span className="text-xs text-muted-foreground font-mono bg-secondary/50 px-2 py-0.5 rounded-md">
                          {group.type}
                        </span>
                        <span className="text-xs text-muted-foreground ml-auto">
                          {group.now}
                        </span>
                      </button>

                      {/* Expanded node list — horizontal chips */}
                      {isExpanded && (
                        <div className="px-4 pb-4">
                          <div className="flex flex-wrap gap-2">
                            {group.members.map((node) => {
                              const isActive = group.now === node.name
                              return (
                                <button
                                  key={`${group.name}::${node.name}`}
                                  onClick={() => handleNodeSwitch(group.name, node.name)}
                                  className={cn("node-chip", isActive && "active")}
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

          {/* ── 4. Routing Mode ── */}
          <div>
            <h3 className="section-header">路由</h3>
            <div className="card-premium p-1">
              <div className="flex items-center gap-1">
                {(["rule", "global", "direct"] as const).map((mode) => (
                  <button
                    key={mode}
                    onClick={() => handleModeSwitch(mode)}
                    className={cn(
                      "flex-1 py-2.5 rounded-lg text-sm font-medium transition-all duration-200",
                      routingMode === mode
                        ? "bg-card text-foreground shadow-sm"
                        : "text-muted-foreground hover:text-foreground"
                    )}
                  >
                    {mode === "rule" && "规则分流"}
                    {mode === "global" && "全局代理"}
                    {mode === "direct" && "直连模式"}
                  </button>
                ))}
              </div>
            </div>
          </div>

          {/* ── 5. Client Monitor ── */}
          <div>
            <h3 className="section-header">客户端</h3>
            <div className="card-premium p-4">
              {clientsLoading && clients.length === 0 ? (
                <p className="text-sm text-muted-foreground">加载中...</p>
              ) : clients.length === 0 ? (
                <p className="text-sm text-muted-foreground">暂无活动客户端</p>
              ) : (
                <div className="flex flex-col gap-2">
                  {clients.map((client) => (
                    <div
                      key={client.ip}
                      className="flex items-center gap-3 px-3 py-2.5 rounded-xl bg-secondary/20"
                    >
                      <div className="w-8 h-8 rounded-lg bg-secondary/50 flex items-center justify-center shrink-0">
                        <span className="text-xs font-mono font-semibold">{client.ip.split('.').pop()}</span>
                      </div>
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2">
                          <span className="text-sm font-medium font-mono">{client.ip}</span>
                          {clientNames[client.ip] && (
                            <span className="text-sm text-muted-foreground">({clientNames[client.ip]})</span>
                          )}
                          <span className="text-xs text-muted-foreground">{client.connections} 连接</span>
                        </div>
                        <div className="flex items-center gap-3 mt-0.5">
                          <span className="text-xs text-muted-foreground font-mono">
                            ↑ {formatBytesPerSec(client.upload_rate)}
                          </span>
                          <span className="text-xs text-muted-foreground font-mono">
                            ↓ {formatBytesPerSec(client.download_rate)}
                          </span>
                        </div>
                      </div>
                      <span className={cn(
                        "text-xs px-2 py-0.5 rounded-full font-medium shrink-0",
                        client.chain.includes("DIRECT") ? "bg-success/10 text-success" : "bg-primary/10 text-primary"
                      )}>
                        {client.chain.includes("DIRECT") ? "直连" : "代理"}
                      </span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {activeTab === "monitor" && (
        <div className="flex-1 flex flex-col gap-4 overflow-auto cascade">
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-medium text-muted-foreground">服务连通性检测</h3>
            <button
              onClick={fetchReach}
              disabled={reachLoading}
              className="flex items-center gap-2 px-3 py-1.5 bg-foreground text-background rounded-lg text-sm font-medium hover:opacity-90 transition-opacity disabled:opacity-50"
            >
              <RefreshCw className={cn("w-3.5 h-3.5", reachLoading && "animate-spin")} strokeWidth={1.5} />
              {reachLoading ? "检测中..." : "全部检测"}
            </button>
          </div>

          {reachError && (
            <div className="p-3 bg-destructive/10 rounded-lg">
              <p className="text-sm text-destructive">{reachError}</p>
            </div>
          )}

          {/* Domestic Services */}
          <Panel>
            <h4 className="text-sm font-medium mb-3 flex items-center gap-2">
              <span className="w-1.5 h-1.5 rounded-full bg-chart-3" />
              国内服务
            </h4>
            {reachLoading && domesticServices.length === 0 ? (
              <p className="text-sm text-muted-foreground">检测中...</p>
            ) : (
              <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-5 gap-2">
                {domesticServices.map((service) => (
                  <ServiceCard key={service.name} service={service} />
                ))}
              </div>
            )}
          </Panel>

          {/* International Services */}
          <Panel>
            <h4 className="text-sm font-medium mb-3 flex items-center gap-2">
              <span className="w-1.5 h-1.5 rounded-full bg-chart-1" />
              国际服务
            </h4>
            {reachLoading && internationalServices.length === 0 ? (
              <p className="text-sm text-muted-foreground">检测中...</p>
            ) : (
              <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-5 gap-2">
                {internationalServices.map((service) => (
                  <ServiceCard key={service.name} service={service} />
                ))}
              </div>
            )}
          </Panel>
        </div>
      )}

      {activeTab === "speed" && (
        <div className="flex-1 flex flex-col gap-4 cascade">
          <SpeedTest />
        </div>
      )}
    </div>
  )
}

function statusColor(status: ServiceStatus["status"]) {
  if (status === "online") return "bg-success"
  if (status === "slow") return "bg-warning"
  return "bg-destructive"
}

function ServiceCard({ service }: { service: ServiceStatus }) {
  return (
    <div className="p-3 bg-card rounded-lg">
      <div className="flex items-center justify-between mb-2">
        <span className="text-sm font-medium truncate">{service.name}</span>
        <span className={cn("w-1.5 h-1.5 rounded-full shrink-0", statusColor(service.status))} />
      </div>
      <div className="flex items-center gap-2 font-mono">
        {service.latency !== null ? (
          <span className="text-sm text-muted-foreground">{service.latency}ms</span>
        ) : (
          <span className="text-sm text-destructive">不可达</span>
        )}
        {service.httpCode !== null && <span className="text-sm text-muted-foreground/60">{service.httpCode}</span>}
      </div>
    </div>
  )
}

function SpeedTest() {
  const [isRunning, setIsRunning] = useState(false)
  const [testType, setTestType] = useState<"lan" | "wan" | null>(null)
  const [results, setResults] = useState({
    lan: { download: 0, upload: 0 },
    wan: { ping: 0, download: 0, upload: 0 },
  })
  const [error, setError] = useState<string | null>(null)

  const runLanTest = async () => {
    setIsRunning(true)
    setTestType("lan")
    setError(null)
    try {
      const downloadStart = performance.now()
      const downloadRes = await fetch("/api/speedtest/lan?size=50")
      if (!downloadRes.ok) throw new Error(`HTTP ${downloadRes.status}`)
      await downloadRes.arrayBuffer()
      const downloadMs = performance.now() - downloadStart
      const downloadMBps = (50 * 8) / (downloadMs / 1000)

      const uploadData = new Uint8Array(10 * 1024 * 1024)
      crypto.getRandomValues(uploadData)
      const uploadStart = performance.now()
      const uploadRes = await fetch("/api/speedtest/lan-upload", {
        method: "POST",
        body: uploadData,
      })
      if (!uploadRes.ok) throw new Error(`HTTP ${uploadRes.status}`)
      await uploadRes.text()
      const uploadMs = performance.now() - uploadStart
      const uploadMBps = (10 * 8) / (uploadMs / 1000)

      setResults((prev) => ({
        ...prev,
        lan: { download: Math.round(downloadMBps * 10) / 10, upload: Math.round(uploadMBps * 10) / 10 },
      }))
    } catch (err) {
      setError(err instanceof Error ? err.message : "LAN test failed")
    } finally {
      setIsRunning(false)
      setTestType(null)
    }
  }

  const runWanTest = async () => {
    setIsRunning(true)
    setTestType("wan")
    setError(null)
    try {
      const res = await fetch("/api/speedtest/wan")
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      const data: WanSpeedResult = await res.json()
      if (!data.ok) throw new Error("Backend returned ok: false")
      setResults((prev) => ({
        ...prev,
        wan: { ping: data.ping, download: data.download, upload: data.upload },
      }))
    } catch (err) {
      setError(err instanceof Error ? err.message : "WAN test failed")
    } finally {
      setIsRunning(false)
      setTestType(null)
    }
  }

  const Metric = ({ label, value, unit }: { label: string; value: string | number; unit: string }) => (
    <div className="p-4 bg-card rounded-lg text-center">
      <p className="text-sm text-muted-foreground mb-1.5">{label}</p>
      <p className="text-2xl font-mono tracking-tight">{value}</p>
      <p className="text-sm text-muted-foreground/70 mt-0.5">{unit}</p>
    </div>
  )

  return (
    <>
      {error && (
        <div className="p-3 bg-destructive/10 rounded-lg">
          <p className="text-sm text-destructive">{error}</p>
        </div>
      )}

      {/* LAN Speed Test */}
      <Panel>
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-2">
            <Zap className="w-4 h-4 text-muted-foreground" strokeWidth={1.5} />
            <span className="text-sm font-medium">局域网测速</span>
          </div>
          <button
            onClick={runLanTest}
            disabled={isRunning}
            className="px-4 py-1.5 bg-foreground text-background rounded-lg text-sm font-medium hover:opacity-90 disabled:opacity-50 transition-opacity"
          >
            {isRunning && testType === "lan" ? "测试中" : "开始测试"}
          </button>
        </div>
        <div className="grid grid-cols-2 gap-2">
          <Metric label="下载速度" value={results.lan.download || "--"} unit="Mbps" />
          <Metric label="上传速度" value={results.lan.upload || "--"} unit="Mbps" />
        </div>
      </Panel>

      {/* WAN Speed Test */}
      <Panel>
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-2">
            <Activity className="w-4 h-4 text-muted-foreground" strokeWidth={1.5} />
            <span className="text-sm font-medium">互联网测速</span>
            <span className="text-sm text-muted-foreground/70">via speedtest.net</span>
          </div>
          <button
            onClick={runWanTest}
            disabled={isRunning}
            className="px-4 py-1.5 bg-foreground text-background rounded-lg text-sm font-medium hover:opacity-90 disabled:opacity-50 transition-opacity"
          >
            {isRunning && testType === "wan" ? "测试中" : "开始测试"}
          </button>
        </div>
        <div className="grid grid-cols-3 gap-2">
          <Metric label="Ping" value={results.wan.ping || "--"} unit="ms" />
          <Metric label="下载" value={results.wan.download || "--"} unit="Mbps" />
          <Metric label="上传" value={results.wan.upload || "--"} unit="Mbps" />
        </div>
      </Panel>
    </>
  )
}
