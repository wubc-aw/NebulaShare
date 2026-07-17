"use client"

import { useState, useEffect } from "react"
import { KnowledgeGraph, GraphData, SDK_NODE_COLORS } from "@/components/knowledge-graph"
import { AlertCircle, PanelRightClose, PanelRightOpen } from "lucide-react"
import { cn } from "@/lib/utils"

function isValidGraphData(obj: unknown): obj is GraphData {
  if (typeof obj !== "object" || obj === null) return false
  const d = obj as Record<string, unknown>
  if (!Array.isArray(d.nodes) || !Array.isArray(d.edges)) return false
  if (d.nodes.length > 0) {
    const first = d.nodes[0] as Record<string, unknown>
    const idType = typeof first.id
    if ((idType !== "string" && idType !== "number") || typeof first.type !== "string") return false
  }
  return true
}

const DIMENSION_CONFIG = [
  {
    type: "BusinessLogic",
    label: "业务逻辑",
    color: "text-blue-500",
    bgColor: "bg-blue-500/10",
    borderColor: "border-blue-500/30",
    dotColor: "bg-blue-500",
  },
  {
    type: "ProtocolLayer",
    label: "协议报文",
    color: "text-green-500",
    bgColor: "bg-green-500/10",
    borderColor: "border-green-500/30",
    dotColor: "bg-green-500",
  },
  {
    type: "TCUAction",
    label: "TCU回调",
    color: "text-amber-500",
    bgColor: "bg-amber-500/10",
    borderColor: "border-amber-500/30",
    dotColor: "bg-amber-500",
  },
  {
    type: "FaultScenario",
    label: "故障场景",
    color: "text-red-500",
    bgColor: "bg-red-500/10",
    borderColor: "border-red-500/30",
    dotColor: "bg-red-500",
  },
]

