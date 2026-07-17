"use client"

import { useState, useEffect } from "react"
import Link from "next/link"
import {
  FolderOpen,
  Network,
  Lightbulb,
  History,
  GitBranch,
  ArrowUpRight,
  Upload,
  Zap,
  Activity,
  Bot,
  FileText,
  Clock,
  ChevronRight,
  MessageSquare,
  Globe,
} from "lucide-react"
import { cn } from "@/lib/utils"

/* ─── Types ────────────────────────────────────────── */

interface ApiFile {
  filename: string
  size_human: string
  mtime_iso: string
  remain_hours: number
}

interface MihomoStatus {
  ok: boolean
  active: boolean
  mode: string
  connections: number
  traffic: { up: number; down: number }
  upload_total: number
  download_total: number
  effective_node?: string
}

interface HistoryMeta {
  totalSessions: number
  totalMessages: number
  generatedAt: string
}

interface HistorySession {
  sessionId: string
  title: string
  project: string
  messageCount: number
  startTime: string
}

interface DailyNewsItem {
  title: string
  date: string
  category: string
}

interface GraphMeta {
  nodes: number
  edges: number
}

/* ─── Dashboard Card Component ─────────────────────── */

function DashboardCard({
  href,
  icon: Icon,
  title,
  subtitle,
  children,
  className,
  accent = "primary",
}: {
  href: string
  icon: React.ElementType
  title: string
  subtitle?: string
  children: React.ReactNode
  className?: string
  accent?: "primary" | "chart-3" | "chart-4" | "chart-5" | "chart-2"
}) {
  const accentColors: Record<string, string> = {
    primary: "text-primary",
    "chart-3": "text-chart-3",
    "chart-4": "text-chart-4",
    "chart-5": "text-chart-5",
    "chart-2": "text-chart-2",
  }

  return (
    <Link
      href={href}
      className={cn(
        "group block rounded-2xl p-5 sm:p-6 bg-card border border-border/40",
        "shadow-[var(--shadow-card)] hover:shadow-[var(--shadow-pop)]",
        "transition-all duration-300 hover:-translate-y-0.5",
        className
      )}
    >
      <div className="flex items-start justify-between mb-4">
        <div className="flex items-center gap-3">
          <div className={cn("w-10 h-10 rounded-xl bg-secondary/60 flex items-center justify-center", accentColors[accent])}>
            <Icon className="w-5 h-5" strokeWidth={1.5} />
          </div>
          <div>
            <h3 className="text-base font-semibold leading-none">{title}</h3>
            {subtitle && <p className="text-xs text-muted-foreground mt-1">{subtitle}</p>}
          </div>
        </div>
        <ArrowUpRight
          className="w-4 h-4 text-muted-foreground/40 group-hover:text-muted-foreground transition-colors"
          strokeWidth={1.5}
        />
      </div>
      <div className="space-y-3">{children}</div>
    </Link>
  )
}

/* ─── Helpers ──────────────────────────────────────── */

function fmtBytes(bytes: number): string {
  if (bytes >= 1e9) return `${(bytes / 1e9).toFixed(2)} GB`
  if (bytes >= 1e6) return `${(bytes / 1e6).toFixed(1)} MB`
  if (bytes >= 1e3) return `${(bytes / 1e3).toFixed(1)} KB`
  return `${bytes} B`
}

function fmtRate(bps: number): string {
  if (bps >= 1e6) return `${(bps / 1e6).toFixed(1)} MB/s`
  if (bps >= 1e3) return `${(bps / 1e3).toFixed(1)} KB/s`
  return `${bps.toFixed(0)} B/s`
}

function fmtTimeAgo(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime()
  const min = Math.floor(diff / 60000)
  if (min < 1) return "刚刚"
  if (min < 60) return `${min} 分钟前`
  const h = Math.floor(min / 60)
  if (h < 24) return `${h} 小时前`
  const d = Math.floor(h / 24)
  return `${d} 天前`
}

/* ─── Main Dashboard ───────────────────────────────── */

