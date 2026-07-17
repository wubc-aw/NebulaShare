"use client"

import { useState, useEffect, useRef, useMemo } from "react"
import { MessageSquare, Clock, Folder, Hash, ChevronRight, Search, Calendar, Bot, User, BrainCircuit, Wrench, Monitor, HardDrive, BarChart3, Tag, Lightbulb, AlertCircle, Code2, GitBranch, Upload, XCircle, CheckCircle2, ScanLine, Play, Loader2, FileText, Layers, Network, Image as ImageIcon } from "lucide-react"
import { cn } from "@/lib/utils"

interface HistoryMessage { role: "user" | "assistant"; text: string; timestamp: string; hostname?: string; turnId?: string }
interface HistoryMedia { type: "image"; url: string; filename: string; turnId?: string }
interface DeviceInfo { hostname: string; machineId: string; localIp: string; platform: string; lastSync: string; sessions: number; messages: number }
interface UsageInfo { inputTokens: number; outputTokens: number; totalTokens: number; estimatedCost: number; toolCalls: number }
interface BehaviorInfo { dominantStyle: string; avgQuestionLength: number; followUpRatio: number; codeRatio: number; questionCount: number; responseCount: number }
interface KeyContentInfo { decisions: string[]; codeReferences: string[]; fileReferences: string[]; correctionsCount: number; conclusions: string[] }
interface HistorySession {
  sessionId: string; title: string; project: string; messageCount: number;
  startTime: string; endTime: string; messages: HistoryMessage[];
  hasFullDialog: boolean; source?: "claude" | "codex"; categories?: string[]; behavior?: BehaviorInfo;
  usage?: UsageInfo; keyContent?: KeyContentInfo; deviceName?: string; deviceId?: string; media?: HistoryMedia[];
}
interface HistoryData {
  meta: { generatedAt: string; totalSessions: number; totalMessages: number; projects: Record<string, number>; devices: Record<string, DeviceInfo>; deviceCount: number; categoryDistribution?: Record<string, number>; styleDistribution?: Record<string, number>; totalTokens?: { input: number; output: number; total: number; estimatedCostUSD: number }; sources?: Record<string, number> }
  sessions: HistorySession[]
}

