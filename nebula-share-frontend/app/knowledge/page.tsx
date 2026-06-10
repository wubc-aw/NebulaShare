"use client"

import { useState, useEffect, useRef, useCallback } from "react"
import { KnowledgeGraph, GraphData } from "@/components/knowledge-graph"
import { Upload, FileJson, X, CheckCircle2, AlertCircle } from "lucide-react"
import { cn } from "@/lib/utils"

// ─── Mock Data ──────────────────────────────────────────────────────
const mockData: GraphData = {
  nodes: [
    { id: "NebulaShare", type: "Project", group: 1, radius: 24 },
    { id: "React", type: "Technology", group: 2 },
    { id: "Next.js", type: "Technology", group: 2 },
    { id: "TypeScript", type: "Technology", group: 2 },
    { id: "D3.js", type: "Technology", group: 2 },
    { id: "Tailwind CSS", type: "Technology", group: 2 },
    { id: "PostgreSQL", type: "Technology", group: 2 },
    { id: "Docker", type: "Technology", group: 2 },
    { id: "REST API", type: "Technology", group: 2 },
    { id: "WebSocket", type: "Technology", group: 2 },
    { id: "Use Next.js App Router", type: "Decision", group: 3 },
    { id: "Use PostgreSQL over MongoDB", type: "Decision", group: 3 },
    { id: "Use D3 for visualization", type: "Decision", group: 3 },
    { id: "Self-host vs Cloud", type: "Decision", group: 3 },
    { id: "Scaling file uploads", type: "Problem", group: 4 },
    { id: "Real-time sync latency", type: "Problem", group: 4 },
    { id: "Auth session management", type: "Problem", group: 4 },
    { id: "Cross-browser compatibility", type: "Problem", group: 4 },
    { id: "Knowledge Graph", type: "Concept", group: 5, radius: 18 },
    { id: "File Hub", type: "Concept", group: 5 },
    { id: "Network Hub", type: "Concept", group: 5 },
    { id: "Intelligence Center", type: "Concept", group: 5 },
    { id: "Zone Navigation", type: "Concept", group: 5 },
    { id: "Microservices", type: "Concept", group: 5 },
    { id: "Event Sourcing", type: "Concept", group: 5 },
    { id: "Session 2024-01-15", type: "Session", group: 6 },
    { id: "Session 2024-02-20", type: "Session", group: 6 },
    { id: "Session 2024-03-10", type: "Session", group: 6 },
    { id: "Session 2024-04-05", type: "Session", group: 6 },
    { id: "Session 2024-05-12", type: "Session", group: 6 },
    { id: "Vercel", type: "Technology", group: 2 },
    { id: "Redis", type: "Technology", group: 2 },
    { id: "CI/CD Pipeline", type: "Concept", group: 5 },
  ],
  edges: [
    { source: "NebulaShare", target: "React", type: "uses" },
    { source: "NebulaShare", target: "Next.js", type: "uses" },
    { source: "NebulaShare", target: "TypeScript", type: "uses" },
    { source: "NebulaShare", target: "Tailwind CSS", type: "uses" },
    { source: "NebulaShare", target: "PostgreSQL", type: "uses" },
    { source: "NebulaShare", target: "Docker", type: "uses" },
    { source: "NebulaShare", target: "Knowledge Graph", type: "contains" },
    { source: "NebulaShare", target: "File Hub", type: "contains" },
    { source: "NebulaShare", target: "Network Hub", type: "contains" },
    { source: "NebulaShare", target: "Intelligence Center", type: "contains" },
    { source: "NebulaShare", target: "Zone Navigation", type: "contains" },
    { source: "Next.js", target: "React", type: "depends-on" },
    { source: "Next.js", target: "TypeScript", type: "supports" },
    { source: "Use Next.js App Router", target: "Next.js", type: "applies-to" },
    { source: "Use Next.js App Router", target: "NebulaShare", type: "applies-to" },
    { source: "Use PostgreSQL over MongoDB", target: "PostgreSQL", type: "applies-to" },
    { source: "Use PostgreSQL over MongoDB", target: "NebulaShare", type: "applies-to" },
    { source: "Use D3 for visualization", target: "D3.js", type: "applies-to" },
    { source: "Use D3 for visualization", target: "Knowledge Graph", type: "applies-to" },
    { source: "Self-host vs Cloud", target: "Docker", type: "applies-to" },
    { source: "Self-host vs Cloud", target: "Vercel", type: "applies-to" },
    { source: "Scaling file uploads", target: "File Hub", type: "affects" },
    { source: "Scaling file uploads", target: "Docker", type: "affects" },
    { source: "Real-time sync latency", target: "WebSocket", type: "affects" },
    { source: "Real-time sync latency", target: "Redis", type: "affects" },
    { source: "Auth session management", target: "Session 2024-01-15", type: "discussed-in" },
    { source: "Auth session management", target: "Next.js", type: "affects" },
    { source: "Cross-browser compatibility", target: "React", type: "affects" },
    { source: "Cross-browser compatibility", target: "Tailwind CSS", type: "affects" },
    { source: "Knowledge Graph", target: "D3.js", type: "uses" },
    { source: "Knowledge Graph", target: "Microservices", type: "related-to" },
    { source: "File Hub", target: "REST API", type: "uses" },
    { source: "Network Hub", target: "WebSocket", type: "uses" },
    { source: "Intelligence Center", target: "Redis", type: "uses" },
    { source: "Intelligence Center", target: "Event Sourcing", type: "implements" },
    { source: "Session 2024-01-15", target: "NebulaShare", type: "involves" },
    { source: "Session 2024-02-20", target: "NebulaShare", type: "involves" },
    { source: "Session 2024-03-10", target: "Knowledge Graph", type: "involves" },
    { source: "Session 2024-04-05", target: "File Hub", type: "involves" },
    { source: "Session 2024-05-12", target: "Intelligence Center", type: "involves" },
    { source: "Session 2024-01-15", target: "Auth session management", type: "discusses" },
    { source: "Session 2024-02-20", target: "Scaling file uploads", type: "discusses" },
    { source: "Session 2024-03-10", target: "Use D3 for visualization", type: "discusses" },
    { source: "Session 2024-04-05", target: "REST API", type: "discusses" },
    { source: "Session 2024-05-12", target: "Microservices", type: "discusses" },
    { source: "CI/CD Pipeline", target: "Docker", type: "uses" },
    { source: "CI/CD Pipeline", target: "Vercel", type: "uses" },
    { source: "CI/CD Pipeline", target: "NebulaShare", type: "applies-to" },
    { source: "Redis", target: "WebSocket", type: "supports" },
    { source: "Event Sourcing", target: "PostgreSQL", type: "uses" },
    { source: "Microservices", target: "Docker", type: "uses" },
    { source: "Microservices", target: "Event Sourcing", type: "related-to" },
  ],
}