export default function SdkKnowledgePage() {
  const [data, setData] = useState<GraphData | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [activeTab, setActiveTab] = useState<"graph" | "business" | "protocol" | "tcu" | "fault">("graph")
  const [highlightNodeId, setHighlightNodeId] = useState<string | null>(null)
  const [navOpen, setNavOpen] = useState(true)
  const [expandedDims, setExpandedDims] = useState<Record<string, boolean>>({
    BusinessLogic: true,
    ProtocolLayer: true,
    TCUAction: true,
    FaultScenario: true,
  })

  useEffect(() => {
    fetch("/api/knowledge/sdk-graph")
      .then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`)
        return r.json()
      })
      .then((raw: GraphData) => {
        if (isValidGraphData(raw) && raw.nodes.length > 0) {
          const d: GraphData = {
            nodes: raw.nodes.map((n, i) => ({
              ...n,
              id: String(n.id),
              group: n.group ?? i % 10,
            })),
            edges: raw.edges.map((e) => ({
              ...e,
              source: String(e.source),
              target: String(e.target),
            })),
          }
          setData(d)
        } else {
          setError("无效的图谱数据")
        }
        setLoading(false)
      })
      .catch((err) => {
        setError(err.message || "加载失败")
        setLoading(false)
      })
  }, [])

  // Compute stats (semantic model) - exclude Layer nodes
  const bizNodes = data?.nodes.filter((n) => n.type === "BusinessLogic") || []
  const protoNodes = data?.nodes.filter((n) => n.type === "ProtocolLayer") || []
  const tcuNodes = data?.nodes.filter((n) => n.type === "TCUAction") || []
  const faultNodes = data?.nodes.filter((n) => n.type === "FaultScenario") || []

  const stats = data
    ? {
        nodes: bizNodes.length + protoNodes.length + tcuNodes.length + faultNodes.length,
        edges: data.edges.length,
        businessLogic: bizNodes.length,
        protocolCMD: protoNodes.length,
        tcuAction: tcuNodes.length,
        faultScenario: faultNodes.length,
      }
    : null

  // Get nodes for tab views (exclude is_category/is_layer)
  const faultScenarios = faultNodes.filter((n) => !n.is_category && !n.is_layer)
  const protocolCMDs = protoNodes.filter((n) => !n.is_category && !n.is_layer)
  const businessLogics = bizNodes.filter((n) => !n.is_category && !n.is_layer)
  const tcuActions = tcuNodes.filter((n) => !n.is_category && !n.is_layer)

  const toggleDim = (type: string) => {
    setExpandedDims((prev) => ({ ...prev, [type]: !prev[type] }))
  }

  if (loading) {
    return (
      <div className="p-6 sm:p-8 max-w-6xl mx-auto h-full flex items-center justify-center">
        <div className="w-8 h-8 border-2 border-primary/30 border-t-primary rounded-full animate-spin" />
      </div>
    )
  }

  if (error || !data) {
    return (
      <div className="p-6 sm:p-8 max-w-6xl mx-auto h-full flex items-center justify-center">
        <div className="text-center">
          <AlertCircle className="w-10 h-10 text-chart-2 mx-auto mb-3" />
          <p className="text-sm text-muted-foreground">{error || "暂无 SDK 知识图谱数据"}</p>
          <p className="text-xs text-muted-foreground/60 mt-2">请确保 /api/knowledge/sdk-graph 接口可用</p>
        </div>
      </div>
    )
  }

  return (
    <div className="p-6 sm:p-8 max-w-6xl mx-auto h-full flex flex-col">
      {/* Page Header */}
      <div className="mb-6">
        <h1 className="text-2xl font-bold tracking-tight">SDK 知识图谱</h1>
        <p className="text-sm text-muted-foreground mt-1">
          充电桩嵌入式 SDK 4.0 · 故障码 · 协议命令 · 接口调用链
        </p>
      </div>

      {/* Stats Cards - 4 Dimensions */}
      {stats && (
        <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-6 gap-3 mb-4">
          <StatCard label="节点" value={stats.nodes} color="text-foreground" />
          <StatCard label="关系" value={stats.edges} color="text-muted-foreground" />
          <StatCard label="业务逻辑" value={stats.businessLogic} color="text-blue-500" />
          <StatCard label="协议报文" value={stats.protocolCMD} color="text-green-500" />
          <StatCard label="TCU回调" value={stats.tcuAction} color="text-amber-500" />
          <StatCard label="故障场景" value={stats.faultScenario} color="text-red-500" />
        </div>
      )}

      {/* Tabs - 4 Dimensions */}
      <div className="flex gap-1 mb-3 bg-secondary/50 p-1 rounded-lg overflow-x-auto scrollbar-hide w-full sm:w-fit">
        {[
          { id: "graph" as const, label: "关系图谱" },
          { id: "business" as const, label: `业务逻辑 (${stats?.businessLogic || 0})` },
          { id: "protocol" as const, label: `协议报文 (${stats?.protocolCMD || 0})` },
          { id: "tcu" as const, label: `TCU回调 (${stats?.tcuAction || 0})` },
          { id: "fault" as const, label: `故障场景 (${stats?.faultScenario || 0})` },
        ].map((tab) => (
          <button
            key={tab.id}
            onClick={() => {
              setActiveTab(tab.id)
              setHighlightNodeId(null)
            }}
            className={cn(
              "px-3 py-1.5 rounded-md text-sm font-medium transition-colors whitespace-nowrap shrink-0",
              activeTab === tab.id
                ? "bg-card text-foreground shadow-sm"
                : "text-muted-foreground hover:text-foreground"
            )}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* Content */}
      <div className="flex-1 min-h-0">
        {activeTab === "graph" && (
          <div className="h-full bg-card rounded-2xl shadow-[var(--shadow-card)] border border-border/40 flex flex-col min-h-[500px] overflow-hidden">
            {/* Header */}
            <div className="flex items-center justify-between px-5 py-3 border-b border-border/30 shrink-0">
              <div>
                <h2 className="text-lg font-semibold tracking-tight">SDK 四维度知识图谱</h2>
                <p className="text-xs text-muted-foreground mt-0.5">
                  {data.nodes.length} 节点 · {data.edges.length} 关系 · 业务逻辑 · 协议报文 · TCU回调 · 故障码
                </p>
              </div>
              <button
                onClick={() => setNavOpen(!navOpen)}
                className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-xs font-medium text-muted-foreground hover:text-foreground hover:bg-secondary transition-colors"
              >
                {navOpen ? <PanelRightClose className="w-3.5 h-3.5" /> : <PanelRightOpen className="w-3.5 h-3.5" />}
                {navOpen ? "收起导航" : "展开导航"}
              </button>
            </div>

            {/* Graph + Navigation */}
            <div className="flex-1 flex flex-col lg:flex-row min-h-0">
              {/* Graph */}
              <div className="flex-1 min-w-0 min-h-[300px] lg:min-h-0 p-3">
                <div className="w-full h-full rounded-xl border border-border/40 overflow-hidden">
                  <KnowledgeGraph
                    data={data}
                    nodeColors={SDK_NODE_COLORS}
                    highlightNodeId={highlightNodeId}
                    onNodeSelect={(node) => setHighlightNodeId(node?.id || null)}
                  />
                </div>
              </div>

              {/* Right Navigation Panel */}
              {navOpen && (
                <div className="w-full lg:w-64 shrink-0 border-t lg:border-t-0 lg:border-l border-border/30 overflow-auto max-h-[240px] lg:max-h-none">
                  <div className="p-3 space-y-3">
                    <p className="text-xs font-medium text-muted-foreground px-1">节点导航</p>
                    {DIMENSION_CONFIG.map((dim) => {
                      const dimNodes = data.nodes.filter(
                        (n) => n.type === dim.type && !n.is_layer && !n.is_category
                      )
                      const expanded = expandedDims[dim.type] ?? true
                      return (
                        <div key={dim.type} className="rounded-lg border border-border/30 overflow-hidden">
                          <button
                            onClick={() => toggleDim(dim.type)}
                            className={cn(
                              "w-full flex items-center gap-2 px-3 py-2 text-xs font-medium transition-colors",
                              dim.bgColor
                            )}
                          >
                            <span className={cn("w-2 h-2 rounded-full", dim.dotColor)} />
                            <span className={cn("flex-1 text-left", dim.color)}>{dim.label}</span>
                            <span className="text-muted-foreground">{dimNodes.length}</span>
                            <span className="text-muted-foreground transition-transform">
                              {expanded ? "−" : "+"}
                            </span>
                          </button>
                          {expanded && (
                            <div className="px-1 py-1 space-y-0.5">
                              {dimNodes.map((node) => (
                                <button
                                  key={node.id}
                                  onClick={() => setHighlightNodeId(node.id)}
                                  className={cn(
                                    "w-full text-left px-2 py-1.5 rounded text-[11px] transition-colors truncate",
                                    highlightNodeId === node.id
                                      ? cn(dim.bgColor, "font-medium", dim.color)
                                      : "text-muted-foreground hover:text-foreground hover:bg-secondary/50"
                                  )}
                                  title={(node as any).label || node.id}
                                >
                                  {(node as any).label || node.id}
                                </button>
                              ))}
                            </div>
                          )}
                        </div>
                      )
                    })}
                  </div>
                </div>
              )}
            </div>
          </div>
        )}

        {activeTab === "business" && (
          <div className="h-full bg-card rounded-2xl p-5 shadow-[var(--shadow-card)] border border-border/40 overflow-auto">
            <h2 className="text-lg font-semibold tracking-tight mb-4">业务逻辑接口</h2>
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2">
              {businessLogics.map((node) => (
                <div
                  key={node.id}
                  className="p-3 rounded-lg bg-secondary/40 border border-border/30 hover:border-blue-500/30 transition-colors"
                >
                  <p className="text-xs font-semibold text-blue-400 truncate">{(node as any).label || node.id}</p>
                  <p className="text-[10px] text-muted-foreground mt-1">{node.type}</p>
                </div>
              ))}
            </div>
          </div>
        )}

        {activeTab === "protocol" && (
          <div className="h-full bg-card rounded-2xl p-5 shadow-[var(--shadow-card)] border border-border/40 overflow-auto">
            <h2 className="text-lg font-semibold tracking-tight mb-4">协议命令列表</h2>
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2">
              {protocolCMDs.map((node) => (
                <div
                  key={node.id}
                  className="p-3 rounded-lg bg-secondary/40 border border-border/30 hover:border-green-500/30 transition-colors"
                >
                  <div className="flex items-center gap-2 mb-1">
                    <span className="text-xs font-semibold text-green-500">
                      {(node as any).label || node.id}
                    </span>
                  </div>
                  <p className="text-xs text-muted-foreground">{(node as any).description || ""}</p>
                </div>
              ))}
            </div>
          </div>
        )}

        {activeTab === "tcu" && (
          <div className="h-full bg-card rounded-2xl p-5 shadow-[var(--shadow-card)] border border-border/40 overflow-auto">
            <h2 className="text-lg font-semibold tracking-tight mb-4">TCU回调接口（桩企需实现）</h2>
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2">
              {tcuActions.map((node) => (
                <div
                  key={node.id}
                  className="p-3 rounded-lg bg-secondary/40 border border-border/30 hover:border-amber-500/30 transition-colors"
                >
                  <p className="text-xs font-semibold text-amber-400 truncate">{(node as any).label || node.id}</p>
                  <p className="text-[10px] text-muted-foreground mt-1">{node.type}</p>
                </div>
              ))}
            </div>
          </div>
        )}

        {activeTab === "fault" && (
          <div className="h-full bg-card rounded-2xl p-5 shadow-[var(--shadow-card)] border border-border/40 overflow-auto">
            <h2 className="text-lg font-semibold tracking-tight mb-4">故障场景</h2>
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2">
              {faultScenarios.map((node) => (
                <div
                  key={node.id}
                  className="p-3 rounded-lg bg-secondary/40 border border-border/30 hover:border-red-500/30 transition-colors"
                >
                  <div className="flex items-center justify-between mb-1">
                    <span className="text-xs font-semibold text-red-400">
                      {(node as any).label || node.id}
                    </span>
                    <span className="text-[10px] px-1.5 py-0.5 rounded bg-red-500/10 text-red-400">
                      {(node as any).fault_count || 0} 个故障码
                    </span>
                  </div>
                  <p className="text-xs text-muted-foreground">{(node as any).description || ""}</p>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

function StatCard({ label, value, color }: { label: string; value: number; color: string }) {
  return (
    <div className="p-3 rounded-xl bg-card border border-border/40 text-center">
      <p className={cn("text-xl font-bold", color)}>{value}</p>
      <p className="text-[10px] text-muted-foreground mt-0.5">{label}</p>
    </div>
  )
}