const fmtTime = (iso: string) => new Date(iso).toLocaleString("zh-CN", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" })
const fmtDate = (iso: string) => new Date(iso).toLocaleDateString("zh-CN", { year: "numeric", month: "long", day: "numeric" })
const fmtDuration = (s: string, e: string) => { const m = Math.round((new Date(e).getTime() - new Date(s).getTime()) / 60000); if (m < 1) return "<1分"; if (m < 60) return `${m}分`; return `${Math.floor(m / 60)}时${m % 60}分` }
const fmtNum = (n: number) => n >= 1000000 ? `${(n / 1000000).toFixed(1)}M` : n >= 1000 ? `${(n / 1000).toFixed(1)}K` : `${n}`
const getProj = (p: string) => p === "/home/aw" ? "🏠 Home" : p === "/home/aw/vibeProjects" ? "📁 Projects" : p.replace("/home/aw/vibeProjects/", "📁 ")

const CAT_COLORS: Record<string, string> = { "技术实现": "bg-chart-1/15 text-chart-1", "问题排查": "bg-chart-2/15 text-chart-2", "设计讨论": "bg-chart-3/15 text-chart-3", "运维配置": "bg-chart-4/15 text-chart-4", "信息查询": "bg-chart-5/15 text-chart-5", "数据处理": "bg-primary/15 text-primary", "其他": "bg-muted/30 text-muted-foreground" }
const STYLE_ICONS: Record<string, string> = { "目标型": "🎯", "探索型": "🔍", "细节控": "🔬", "效率型": "⚡", "谨慎型": "🛡️", "平衡型": "⚖️" }

function renderMsg(text: string) {
  const parts: { type: string; content: string }[] = []
  let rem = text
  const th = rem.match(/^\[思考\]\s*([\s\S]*?)(?=\n(?:\[使用工具|\[工具结果|$))/)
  if (th) { parts.push({ type: "think", content: th[1].trim() }); rem = rem.slice(th[0].length).trim() }
  const tl = rem.match(/^\[使用工具:\s*([^\]]+)\]/)
  if (tl) { parts.push({ type: "tool", content: tl[1].trim() }); rem = rem.slice(tl[0].length).trim() }
  if (rem) parts.push({ type: "text", content: rem })
  if (!parts.length) parts.push({ type: "text", content: text })
  return parts
}

function MsgContent({ text }: { text: string }) {
  const [showThink, setShowThink] = useState(false)
  return (
    <div className="space-y-1.5">
      {renderMsg(text).map((p, i) => {
        if (p.type === "think") return (
          <div key={i}>
            <button onClick={() => setShowThink(!showThink)} className="flex items-center gap-1 text-[11px] text-muted-foreground/50 hover:text-muted-foreground transition-colors">
              <BrainCircuit className="w-3 h-3" strokeWidth={1.5} />{showThink ? "隐藏思考" : "显示思考"}
            </button>
            {showThink && <div className="mt-1 p-2 rounded bg-secondary/40 text-[11px] text-muted-foreground/80 whitespace-pre-wrap">{p.content}</div>}
          </div>)
        if (p.type === "tool") return <div key={i} className="flex items-center gap-1 text-[11px] text-chart-3"><Wrench className="w-3 h-3" strokeWidth={1.5} /><span>工具: {p.content}</span></div>
        return <p key={i} className="text-sm leading-relaxed whitespace-pre-wrap break-words">{p.content}</p>
      })}
    </div>
  )
}

export function HistorySessions() {
  const [data, setData] = useState<HistoryData | null>(null)
  const [loading, setLoading] = useState(true)
  const [sel, setSel] = useState<HistorySession | null>(null)
  const [q, setQ] = useState("")
  const [pf, setPf] = useState("all")
  const [df, setDf] = useState("all")
  const [sf, setSf] = useState("all")
  const [showDev, setShowDev] = useState(false)
  const [expandedNodes, setExpandedNodes] = useState<Record<string, boolean>>({})
  const [showAnalysis, setShowAnalysis] = useState(false)
  const [uploadStatus, setUploadStatus] = useState<{ status: "idle" | "uploading" | "done" | "error"; message?: string }>({ status: "idle" })
  const scrollRef = useRef<HTMLDivElement>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)

  // ── Scan & Process ──
  interface ScanResult {
    ok: boolean
    source: {
      exists: boolean
      filePath: string
      fileSizeHuman: string
      totalLines: number
      validLines: number
      sessionCount: number
      earliest: string | null
      latest: string | null
    }
    existing: { totalSessions: number; totalMessages: number; generatedAt: string }
    hasExtracted: boolean
    hasGraph: boolean
    hasAnalysis: boolean
  }
  interface ProcessStep { name: string; status: "done" | "error" | "skipped"; message: string; durationMs?: number }
  interface ProcessResult {
    ok: boolean
    steps: ProcessStep[]
    totalTimeMs: number
    finalState?: { totalSessions: number; totalMessages: number; hasGraph: boolean; hasAnalysis: boolean }
  }
  const [scanResult, setScanResult] = useState<ScanResult | null>(null)
  const [scanLoading, setScanLoading] = useState(false)
  const [processResult, setProcessResult] = useState<ProcessResult | null>(null)
  const [processLoading, setProcessLoading] = useState(false)
  const [showScanPanel, setShowScanPanel] = useState(false)

  useEffect(() => { fetch("/api/claude-history").then(r => r.json()).then(d => { setData(d); setLoading(false) }).catch(() => setLoading(false)) }, [])
  useEffect(() => { if (sel && scrollRef.current) scrollRef.current.scrollTop = scrollRef.current.scrollHeight }, [sel])

  const tree = useMemo(() => {
    if (!data) return {}
    const t: Record<string, Record<string, Record<string, HistorySession[]>>> = {}
    for (const s of data.sessions) {
      const did = s.deviceId || "unknown"
      const src = s.source || "claude"
      const proj = s.project || "未知项目"
      t[did] ||= {}
      t[did][src] ||= {}
      t[did][src][proj] ||= []
      t[did][src][proj].push(s)
    }
    return t
  }, [data])

  const toggleNode = (key: string) => {
    setExpandedNodes(prev => ({ ...prev, [key]: !prev[key] }))
  }

  const doScan = async () => {
    setScanLoading(true)
    setProcessResult(null)
    try {
      const r = await fetch("/api/claude-history/scan")
      const d = await r.json()
      setScanResult(d)
    } catch (e: any) {
      setScanResult({ ok: false, source: { exists: false, filePath: "", fileSizeHuman: "0 B", totalLines: 0, validLines: 0, sessionCount: 0, earliest: null, latest: null }, existing: { totalSessions: 0, totalMessages: 0, generatedAt: "" }, hasExtracted: false, hasGraph: false, hasAnalysis: false })
    } finally {
      setScanLoading(false)
    }
  }

  const doProcess = async () => {
    setProcessLoading(true)
    setProcessResult(null)
    try {
      const r = await fetch("/api/claude-history/process", { method: "POST" })
      const d = await r.json()
      setProcessResult(d)
      // 刷新主数据
      fetch("/api/claude-history").then(r => r.json()).then(setData)
    } catch (e: any) {
      setProcessResult({ ok: false, steps: [{ name: "fetch", status: "error", message: e.message }], totalTimeMs: 0 })
    } finally {
      setProcessLoading(false)
    }
  }

  const handleFileUpload = async (file: File) => {
    setUploadStatus({ status: "uploading", message: "上传中..." })
    const hostname = prompt("请输入设备名称（如 MacBook-Pro）:", file.name.replace(/\.[^/.]+$/, "")) || "unknown"
    const form = new FormData()
    form.append("file", file)
    form.append("hostname", hostname)
    try {
      const r = await fetch("/api/claude-history/upload", { method: "POST", body: form })
      const d = await r.json()
      if (d.ok) {
        setUploadStatus({ status: "done", message: `已同步 ${d.hostname}: ${d.sessions} 会话` })
        // 刷新数据
        fetch("/api/claude-history").then(r => r.json()).then(setData)
      } else {
        setUploadStatus({ status: "error", message: d.error })
      }
    } catch (e: any) {
      setUploadStatus({ status: "error", message: e.message })
    }
  }

  if (loading) return <div className="h-full flex items-center justify-center"><div className="w-8 h-8 border-2 border-primary/30 border-t-primary rounded-full animate-spin" /></div>
  if (!data || !data.meta.totalSessions) return <div className="h-full flex items-center justify-center"><Bot className="w-10 h-10 text-muted-foreground/40" /><p className="text-sm text-muted-foreground mt-2">暂无记录</p></div>

  const projects = Object.keys(data.meta.projects)
  const devices = Object.values(data.meta.devices)
  const cats = data.meta.categoryDistribution || {}
  const styles = data.meta.styleDistribution || {}
  const toks = data.meta.totalTokens
  const sourceStats = data.meta.sources || {}

  const filtered = data.sessions.filter(s => {
    const mp = pf === "all" || s.project === pf
    const md = df === "all" || s.deviceId === df
    const ms = sf === "all" || s.source === sf
    const mq = !q || s.title.toLowerCase().includes(q.toLowerCase()) || s.messages.some(m => m.text.toLowerCase().includes(q.toLowerCase()))
    return mp && md && ms && mq
  })

  return (
    <div className="h-full flex flex-col">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 mb-4">
        <div className="min-w-0">
          <h2 className="text-lg font-semibold tracking-tight">历史会话</h2>
          <p className="text-sm text-muted-foreground mt-0.5 truncate">
            {data.meta.totalSessions} 会话 · {data.meta.totalMessages} 消息 · {data.meta.deviceCount} 设备
            {Object.entries(sourceStats).map(([src, cnt]) => (
              <span key={src} className={cn("ml-2 px-1.5 py-0.5 rounded text-[10px] font-medium", src === "codex" ? "bg-chart-3/15 text-chart-3" : "bg-chart-1/15 text-chart-1")}>{src === "codex" ? "Codex" : "Claude"} {cnt}</span>
            ))}
            {toks && <span className="ml-2">· {fmtNum(toks.total)} tokens · ${toks.estimatedCostUSD}</span>}
          </p>
        </div>
        <div className="flex items-center gap-2 shrink-0 overflow-x-auto scrollbar-hide pb-1 sm:pb-0">
          <button onClick={() => setShowScanPanel(!showScanPanel)} className={cn("px-2.5 py-1.5 rounded-lg text-xs font-medium transition-colors whitespace-nowrap shrink-0", showScanPanel ? "bg-primary/10 text-primary" : "bg-secondary/60 text-muted-foreground hover:text-foreground")}>
            <ScanLine className="w-3.5 h-3.5 inline mr-1" strokeWidth={1.5} />扫描
          </button>
          <button onClick={() => setShowAnalysis(!showAnalysis)} className={cn("px-2.5 py-1.5 rounded-lg text-xs font-medium transition-colors whitespace-nowrap shrink-0", showAnalysis ? "bg-primary/10 text-primary" : "bg-secondary/60 text-muted-foreground hover:text-foreground")}>
            <BarChart3 className="w-3.5 h-3.5 inline mr-1" strokeWidth={1.5} />分析
          </button>
          <button onClick={() => setShowDev(!showDev)} className={cn("px-2.5 py-1.5 rounded-lg text-xs font-medium transition-colors whitespace-nowrap shrink-0", showDev ? "bg-primary/10 text-primary" : "bg-secondary/60 text-muted-foreground hover:text-foreground")}>
            <Monitor className="w-3.5 h-3.5 inline mr-1" strokeWidth={1.5} />{data.meta.deviceCount} 设备
          </button>
        </div>
      </div>

      {/* Scan & Process Panel */}
      {showScanPanel && (
        <div className="mb-4 p-4 rounded-xl bg-secondary/30 border border-border/40">
          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 mb-3">
            <h3 className="text-sm font-semibold flex items-center gap-1.5">
              <HardDrive className="w-4 h-4 text-primary" strokeWidth={1.5} />
              服务器本地 Claude 历史数据
            </h3>
            <div className="flex items-center gap-2 shrink-0">
              <button
                onClick={doScan}
                disabled={scanLoading}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-primary/10 text-primary text-xs font-medium hover:bg-primary/15 transition-colors disabled:opacity-50"
              >
                {scanLoading ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <ScanLine className="w-3.5 h-3.5" />}
                扫描本地记录
              </button>
              {scanResult?.source?.exists && (
                <button
                  onClick={doProcess}
                  disabled={processLoading}
                  className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-chart-1/10 text-chart-1 text-xs font-medium hover:bg-chart-1/15 transition-colors disabled:opacity-50"
                >
                  {processLoading ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Play className="w-3.5 h-3.5" />}
                  提取 → 建图 → 分析
                </button>
              )}
            </div>
          </div>

          {/* Scan Result */}
          {scanResult && (
            <div className="space-y-3">
              {!scanResult.source?.exists ? (
                <div className="flex items-center gap-2 text-xs text-chart-2">
                  <XCircle className="w-4 h-4" />
                  未找到本地历史文件：{scanResult.source?.filePath}
                </div>
              ) : (
                <>
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
                    <div className="p-2.5 rounded-lg bg-card/50">
                      <p className="text-[10px] text-muted-foreground">文件大小</p>
                      <p className="text-sm font-semibold">{scanResult.source.fileSizeHuman}</p>
                    </div>
                    <div className="p-2.5 rounded-lg bg-card/50">
                      <p className="text-[10px] text-muted-foreground">总行数</p>
                      <p className="text-sm font-semibold">{fmtNum(scanResult.source.totalLines)}</p>
                    </div>
                    <div className="p-2.5 rounded-lg bg-card/50">
                      <p className="text-[10px] text-muted-foreground">有效记录</p>
                      <p className="text-sm font-semibold">{fmtNum(scanResult.source.validLines)}</p>
                    </div>
                    <div className="p-2.5 rounded-lg bg-card/50">
                      <p className="text-[10px] text-muted-foreground">会话数</p>
                      <p className="text-sm font-semibold">{fmtNum(scanResult.source.sessionCount)}</p>
                    </div>
                  </div>

                  {(scanResult.source.earliest || scanResult.source.latest) && (
                    <div className="flex items-center gap-3 text-[11px] text-muted-foreground">
                      {scanResult.source.earliest && <span>最早: {fmtDate(scanResult.source.earliest)}</span>}
                      {scanResult.source.latest && <span>最新: {fmtDate(scanResult.source.latest)}</span>}
                    </div>
                  )}

                  {/* Existing Data Status */}
                  <div className="flex items-center gap-3 pt-2 border-t border-border/30">
                    <span className={cn("flex items-center gap-1 text-[11px]", scanResult.hasExtracted ? "text-chart-1" : "text-muted-foreground/50")}>
                      <FileText className="w-3 h-3" /> 已提取
                    </span>
                    <span className={cn("flex items-center gap-1 text-[11px]", scanResult.hasAnalysis ? "text-chart-1" : "text-muted-foreground/50")}>
                      <BarChart3 className="w-3 h-3" /> 已分析
                    </span>
                    {scanResult.existing?.totalSessions > 0 && (
                      <span className="text-[11px] text-muted-foreground ml-auto">
                        当前数据: {scanResult.existing.totalSessions} 会话 · {scanResult.existing.totalMessages} 消息
                      </span>
                    )}
                  </div>
                </>
              )}

              {/* Process Result */}
              {processResult && (
                <div className="mt-3 p-3 rounded-lg bg-card/50 border border-border/30">
                  <p className="text-xs font-medium mb-2">
                    处理结果
                    {processResult.totalTimeMs > 0 && (
                      <span className="text-muted-foreground font-normal"> · 耗时 {(processResult.totalTimeMs / 1000).toFixed(1)}s</span>
                    )}
                  </p>
                  <div className="space-y-1.5">
                    {processResult.steps?.map((step, i) => (
                      <div key={i} className="flex items-center gap-2 text-xs">
                        {step.status === "done" && <CheckCircle2 className="w-3.5 h-3.5 text-chart-1 shrink-0" />}
                        {step.status === "error" && <XCircle className="w-3.5 h-3.5 text-chart-2 shrink-0" />}
                        {step.status === "skipped" && <AlertCircle className="w-3.5 h-3.5 text-muted-foreground shrink-0" />}
                        <span className={cn(
                          step.status === "done" && "text-chart-1",
                          step.status === "error" && "text-chart-2",
                          step.status === "skipped" && "text-muted-foreground"
                        )}>
                          {step.name === "extract" && "提取"}
                          {step.name === "merge" && "合并"}
                          {step.name === "analyze" && "分析"}
                          {step.name === "fetch" && "请求"}
                        </span>
                        <span className="text-muted-foreground">{step.message}</span>
                        {step.durationMs && <span className="text-[10px] text-muted-foreground/60">{step.durationMs}ms</span>}
                      </div>
                    ))}
                  </div>
                  {processResult.finalState && (
                    <div className="mt-2 pt-2 border-t border-border/30 flex items-center gap-3 text-[11px]">
                      <span>最终: {processResult.finalState.totalSessions} 会话 · {processResult.finalState.totalMessages} 消息</span>
                      {processResult.finalState.hasAnalysis && <span className="text-chart-1">✓ 分析</span>}
                    </div>
                  )}
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {/* Analysis Panel */}
      {showAnalysis && (
        <div className="mb-4 p-4 rounded-xl bg-secondary/30 border border-border/40">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-4">
            <div className="p-3 rounded-lg bg-card/50">
              <p className="text-[11px] text-muted-foreground">总 Token</p>
              <p className="text-lg font-semibold">{toks ? fmtNum(toks.total) : "-"}</p>
            </div>
            <div className="p-3 rounded-lg bg-card/50">
              <p className="text-[11px] text-muted-foreground">输入 / 输出</p>
              <p className="text-lg font-semibold">{toks ? `${fmtNum(toks.input)} / ${fmtNum(toks.output)}` : "-"}</p>
            </div>
            <div className="p-3 rounded-lg bg-card/50">
              <p className="text-[11px] text-muted-foreground">估算成本</p>
              <p className="text-lg font-semibold">${toks?.estimatedCostUSD ?? "-"}</p>
            </div>
            <div className="p-3 rounded-lg bg-card/50">
              <p className="text-[11px] text-muted-foreground">平均会话长度</p>
              <p className="text-lg font-semibold">{Math.round(data.meta.totalMessages / data.meta.totalSessions)} 条</p>
            </div>
          </div>
          {Object.keys(cats).length > 0 && (
            <div className="mb-3">
              <p className="text-[11px] text-muted-foreground mb-2">会话类型分布</p>
              <div className="flex flex-wrap gap-1.5">
                {Object.entries(cats).sort((a, b) => b[1] - a[1]).map(([c, n]) => (
                  <span key={c} className={cn("px-2 py-0.5 rounded text-[11px] font-medium", CAT_COLORS[c] || "bg-muted/30 text-muted-foreground")}>{c} {n}</span>
                ))}
              </div>
            </div>
          )}
          {Object.keys(styles).length > 0 && (
            <div>
              <p className="text-[11px] text-muted-foreground mb-2">提问风格分布</p>
              <div className="flex flex-wrap gap-1.5">
                {Object.entries(styles).sort((a, b) => b[1] - a[1]).map(([s, n]) => (
                  <span key={s} className="px-2 py-0.5 rounded text-[11px] font-medium bg-secondary/70 text-muted-foreground">{STYLE_ICONS[s] || "•"} {s} {n}</span>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* Devices Panel + Upload */}
      {showDev && (
        <div className="mb-4 p-4 rounded-xl bg-secondary/30 border border-border/40">
          {/* Upload Area */}
          <div className="mb-3 flex items-center gap-3">
            <input
              ref={fileInputRef}
              type="file"
              accept=".zip,.json,.jsonl"
              className="hidden"
              onChange={e => {
                const f = e.target.files?.[0]
                if (f) handleFileUpload(f)
                e.target.value = ""
              }}
            />
            <button
              onClick={() => fileInputRef.current?.click()}
              disabled={uploadStatus.status === "uploading"}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-primary/10 text-primary text-xs font-medium hover:bg-primary/15 transition-colors disabled:opacity-50"
            >
              <Upload className="w-3.5 h-3.5" strokeWidth={1.5} />
              上传本地记录
            </button>
            {uploadStatus.status === "uploading" && <span className="text-xs text-muted-foreground">{uploadStatus.message}</span>}
            {uploadStatus.status === "done" && <span className="text-xs text-chart-1 flex items-center gap-1"><CheckCircle2 className="w-3 h-3" />{uploadStatus.message}</span>}
            {uploadStatus.status === "error" && <span className="text-xs text-chart-2 flex items-center gap-1"><XCircle className="w-3 h-3" />{uploadStatus.message}</span>}
            <span className="text-[10px] text-muted-foreground ml-auto">支持 .zip / .json / .jsonl</span>
          </div>

          {/* Device / Source / Project Tree */}
          <div className="space-y-2">
            {Object.entries(tree).map(([deviceId, sources]) => {
              const dev = devices.find(d => d.machineId === deviceId)
              const devLabel = dev?.hostname || deviceId
              const devKey = `dev:${deviceId}`
              const devExpanded = expandedNodes[devKey] ?? true
              const devSessions = Object.values(sources).flatMap(p => Object.values(p).flat()).length
              return (
                <div key={deviceId} className="rounded-lg border border-border/40 bg-card/50 overflow-hidden">
                  <button
                    onClick={() => toggleNode(devKey)}
                    className="w-full flex items-center gap-2 px-3 py-2 text-sm font-medium"
                  >
                    {devExpanded ? <ChevronDown className="w-3.5 h-3.5 text-muted-foreground" strokeWidth={1.5} /> : <ChevronRight className="w-3.5 h-3.5 text-muted-foreground" strokeWidth={1.5} />}
                    <Monitor className="w-4 h-4 text-chart-1" strokeWidth={1.5} />
                    <span>{devLabel}</span>
                    <span className="ml-auto text-[10px] text-muted-foreground">{devSessions} 会话</span>
                  </button>
                  {devExpanded && (
                    <div className="px-3 pb-2 space-y-1">
                      {Object.entries(sources).map(([source, projects]) => {
                        const srcKey = `src:${deviceId}:${source}`
                        const srcExpanded = expandedNodes[srcKey] ?? true
                        const srcIcon = source === "codex"
                          ? <Code2 className="w-3.5 h-3.5 text-chart-3" strokeWidth={1.5} />
                          : <Bot className="w-3.5 h-3.5 text-chart-1" strokeWidth={1.5} />
                        const srcCount = Object.values(projects).flat().length
                        return (
                          <div key={source} className="ml-4">
                            <button
                              onClick={() => toggleNode(srcKey)}
                              className="w-full flex items-center gap-2 py-1 text-xs font-medium"
                            >
                              {srcExpanded ? <ChevronDown className="w-3 h-3 text-muted-foreground" strokeWidth={1.5} /> : <ChevronRight className="w-3 h-3 text-muted-foreground" strokeWidth={1.5} />}
                              {srcIcon}
                              <span className="capitalize">{source}</span>
                              <span className="ml-auto text-[10px] text-muted-foreground">{srcCount} 会话</span>
                            </button>
                            {srcExpanded && (
                              <div className="ml-5 space-y-0.5">
                                {Object.entries(projects).sort((a, b) => a[0].localeCompare(b[0])).map(([project, sessions]) => (
                                  <button
                                    key={project}
                                    onClick={() => { setDf(deviceId); setSf(source); setPf(project); }}
                                    className={cn(
                                      "w-full flex items-center gap-2 px-2 py-1 rounded text-xs text-left hover:bg-secondary/60",
                                      pf === project && df === deviceId && sf === source ? "bg-primary/10 text-primary" : "text-muted-foreground"
                                    )}
                                  >
                                    <Folder className="w-3 h-3 shrink-0" strokeWidth={1.5} />
                                    <span className="flex-1 truncate">{project.replace("/home/aw/", "~/")}</span>
                                    <span className="text-[10px] shrink-0">{sessions.length}</span>
                                  </button>
                                ))}
                              </div>
                            )}
                          </div>
                        )
                      })}
                    </div>
                  )}
                </div>
              )
            })}
          </div>
        </div>
      )}

      {/* Filters */}
      <div className="flex flex-wrap items-center gap-2 mb-3">
        <div className="relative flex-1 min-w-[120px] max-w-sm"><Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-muted-foreground/50" strokeWidth={1.5} /><input type="text" placeholder="搜索..." value={q} onChange={e => setQ(e.target.value)} className="w-full pl-8 pr-2 py-1.5 rounded-lg bg-secondary/60 text-sm placeholder:text-muted-foreground/40 focus:outline-none focus:ring-1 focus:ring-primary/30" /></div>
        <select value={pf} onChange={e => setPf(e.target.value)} className="px-2 py-1.5 rounded-lg bg-secondary/60 text-sm text-xs focus:outline-none">{["all", ...projects].map(p => <option key={p} value={p}>{getProj(p)}</option>)}</select>
        <select value={df} onChange={e => setDf(e.target.value)} className="px-2 py-1.5 rounded-lg bg-secondary/60 text-sm text-xs focus:outline-none">{["all", ...devices.map(d => d.machineId)].map(v => <option key={v} value={v}>{v === "all" ? "全部设备" : devices.find(d => d.machineId === v)?.hostname}</option>)}</select>
        <select value={sf} onChange={e => setSf(e.target.value)} className="px-2 py-1.5 rounded-lg bg-secondary/60 text-sm text-xs focus:outline-none">
          <option value="all">全部来源</option>
          <option value="claude">Claude</option>
          <option value="codex">Codex</option>
        </select>
      </div>

      {/* Content */}
      <div className="flex-1 flex flex-col md:flex-row gap-3 min-h-0">
        {/* List */}
        <div className={cn("flex-1 flex flex-col min-w-0", sel && "hidden md:flex")}>
          <div className="flex-1 overflow-auto">
            {filtered?.map((s, i) => (
              <button key={`${s.deviceId}-${s.sessionId}`} onClick={() => setSel(s)} className={cn("relative w-full px-3 py-3 text-left transition-colors group rounded-lg hover:bg-secondary/50", i !== 0 && "border-t border-border/60")}>
                {sel?.sessionId === s.sessionId && sel?.deviceId === s.deviceId && <span className="absolute left-0 top-3 bottom-3 w-0.5 rounded-full bg-chart-1" />}
                <div className="flex items-start justify-between gap-2">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-1.5 mb-1 flex-wrap">
                      {s.categories?.map(c => <span key={c} className={cn("px-1.5 py-0.5 rounded text-[10px] font-medium", CAT_COLORS[c] || "bg-muted/30")}>{c}</span>)}
                      {s.source === "codex" && <span className="inline-flex items-center gap-0.5 text-[10px] px-1 py-0.5 rounded bg-chart-3/15 text-chart-3"><Code2 className="w-2.5 h-2.5" strokeWidth={1.5} />Codex</span>}
                      {s.source === "claude" && <span className="inline-flex items-center gap-0.5 text-[10px] px-1 py-0.5 rounded bg-chart-1/15 text-chart-1"><Bot className="w-2.5 h-2.5" strokeWidth={1.5} />Claude</span>}
                      <span className="text-[10px] text-muted-foreground font-mono flex items-center gap-0.5"><Calendar className="w-2.5 h-2.5" strokeWidth={1.5} />{fmtDate(s.startTime)}</span>
                      {s.deviceName && s.deviceName !== "awberry" && <span className="inline-flex items-center gap-0.5 text-[10px] px-1 py-0.5 rounded bg-chart-3/10 text-chart-3"><Monitor className="w-2.5 h-2.5" strokeWidth={1.5} />{s.deviceName}</span>}
                    </div>
                    <h3 className="text-sm font-medium mb-0.5 line-clamp-1">{s.title}</h3>
                    <div className="flex items-center gap-2 text-[10px] text-muted-foreground">
                      <span className="flex items-center gap-0.5"><MessageSquare className="w-2.5 h-2.5" strokeWidth={1.5} />{s.messageCount} 条</span>
                      <span className="flex items-center gap-0.5"><Clock className="w-2.5 h-2.5" strokeWidth={1.5} />{fmtDuration(s.startTime, s.endTime)}</span>
                      {s.usage && s.usage.totalTokens > 0 && <span className="flex items-center gap-0.5">{fmtNum(s.usage.totalTokens)} t</span>}
                      {s.behavior?.dominantStyle && <span>{STYLE_ICONS[s.behavior.dominantStyle]} {s.behavior.dominantStyle}</span>}
                    </div>
                  </div>
                  <ChevronRight className="w-4 h-4 text-muted-foreground/40 sm:opacity-0 sm:group-hover:opacity-100 transition-opacity shrink-0 mt-1" strokeWidth={1.5} />
                </div>
              </button>
            ))}
            {!filtered?.length && <div className="flex items-center justify-center py-12"><p className="text-sm text-muted-foreground">无匹配</p></div>}
          </div>
        </div>

        {/* Detail */}
        {sel && (
          <div className="flex-1 flex flex-col bg-secondary/30 rounded-xl overflow-hidden min-w-0">
            {/* Detail Header */}
            <div className="flex items-center justify-between px-4 py-2.5 border-b border-border/60 shrink-0">
              <button onClick={() => setSel(null)} className="md:hidden flex items-center gap-1 text-sm text-muted-foreground"><ChevronRight className="w-4 h-4 rotate-180" strokeWidth={1.5} />返回</button>
              <div className="hidden md:flex items-center gap-2">
                {sel.categories?.map(c => <span key={c} className={cn("px-1.5 py-0.5 rounded text-[10px] font-medium", CAT_COLORS[c] || "bg-muted/30")}>{c}</span>)}
                <span className="text-[11px] text-muted-foreground font-mono">{fmtDate(sel.startTime)}</span>
              </div>
              <span className="text-[11px] text-muted-foreground">{sel.messageCount} 条 · {fmtDuration(sel.startTime, sel.endTime)}</span>
            </div>

            {/* Session Analysis Summary */}
            {(sel.usage?.totalTokens || sel.behavior || sel.keyContent?.decisions?.length) && (
              <div className="px-4 py-2.5 border-b border-border/40 bg-secondary/20">
                <div className="flex flex-wrap gap-x-4 gap-y-1 text-[11px]">
                  {sel.usage && sel.usage.totalTokens > 0 && (
                    <span className="flex items-center gap-1 text-muted-foreground"><BarChart3 className="w-3 h-3" strokeWidth={1.5} />{fmtNum(sel.usage.inputTokens)}→{fmtNum(sel.usage.outputTokens)} · ${sel.usage.estimatedCost}</span>
                  )}
                  {sel.behavior?.dominantStyle && (
                    <span className="flex items-center gap-1 text-muted-foreground"><Tag className="w-3 h-3" strokeWidth={1.5} />{STYLE_ICONS[sel.behavior.dominantStyle]} {sel.behavior.dominantStyle} · 追问率{sel.behavior.followUpRatio}%</span>
                  )}
                  {sel.keyContent?.correctionsCount ? (
                    <span className="flex items-center gap-1 text-chart-2"><AlertCircle className="w-3 h-3" strokeWidth={1.5} />{sel.keyContent.correctionsCount} 次观点调整</span>
                  ) : null}
                  {sel.keyContent?.decisions?.length ? (
                    <span className="flex items-center gap-1 text-chart-1"><GitBranch className="w-3 h-3" strokeWidth={1.5} />{sel.keyContent.decisions.length} 个决策</span>
                  ) : null}
                  {sel.keyContent?.codeReferences?.length ? (
                    <span className="flex items-center gap-1 text-chart-3"><Code2 className="w-3 h-3" strokeWidth={1.5} />{sel.keyContent.codeReferences.length} 处代码引用</span>
                  ) : null}
                </div>

                {/* Key GitBranchs */}
                {sel.keyContent?.decisions && sel.keyContent.decisions.length > 0 && (
                  <div className="mt-2 pt-2 border-t border-border/30">
                    <p className="text-[10px] text-muted-foreground mb-1 flex items-center gap-1"><Lightbulb className="w-2.5 h-2.5" strokeWidth={1.5} />关键决策</p>
                    <div className="flex flex-wrap gap-1">
                      {sel.keyContent.decisions.map((d, i) => (
                        <span key={i} className="px-1.5 py-0.5 rounded bg-chart-1/10 text-chart-1 text-[10px]">{d}</span>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            )}

            {/* Messages */}
            <div ref={scrollRef} className="flex-1 overflow-auto p-3 space-y-3">
              {sel.messages.map((msg, idx) => (
                <div key={idx} className="flex gap-2.5">
                  <div className={cn("shrink-0 w-6 h-6 rounded-full flex items-center justify-center mt-0.5", msg.role === "user" ? "bg-primary/10" : "bg-chart-1/10")}>
                    {msg.role === "user" ? <User className="w-3 h-3 text-primary" strokeWidth={1.5} /> : <Bot className="w-3 h-3 text-chart-1" strokeWidth={1.5} />}
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-1.5 mb-0.5">
                      <span className={cn("text-[10px] font-medium", msg.role === "user" ? "text-primary/70" : "text-chart-1/70")}>{msg.role === "user" ? "你" : sel.source === "codex" ? "Codex" : "Claude"}</span>
                      <span className="text-[9px] text-muted-foreground/40 font-mono">{msg.timestamp ? fmtTime(msg.timestamp) : ""}</span>
                      {msg.hostname && msg.hostname !== "awberry" && <span className="text-[9px] text-muted-foreground/40">· {msg.hostname}</span>}
                    </div>
                    <MsgContent text={msg.text} />
                  </div>
                </div>
              ))}
              {sel.media && sel.media.length > 0 && (
                <div className="pt-3 border-t border-border/40">
                  <p className="text-[10px] text-muted-foreground mb-2 flex items-center gap-1"><ImageIcon className="w-3 h-3" strokeWidth={1.5} />生成图片 ({sel.media.length})</p>
                  <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
                    {sel.media.map((m, i) => (
                      <a key={i} href={m.url} target="_blank" rel="noreferrer" className="relative aspect-video rounded-lg overflow-hidden bg-secondary/50 border border-border/40 hover:border-primary/30 transition-colors">
                        <img src={m.url} alt={m.filename} className="w-full h-full object-cover" loading="lazy" />
                      </a>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </div>
        )}

        {!sel && <div className="hidden md:flex flex-1 items-center justify-center bg-secondary/30 rounded-xl"><MessageSquare className="w-8 h-8 text-muted-foreground/40 mb-2" /><p className="text-sm text-muted-foreground">选择会话查看详情</p></div>}
      </div>
    </div>
  )
}