// ─── Inline Upload Component ────────────────────────────────────────
type UploadState =
  | { status: "idle" }
  | { status: "parsing"; fileName: string }
  | { status: "done"; fileName: string; nodeCount: number; edgeCount: number }
  | { status: "error"; fileName: string; message: string }

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

export default function KnowledgePage() {
  const [data, setData] = useState<GraphData | null>(null)
  const [loading, setLoading] = useState(true)
  const [uploadState, setUploadState] = useState<UploadState>({ status: "idle" })
  const [dragOver, setDragOver] = useState(false)
  const fileInputRef = useRef<HTMLInputElement>(null)

  // Try load from API first, fallback to mock
  useEffect(() => {
    fetch("/api/knowledge/graph")
      .then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`)
        return r.json()
      })
      .then((d: GraphData) => {
        if (isValidGraphData(d) && d.nodes.length > 0) {
          setData(d)
        } else {
          setData(mockData)
        }
        setLoading(false)
      })
      .catch(() => {
        setData(mockData)
        setLoading(false)
      })
  }, [])

  const parseFile = useCallback((file: File) => {
    setUploadState({ status: "parsing", fileName: file.name })
    const reader = new FileReader()
    reader.onload = () => {
      try {
        const text = reader.result as string
        const json = JSON.parse(text)
        if (!isValidGraphData(json)) {
          setUploadState({
            status: "error",
            fileName: file.name,
            message: "JSON 格式不符：需要包含 nodes[] 和 edges[] 数组",
          })
          return
        }
        setData(json)
        setUploadState({
          status: "done",
          fileName: file.name,
          nodeCount: json.nodes.length,
          edgeCount: json.edges.length,
        })
      } catch (e) {
        setUploadState({
          status: "error",
          fileName: file.name,
          message: e instanceof Error ? e.message : "解析失败",
        })
      }
    }
    reader.onerror = () => {
      setUploadState({
        status: "error",
        fileName: file.name,
        message: "读取文件失败",
      })
    }
    reader.readAsText(file)
  }, [])

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault()
      setDragOver(false)
      const file = e.dataTransfer.files[0]
      if (file && file.name.endsWith(".json")) {
        parseFile(file)
      } else {
        setUploadState({
          status: "error",
          fileName: file?.name || "未知",
          message: "仅支持 .json 文件",
        })
      }
    },
    [parseFile]
  )

  const handleFileSelect = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const file = e.target.files?.[0]
      if (file) parseFile(file)
      e.target.value = ""
    },
    [parseFile]
  )

  const clearUpload = useCallback(() => {
    setUploadState({ status: "idle" })
    setData(mockData)
  }, [])

  if (loading) {
    return (
      <div className="p-6 sm:p-8 max-w-6xl mx-auto h-full flex items-center justify-center">
        <div className="w-8 h-8 border-2 border-primary/30 border-t-primary rounded-full animate-spin" />
      </div>
    )
  }

  if (!data || !data.nodes.length) {
    return (
      <div className="p-6 sm:p-8 max-w-6xl mx-auto h-full flex items-center justify-center">
        <p className="text-sm text-muted-foreground">暂无知识图谱数据</p>
      </div>
    )
  }

  return (
    <div className="p-6 sm:p-8 max-w-6xl mx-auto h-full flex flex-col">
      {/* Page Header */}
      <div className="mb-6">
        <h1 className="text-2xl font-bold tracking-tight">☁️ Cloud历史知识图谱</h1>
        <p className="text-sm text-muted-foreground mt-1">
          Claude Code 会话历史 · 概念关联 · 决策追踪 · 会话溯源
        </p>
      </div>

      <div className="flex-1 bg-card rounded-2xl p-5 sm:p-6 shadow-[var(--shadow-card)] border border-border/40 flex flex-col min-h-[500px]">
        {/* Header with upload */}
        <div className="flex items-center justify-between mb-3 shrink-0">
          <div>
            <h2 className="text-lg font-semibold tracking-tight">知识图谱</h2>
            <p className="text-xs text-muted-foreground mt-0.5">
              {data.nodes.length} 节点 · {data.edges.length} 关系
              {uploadState.status === "done" && (
                <span className="ml-2 text-chart-1">· 来自 {uploadState.fileName}</span>
              )}
            </p>
          </div>

          <div className="flex items-center gap-2">
            {/* Upload status indicators */}
            {uploadState.status === "parsing" && (
              <span className="text-xs text-muted-foreground flex items-center gap-1">
                <div className="w-3 h-3 border border-primary/30 border-t-primary rounded-full animate-spin" />
                解析 {uploadState.fileName}...
              </span>
            )}
            {uploadState.status === "done" && (
              <span className="text-xs text-chart-1 flex items-center gap-1">
                <CheckCircle2 className="w-3.5 h-3.5" />
                已加载
              </span>
            )}
            {uploadState.status === "error" && (
              <span className="text-xs text-chart-2 flex items-center gap-1">
                <AlertCircle className="w-3.5 h-3.5" />
                {uploadState.message}
              </span>
            )}

            {/* Upload button */}
            <input
              ref={fileInputRef}
              type="file"
              accept=".json"
              className="hidden"
              onChange={handleFileSelect}
            />
            <button
              onClick={() => fileInputRef.current?.click()}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-primary/10 text-primary text-xs font-medium hover:bg-primary/15 transition-colors"
            >
              <Upload className="w-3.5 h-3.5" strokeWidth={1.5} />
              加载 graph.json
            </button>
            {uploadState.status === "done" && (
              <button
                onClick={clearUpload}
                className="flex items-center gap-1 px-2 py-1.5 rounded-lg bg-secondary/60 text-muted-foreground text-xs hover:text-foreground transition-colors"
              >
                <X className="w-3 h-3" strokeWidth={1.5} />
                重置
              </button>
            )}
          </div>
        </div>

        {/* Drop zone */}
        <div
          className={cn(
            "flex-1 rounded-xl border border-border/40 overflow-hidden transition-colors min-h-0",
            dragOver && "border-primary/50 bg-primary/5"
          )}
          onDragOver={(e) => {
            e.preventDefault()
            setDragOver(true)
          }}
          onDragLeave={() => setDragOver(false)}
          onDrop={handleDrop}
        >
          <KnowledgeGraph data={data} />
        </div>

        {/* Hint */}
        <p className="text-[10px] text-muted-foreground/60 mt-2 text-center shrink-0">
          <FileJson className="w-3 h-3 inline mr-1" strokeWidth={1.5} />
          拖拽 graph.json 到上方区域，或点击按钮选择文件
        </p>
      </div>
    </div>
  )
}