export default function DashboardPage() {
  const [files, setFiles] = useState<ApiFile[]>([])
  const [mihomo, setMihomo] = useState<MihomoStatus | null>(null)
  const [historyMeta, setHistoryMeta] = useState<HistoryMeta | null>(null)
  const [historySessions, setHistorySessions] = useState<HistorySession[]>([])
  const [news, setNews] = useState<DailyNewsItem | null>(null)
  const [graphMeta, setGraphMeta] = useState<GraphMeta | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let mounted = true
    setLoading(true)

    Promise.all([
      fetch("/api/files")
        .then((r) => (r.ok ? r.json() : []))
        .then((d) => mounted && setFiles(d.files?.slice(0, 3) || [])),
      fetch("/api/mihomo/status")
        .then((r) => (r.ok ? r.json() : null))
        .then((d) => mounted && setMihomo(d)),
      fetch("/api/claude-history")
        .then((r) => (r.ok ? r.json() : null))
        .then((d) => {
          if (!mounted || !d) return
          setHistoryMeta(d.meta)
          setHistorySessions(d.sessions?.slice(0, 3) || [])
        }),
      fetch("/api/intel/articles?unread=1&per_page=1")
        .then((r) => (r.ok ? r.json() : null))
        .then((d) => {
          if (!mounted || !d?.articles?.length) return
          const a = d.articles[0]
          setNews({
            title: a.title,
            date: a.published_at?.split("T")[0] || "",
            category: a.category,
          })
        }),
      fetch("/api/knowledge/graph")
        .then((r) => (r.ok ? r.json() : null))
        .then((d) => {
          if (!mounted || !d) return
          setGraphMeta({ nodes: d.nodes?.length || 0, edges: d.edges?.length || 0 })
        }),
    ]).finally(() => mounted && setLoading(false))

    // Refresh mihomo traffic every 3s
    const trafficInterval = setInterval(() => {
      fetch("/api/mihomo/status")
        .then((r) => (r.ok ? r.json() : null))
        .then((d) => mounted && d && setMihomo(d))
    }, 3000)

    return () => {
      mounted = false
      clearInterval(trafficInterval)
    }
  }, [])

  return (
    <div className="p-6 sm:p-8 max-w-6xl mx-auto">
      {/* Header */}
      <div className="mb-8">
        <h1 className="text-2xl font-bold tracking-tight">概览</h1>
        <p className="text-sm text-muted-foreground mt-1">
          星云运转中 · {new Date().toLocaleDateString("zh-CN", { month: "long", day: "numeric", weekday: "long" })}
        </p>
      </div>

      {loading ? (
        <div className="flex items-center justify-center py-24">
          <div className="w-8 h-8 border-2 border-primary/30 border-t-primary rounded-full animate-spin" />
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-5">
          {/* ── File Hub Card ── */}
          <DashboardCard
            href="/files"
            icon={FolderOpen}
            title="文件中心"
            subtitle="快速交换"
            accent="chart-2"
          >
            {files.length > 0 ? (
              <div className="space-y-2">
                {files.map((f) => (
                  <div
                    key={f.filename}
                    className="flex items-center gap-2.5 text-sm py-1.5 px-2 rounded-lg bg-secondary/30"
                  >
                    <FileText className="w-3.5 h-3.5 text-muted-foreground shrink-0" strokeWidth={1.5} />
                    <span className="flex-1 truncate font-medium">{f.filename}</span>
                    <span className="text-xs text-muted-foreground shrink-0">{f.size_human}</span>
                  </div>
                ))}
              </div>
            ) : (
              <div className="flex flex-col items-center justify-center py-4 text-muted-foreground/60 gap-2">
                <Upload className="w-5 h-5" strokeWidth={1.5} />
                <span className="text-sm">暂无文件 · 点击上传</span>
              </div>
            )}
          </DashboardCard>

          {/* ── Network Hub Card ── */}
          <DashboardCard
            href="/network"
            icon={Network}
            title="网络枢纽"
            subtitle={mihomo?.active ? "代理在线" : "代理离线"}
            accent="primary"
          >
            {mihomo?.active ? (
              <div className="space-y-3">
                <div className="flex items-center gap-2">
                  <span className="w-2 h-2 rounded-full bg-success animate-pulse-soft" />
                  <span className="text-sm font-medium">{mihomo.mode || "全局"} 模式</span>
                  <span className="text-xs text-muted-foreground ml-auto">
                    {mihomo.connections} 连接
                  </span>
                </div>
                {mihomo.effective_node && (
                  <div className="flex items-center gap-2 px-3 py-2 rounded-lg bg-secondary/30">
                    <Globe className="w-3.5 h-3.5 text-muted-foreground" strokeWidth={1.5} />
                    <span className="text-xs text-muted-foreground">生效节点</span>
                    <span className="text-sm font-medium truncate ml-auto">{mihomo.effective_node}</span>
                  </div>
                )}
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  <div className="px-3 py-2 rounded-lg bg-secondary/30">
                    <div className="flex items-center gap-1.5 text-xs text-muted-foreground mb-0.5">
                      <Activity className="w-3 h-3" strokeWidth={1.5} />
                      上行
                    </div>
                    <div className="text-sm font-mono font-medium">
                      {fmtRate(mihomo.traffic?.up || 0)}
                    </div>
                  </div>
                  <div className="px-3 py-2 rounded-lg bg-secondary/30">
                    <div className="flex items-center gap-1.5 text-xs text-muted-foreground mb-0.5">
                      <Activity className="w-3 h-3" strokeWidth={1.5} />
                      下行
                    </div>
                    <div className="text-sm font-mono font-medium">
                      {fmtRate(mihomo.traffic?.down || 0)}
                    </div>
                  </div>
                </div>
                <div className="flex flex-col sm:flex-row sm:items-center gap-1 sm:gap-3 text-xs text-muted-foreground px-1">
                  <span>总上行 {fmtBytes(mihomo.upload_total || 0)}</span>
                  <span className="hidden sm:inline opacity-40">·</span>
                  <span>总下行 {fmtBytes(mihomo.download_total || 0)}</span>
                </div>
              </div>
            ) : (
              <div className="flex items-center gap-2 py-4 text-muted-foreground/60">
                <Zap className="w-4 h-4" strokeWidth={1.5} />
                <span className="text-sm">代理未运行 · 点击管理</span>
              </div>
            )}
          </DashboardCard>

          {/* ── Claude History Card ── */}
          <DashboardCard
            href="/claude"
            icon={Bot}
            title="Claude 历史"
            subtitle={historyMeta ? `${historyMeta.totalSessions} 会话 · ${historyMeta.totalMessages} 消息` : undefined}
            accent="chart-5"
          >
            {historySessions.length > 0 ? (
              <div className="space-y-2">
                {historySessions.map((s) => (
                  <div
                    key={s.sessionId}
                    className="flex items-center gap-2.5 text-sm py-1.5 px-2 rounded-lg bg-secondary/30"
                  >
                    <MessageSquare className="w-3.5 h-3.5 text-muted-foreground shrink-0" strokeWidth={1.5} />
                    <span className="flex-1 truncate font-medium">{s.title}</span>
                    <span className="text-xs text-muted-foreground shrink-0">{s.messageCount} 条</span>
                  </div>
                ))}
              </div>
            ) : (
              <div className="flex items-center gap-2 py-4 text-muted-foreground/60">
                <Clock className="w-4 h-4" strokeWidth={1.5} />
                <span className="text-sm">暂无历史记录</span>
              </div>
            )}
          </DashboardCard>

          {/* ── Intelligence Card ── */}
          <DashboardCard
            href="/intel"
            icon={Lightbulb}
            title="情报站"
            subtitle="每日简报"
            accent="chart-4"
          >
            {news ? (
              <div className="space-y-2">
                <p className="text-sm font-medium leading-relaxed line-clamp-2">{news.title}</p>
                <div className="flex items-center gap-2 text-xs text-muted-foreground">
                  <span className="px-1.5 py-0.5 rounded bg-chart-4/10 text-chart-4">{news.category}</span>
                  <span>{news.date}</span>
                </div>
              </div>
            ) : (
              <div className="flex items-center gap-2 py-4 text-muted-foreground/60">
                <FileText className="w-4 h-4" strokeWidth={1.5} />
                <span className="text-sm">暂无今日简报</span>
              </div>
            )}
          </DashboardCard>

          {/* ── Knowledge Graph Card ── */}
          <DashboardCard
            href="/knowledge"
            icon={GitBranch}
            title="知识图谱"
            subtitle={graphMeta ? `${graphMeta.nodes} 节点 · ${graphMeta.edges} 关系` : undefined}
            accent="chart-3"
          >
            {graphMeta && graphMeta.nodes > 0 ? (
              <div className="space-y-3">
                <div className="flex items-center gap-4">
                  <div className="flex-1 px-3 py-2 rounded-lg bg-secondary/30 text-center">
                    <div className="text-lg font-bold font-mono">{graphMeta.nodes}</div>
                    <div className="text-[11px] text-muted-foreground">节点</div>
                  </div>
                  <div className="flex-1 px-3 py-2 rounded-lg bg-secondary/30 text-center">
                    <div className="text-lg font-bold font-mono">{graphMeta.edges}</div>
                    <div className="text-[11px] text-muted-foreground">关系</div>
                  </div>
                </div>
                <div className="flex items-center gap-1 text-xs text-muted-foreground">
                  <ChevronRight className="w-3 h-3" strokeWidth={1.5} />
                  <span>点击探索关联网络</span>
                </div>
              </div>
            ) : (
              <div className="flex items-center gap-2 py-4 text-muted-foreground/60">
                <GitBranch className="w-4 h-4" strokeWidth={1.5} />
                <span className="text-sm">暂无知识图谱数据</span>
              </div>
            )}
          </DashboardCard>

          {/* ── Quick Actions Card (filler for grid balance) ── */}
          <div className="rounded-2xl p-5 sm:p-6 bg-card/50 border border-dashed border-border/40 flex flex-col items-center justify-center text-center gap-3">
            <div className="w-12 h-12 rounded-2xl bg-secondary/40 flex items-center justify-center">
              <Zap className="w-6 h-6 text-muted-foreground/40" strokeWidth={1.5} />
            </div>
            <div>
              <p className="text-sm font-medium text-muted-foreground">更多功能开发中</p>
              <p className="text-xs text-muted-foreground/50 mt-0.5">Nebula 持续进化</p>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

