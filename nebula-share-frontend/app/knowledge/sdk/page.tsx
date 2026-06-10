"use client"

import { useState, useEffect } from "react"
import { KnowledgeGraph, GraphData, SDK_NODE_COLORS } from "@/components/knowledge-graph"
import { Cpu, AlertCircle, CheckCircle2 } from "lucide-react"
import { cn } from "@/lib/utils"

function isValidGraphData(obj: unknown): obj is GraphData {
  if (typeof obj !== "object" || obj === null) return false
  const d = obj as Record<string, unknown>
  if (!Array.isArray(d.nodes) || !Array.isArray(d.edges)) return false
  if (d.nodes.length > 0) {
    const first = d.nodes[0] as Record<string, unknown>
    if (typeof first.id !== "string" || typeof first.type !== "string") return false
  }
  return true
}

export default function SdkKnowledgePage() {
  const [data, setData] = useState<GraphData | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [activeTab, setActiveTab] = useState<"graph" | "fault" | "protocol" | "api">("graph")

  useEffect(() => {
    fetch("/api/knowledge/sdk-graph")
      .then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`)
        return r.json()
      })
      .then((d: GraphData) => {
        if (isValidGraphData(d) && d.nodes.length > 0) {
          // Add group field if not present
          d.nodes.forEach((n, i) => {
            if (!n.group) n.group = i % 10
          })
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

  // Compute stats
  const stats = data ? {
    nodes: data.nodes.length,
    edges: data.edges.length,
    faultCodes: data.nodes.filter((n) => n.type === "FaultCode").length,
    commands: data.nodes.filter((n) => n.type === "Command").length,
    protocols: data.nodes.filter((n) => n.type === "Protocol").length,
    dataFields: data.nodes.filter((n) => n.type === "DataField").length,
    dataStructs: data.nodes.filter((n) => n.type === "DataStruct").length,
    enums: data.nodes.filter((n) => n.type === "EnumType" || n.type === "EnumValue").length,
  } : null

  // Get fault codes for tab view
  const faultCodes = data?.nodes.filter((n) => n.type === "FaultCode") || []
  const protocols = data?.nodes.filter((n) => n.type === "Protocol") || []
  const commands = data?.nodes.filter((n) => n.type === "Command" && n.type !== "DataField") || []

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
          <p className="text-xs text-muted-foreground/60 mt-2">
            请确保 /api/knowledge/sdk-graph 接口可用
          </p>
        </div>
      </div>
    )
  }

  return (
    <div className="p-6 sm:p-8 max-w-6xl mx-auto h-full flex flex-col">
      {/* Page Header */}
      <div className="mb-6">
        <h1 className="text-2xl font-bold tracking-tight">🔋 SDK 知识图谱</h1>
        <p className="text-sm text-muted-foreground mt-1">
          充电桩嵌入式 SDK 4.0 · 故障码 · 协议命令 · 接口调用链
        </p>
      </div>

      {/* Stats Cards */}
      {stats && (
        <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-8 gap-3 mb-4">
          <StatCard label="节点" value={stats.nodes} color="text-foreground" />
          <StatCard label="关系" value={stats.edges} color="text-muted-foreground" />
          <StatCard label="故障码" value={stats.faultCodes} color="text-red-500" />
          <StatCard label="接口" value={stats.commands} color="text-blue-500" />
          <StatCard label="协议" value={stats.protocols} color="text-green-500" />
          <StatCard label="字段" value={stats.dataFields} color="text-amber-500" />
          <StatCard label="结构体" value={stats.dataStructs} color="text-purple-500" />
          <StatCard label="枚举" value={stats.enums} color="text-emerald-500" />
        </div>
      )}

      {/* Tabs */}
      <div className="flex gap-1 mb-3 bg-secondary/50 p-1 rounded-lg w-fit">
        {[
          { id: "graph" as const, label: "关系图谱" },
          { id: "fault" as const, label: `故障码 (${stats?.faultCodes || 0})` },
          { id: "protocol" as const, label: `协议命令 (${stats?.protocols || 0})` },
          { id: "api" as const, label: `接口 (${stats?.commands || 0})` },
        ].map((tab) => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            className={cn(
              "px-3 py-1.5 rounded-md text-sm font-medium transition-colors",
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
          <div className="h-full bg-card rounded-2xl p-5 sm:p-6 shadow-[var(--shadow-card)] border border-border/40 flex flex-col min-h-[500px]">
            <div className="flex items-center justify-between mb-3 shrink-0">
              <div>
                <h2 className="text-lg font-semibold tracking-tight">SDK 知识图谱</h2>
                <p className="text-xs text-muted-foreground mt-0.5">
                  {data.nodes.length} 节点 · {data.edges.length} 关系
                </p>
              </div>
            </div>
            <div className="flex-1 rounded-xl border border-border/40 overflow-hidden min-h-0">
              <KnowledgeGraph data={data} nodeColors={SDK_NODE_COLORS} />
            </div>
          </div>
        )}

        {activeTab === "fault" && (
          <div className="h-full bg-card rounded-2xl p-5 shadow-[var(--shadow-card)] border border-border/40 overflow-auto">
            <h2 className="text-lg font-semibold tracking-tight mb-4">🐛 故障码列表</h2>
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2">
              {faultCodes.map((node) => (
                <div
                  key={node.id}
                  className="p-3 rounded-lg bg-secondary/40 border border-border/30 hover:border-red-500/30 transition-colors"
                >
                  <div className="flex items-center gap-2 mb-1">
                    <span className="text-xs font-mono font-bold text-red-500">
                      {node.description || "未知代码"}
                    </span>
                  </div>
                  <p className="text-xs text-muted-foreground truncate">{node.label || node.id}</p>
                </div>
              ))}
            </div>
          </div>
        )}

        {activeTab === "protocol" && (
          <div className="h-full bg-card rounded-2xl p-5 shadow-[var(--shadow-card)] border border-border/40 overflow-auto">
            <h2 className="text-lg font-semibold tracking-tight mb-4">📡 协议命令列表</h2>
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2">
              {protocols.map((node) => (
                <div
                  key={node.id}
                  className="p-3 rounded-lg bg-secondary/40 border border-border/30 hover:border-green-500/30 transition-colors"
                >
                  <div className="flex items-center gap-2 mb-1">
                    <span className="text-xs font-mono font-bold text-green-500">
                      CMD_{node.label?.replace("CMD_", "") || node.id}
                    </span>
                  </div>
                  <p className="text-xs text-muted-foreground">{node.label || node.id}</p>
                </div>
              ))}
            </div>
          </div>
        )}

        {activeTab === "api" && (
          <div className="h-full bg-card rounded-2xl p-5 shadow-[var(--shadow-card)] border border-border/40 overflow-auto">
            <h2 className="text-lg font-semibold tracking-tight mb-4">🔌 接口函数列表</h2>
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2">
              {commands.slice(0, 200).map((node) => (
                <div
                  key={node.id}
                  className="p-3 rounded-lg bg-secondary/40 border border-border/30 hover:border-blue-500/30 transition-colors"
                >
                  <p className="text-xs font-mono text-blue-400 truncate">{node.label || node.id}</p>
                  <p className="text-[10px] text-muted-foreground mt-1">{node.type}</p>
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
