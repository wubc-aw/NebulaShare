"use client"

import { useState, useEffect } from "react"
import { X, Link2, Loader2, Globe, CheckCircle2, AlertCircle } from "lucide-react"
import { cn } from "@/lib/utils"

export interface SourceFormData {
  id?: number
  name: string
  url: string
  category: string
}

interface SourceFormProps {
  source?: SourceFormData | null
  onClose: () => void
  onSaved: () => void
}

const categories = ["AI", "互联网", "金融", "创投", "工具", "阅读"]

const API_BASE = "/api/intel"

interface ScrapeTestResult {
  title?: string
  summary?: string
  content?: string
  url?: string
  error?: string
}

export function SourceForm({ source, onClose, onSaved }: SourceFormProps) {
  const isEdit = !!source?.id

  const [name, setName] = useState("")
  const [url, setUrl] = useState("")
  const [category, setCategory] = useState("阅读")
  const [testing, setTesting] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [testResult, setTestResult] = useState<{
    success: boolean
    message: string
  } | null>(null)

  // Initialize form when source changes
  useEffect(() => {
    if (source) {
      setName(source.name || "")
      setUrl(source.url || "")
      setCategory(source.category || "阅读")
    } else {
      setName("")
      setUrl("")
      setCategory("阅读")
    }
    setError(null)
    setTestResult(null)
  }, [source])

  const handleTestUrl = async () => {
    const targetUrl = url.trim()
    if (!targetUrl) {
      setError("请输入 RSS URL")
      setTestResult(null)
      return
    }
    setTesting(true)
    setError(null)
    setTestResult(null)
    try {
      const res = await fetch(`${API_BASE}/scrape`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url: targetUrl }),
      })
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      const data: ScrapeTestResult = await res.json()
      if (data.error) {
        setTestResult({ success: false, message: data.error })
      } else {
        setTestResult({
          success: true,
          message: data.title ? `可访问: ${data.title}` : "URL 可访问",
        })
      }
    } catch (err) {
      setTestResult({
        success: false,
        message: err instanceof Error ? err.message : "测试失败",
      })
    } finally {
      setTesting(false)
    }
  }

  const handleSubmit = async () => {
    const payloadName = name.trim()
    const payloadUrl = url.trim()

    if (!payloadName) {
      setError("名称不能为空")
      return
    }
    if (!payloadUrl) {
      setError("RSS URL 不能为空")
      return
    }

    setSubmitting(true)
    setError(null)
    try {
      const payload = {
        name: payloadName,
        type: "rss",
        url: payloadUrl,
        config: { category },
      }

      const res = await fetch(
        isEdit ? `${API_BASE}/sources/${source!.id}` : `${API_BASE}/sources`,
        {
          method: isEdit ? "PUT" : "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        }
      )

      if (!res.ok) {
        if (res.status === 400) {
          const data = await res.json()
          throw new Error(data.error || "请求无效")
        }
        throw new Error(`HTTP ${res.status}`)
      }

      onSaved()
      onClose()
    } catch (err) {
      setError(err instanceof Error ? err.message : "保存失败")
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-background/80 backdrop-blur-sm"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose()
      }}
    >
      <div className="w-full max-w-md mx-4 bg-card rounded-2xl shadow-[var(--shadow-pop)] border border-border/60 flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-border/60 shrink-0">
          <h2 className="text-base font-semibold tracking-tight">
            {isEdit ? "编辑 RSS 源" : "新增 RSS 源"}
          </h2>
          <button
            onClick={onClose}
            className="p-2 hover:bg-secondary rounded-lg transition-colors"
          >
            <X className="w-4 h-4 text-muted-foreground" strokeWidth={1.5} />
          </button>
        </div>

        {/* Form content */}
        <div className="flex-1 overflow-auto px-5 py-4 flex flex-col gap-4">
          {error && (
            <div className="px-3 py-2 rounded-lg bg-destructive/10 text-destructive text-xs">
              {error}
            </div>
          )}

          {/* Name */}
          <div className="flex flex-col gap-1">
            <label className="text-xs font-medium text-muted-foreground">
              名称
            </label>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="例如: 机器之心"
              className={cn(
                "w-full px-3 py-2.5 rounded-xl text-sm",
                "bg-secondary/60 border border-border/60",
                "placeholder:text-muted-foreground/60",
                "focus:outline-none focus:ring-1 focus:ring-ring focus:border-ring/50",
                "transition-all duration-200"
              )}
            />
          </div>

          {/* URL + Test */}
          <div className="flex flex-col gap-1">
            <label className="text-xs font-medium text-muted-foreground">
              RSS URL
            </label>
            <div className="flex items-center gap-2">
              <div className="relative flex-1">
                <Globe
                  className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground"
                  strokeWidth={1.5}
                />
                <input
                  type="url"
                  value={url}
                  onChange={(e) => {
                    setUrl(e.target.value)
                    setTestResult(null)
                  }}
                  placeholder="https://.../feed.xml"
                  className={cn(
                    "w-full pl-9 pr-3 py-2.5 rounded-xl text-sm",
                    "bg-secondary/60 border border-border/60",
                    "placeholder:text-muted-foreground/60",
                    "focus:outline-none focus:ring-1 focus:ring-ring focus:border-ring/50",
                    "transition-all duration-200"
                  )}
                />
              </div>
              <button
                onClick={handleTestUrl}
                disabled={testing || !url.trim()}
                className={cn(
                  "inline-flex items-center gap-1.5 px-3 py-2.5 rounded-xl text-xs font-medium",
                  "bg-chart-1/15 text-chart-1 hover:bg-chart-1/20",
                  "transition-all duration-200 disabled:opacity-50 shrink-0"
                )}
              >
                {testing ? (
                  <Loader2
                    className="w-3.5 h-3.5 animate-spin"
                    strokeWidth={1.5}
                  />
                ) : (
                  <Link2 className="w-3.5 h-3.5" strokeWidth={1.5} />
                )}
                测试
              </button>
            </div>
            {testResult && (
              <div
                className={cn(
                  "flex items-center gap-1.5 px-3 py-2 rounded-lg text-xs",
                  testResult.success
                    ? "bg-emerald-500/10 text-emerald-600"
                    : "bg-destructive/10 text-destructive"
                )}
              >
                {testResult.success ? (
                  <CheckCircle2 className="w-3.5 h-3.5 shrink-0" strokeWidth={1.5} />
                ) : (
                  <AlertCircle className="w-3.5 h-3.5 shrink-0" strokeWidth={1.5} />
                )}
                <span className="truncate">{testResult.message}</span>
              </div>
            )}
          </div>

          {/* Category pills */}
          <div className="flex flex-col gap-1">
            <label className="text-xs font-medium text-muted-foreground">
              默认分类
            </label>
            <div className="flex items-center gap-1.5 flex-wrap">
              {categories.map((cat) => (
                <button
                  key={cat}
                  onClick={() => setCategory(cat)}
                  className={cn(
                    "px-2.5 py-1 rounded-lg text-xs font-medium transition-all duration-200",
                    category === cat
                      ? "bg-primary text-primary-foreground shadow-[0_0_12px_rgba(59,130,246,0.25)]"
                      : "bg-secondary/60 text-muted-foreground hover:bg-secondary hover:text-foreground"
                  )}
                >
                  {cat}
                </button>
              ))}
            </div>
          </div>
        </div>

        {/* Footer actions */}
        <div className="flex items-center justify-end gap-2 px-5 py-4 border-t border-border/60 shrink-0">
          <button
            onClick={onClose}
            className="px-4 py-2 rounded-lg text-xs font-medium text-muted-foreground hover:bg-secondary transition-all duration-200"
          >
            取消
          </button>
          <button
            onClick={handleSubmit}
            disabled={submitting || !name.trim() || !url.trim()}
            className={cn(
              "inline-flex items-center gap-1.5 px-4 py-2 rounded-lg text-xs font-medium",
              "bg-primary text-primary-foreground hover:bg-primary/90",
              "transition-all duration-200 disabled:opacity-50"
            )}
          >
            {submitting && (
              <Loader2
                className="w-3.5 h-3.5 animate-spin"
                strokeWidth={1.5}
              />
            )}
            {isEdit ? "保存" : "创建"}
          </button>
        </div>
      </div>
    </div>
  )
}
