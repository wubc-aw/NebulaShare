"use client"

import { useState } from "react"
import { X, Link2, PenLine, Loader2, Globe } from "lucide-react"
import { cn } from "@/lib/utils"

interface ArticleFormProps {
  onClose: () => void
  onCreated: () => void
}

type Mode = "url" | "manual"

const categories = ["AI", "互联网", "金融", "创投", "工具", "阅读"]

const API_BASE = "/api/intel"

interface ScrapeResult {
  title?: string
  summary?: string
  content?: string
  url?: string
  error?: string
}

export function ArticleForm({ onClose, onCreated }: ArticleFormProps) {
  const [mode, setMode] = useState<Mode>("url")
  const [url, setUrl] = useState("")
  const [title, setTitle] = useState("")
  const [category, setCategory] = useState("阅读")
  const [summary, setSummary] = useState("")
  const [content, setContent] = useState("")
  const [scraping, setScraping] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const handleScrape = async () => {
    const targetUrl = url.trim()
    if (!targetUrl) {
      setError("请输入 URL")
      return
    }
    setScraping(true)
    setError(null)
    try {
      const res = await fetch(`${API_BASE}/scrape`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url: targetUrl }),
      })
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      const data: ScrapeResult = await res.json()
      if (data.error) throw new Error(data.error)
      setTitle(data.title || "")
      setSummary(data.summary || "")
      setContent(data.content || "")
      // Switch to manual mode so user can review/edit before submitting
      setMode("manual")
    } catch (err) {
      setError(err instanceof Error ? err.message : "抓取失败")
    } finally {
      setScraping(false)
    }
  }

  const handleSubmit = async () => {
    const payloadTitle = title.trim()
    if (!payloadTitle) {
      setError("标题不能为空")
      return
    }

    setSubmitting(true)
    setError(null)
    try {
      const res = await fetch(`${API_BASE}/articles`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          title: payloadTitle,
          category,
          summary: summary.trim(),
          content: content.trim(),
          url: url.trim(),
          source_id: 2,
        }),
      })
      if (!res.ok) {
        if (res.status === 400) {
          const data = await res.json()
          throw new Error(data.error || "请求无效")
        }
        throw new Error(`HTTP ${res.status}`)
      }
      onCreated()
      onClose()
    } catch (err) {
      setError(err instanceof Error ? err.message : "创建失败")
    } finally {
      setSubmitting(false)
    }
  }

  const resetForm = () => {
    setUrl("")
    setTitle("")
    setCategory("阅读")
    setSummary("")
    setContent("")
    setError(null)
  }

  const handleModeChange = (newMode: Mode) => {
    setMode(newMode)
    setError(null)
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-background/80 backdrop-blur-sm"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose()
      }}
    >
      <div className="w-full max-w-lg mx-4 bg-card rounded-2xl shadow-[var(--shadow-pop)] border border-border/60 flex flex-col max-h-[85vh]">
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-border/60 shrink-0">
          <h2 className="text-base font-semibold tracking-tight">新建文章</h2>
          <button
            onClick={onClose}
            className="p-2 hover:bg-secondary rounded-lg transition-colors"
          >
            <X className="w-4 h-4 text-muted-foreground" strokeWidth={1.5} />
          </button>
        </div>

        {/* Mode switch */}
        <div className="flex items-center gap-1 px-5 pt-4 shrink-0">
          <button
            onClick={() => handleModeChange("url")}
            className={cn(
              "flex-1 inline-flex items-center justify-center gap-1.5 px-3 py-2 rounded-lg text-xs font-medium transition-all duration-200",
              mode === "url"
                ? "bg-chart-1/15 text-chart-1 border border-chart-1/30"
                : "bg-secondary/60 text-muted-foreground hover:bg-secondary hover:text-foreground border border-transparent"
            )}
          >
            <Link2 className="w-3.5 h-3.5" strokeWidth={1.5} />
            粘贴链接
          </button>
          <button
            onClick={() => handleModeChange("manual")}
            className={cn(
              "flex-1 inline-flex items-center justify-center gap-1.5 px-3 py-2 rounded-lg text-xs font-medium transition-all duration-200",
              mode === "manual"
                ? "bg-chart-1/15 text-chart-1 border border-chart-1/30"
                : "bg-secondary/60 text-muted-foreground hover:bg-secondary hover:text-foreground border border-transparent"
            )}
          >
            <PenLine className="w-3.5 h-3.5" strokeWidth={1.5} />
            手动撰写
          </button>
        </div>

        {/* Form content */}
        <div className="flex-1 overflow-auto px-5 py-4 flex flex-col gap-3">
          {error && (
            <div className="px-3 py-2 rounded-lg bg-destructive/10 text-destructive text-xs">
              {error}
            </div>
          )}

          {/* URL mode */}
          {mode === "url" && (
            <div className="flex flex-col gap-3">
              <div className="flex items-center gap-2">
                <div className="relative flex-1">
                  <Globe className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" strokeWidth={1.5} />
                  <input
                    type="url"
                    value={url}
                    onChange={(e) => setUrl(e.target.value)}
                    placeholder="https://..."
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
                  onClick={handleScrape}
                  disabled={scraping || !url.trim()}
                  className={cn(
                    "inline-flex items-center gap-1.5 px-4 py-2.5 rounded-xl text-xs font-medium",
                    "bg-chart-1/15 text-chart-1 hover:bg-chart-1/20",
                    "transition-all duration-200 disabled:opacity-50 shrink-0"
                  )}
                >
                  {scraping ? (
                    <Loader2 className="w-3.5 h-3.5 animate-spin" strokeWidth={1.5} />
                  ) : (
                    <Link2 className="w-3.5 h-3.5" strokeWidth={1.5} />
                  )}
                  抓取
                </button>
              </div>
              <p className="text-xs text-muted-foreground">
                输入文章链接，系统将自动提取标题、摘要和正文内容。
              </p>
            </div>
          )}

          {/* Manual mode fields */}
          {mode === "manual" && (
            <div className="flex flex-col gap-3">
              {/* Title */}
              <div className="flex flex-col gap-1">
                <label className="text-xs font-medium text-muted-foreground">标题</label>
                <input
                  type="text"
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                  placeholder="文章标题"
                  className={cn(
                    "w-full px-3 py-2 rounded-xl text-sm",
                    "bg-secondary/60 border border-border/60",
                    "placeholder:text-muted-foreground/60",
                    "focus:outline-none focus:ring-1 focus:ring-ring focus:border-ring/50",
                    "transition-all duration-200"
                  )}
                />
              </div>

              {/* Category pills */}
              <div className="flex flex-col gap-1">
                <label className="text-xs font-medium text-muted-foreground">分类</label>
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

              {/* Summary */}
              <div className="flex flex-col gap-1">
                <label className="text-xs font-medium text-muted-foreground">摘要</label>
                <textarea
                  value={summary}
                  onChange={(e) => setSummary(e.target.value)}
                  placeholder="文章摘要..."
                  rows={3}
                  className={cn(
                    "w-full px-3 py-2 rounded-xl text-sm resize-none",
                    "bg-secondary/60 border border-border/60",
                    "placeholder:text-muted-foreground/60",
                    "focus:outline-none focus:ring-1 focus:ring-ring focus:border-ring/50",
                    "transition-all duration-200"
                  )}
                />
              </div>

              {/* Content */}
              <div className="flex flex-col gap-1">
                <label className="text-xs font-medium text-muted-foreground">正文</label>
                <textarea
                  value={content}
                  onChange={(e) => setContent(e.target.value)}
                  placeholder="文章正文（支持 HTML）..."
                  rows={6}
                  className={cn(
                    "w-full px-3 py-2 rounded-xl text-sm resize-none",
                    "bg-secondary/60 border border-border/60",
                    "placeholder:text-muted-foreground/60",
                    "focus:outline-none focus:ring-1 focus:ring-ring focus:border-ring/50",
                    "transition-all duration-200"
                  )}
                />
              </div>

              {/* URL (optional, for manual mode too) */}
              <div className="flex flex-col gap-1">
                <label className="text-xs font-medium text-muted-foreground">原文链接（可选）</label>
                <div className="relative">
                  <Globe className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" strokeWidth={1.5} />
                  <input
                    type="url"
                    value={url}
                    onChange={(e) => setUrl(e.target.value)}
                    placeholder="https://..."
                    className={cn(
                      "w-full pl-9 pr-3 py-2 rounded-xl text-sm",
                      "bg-secondary/60 border border-border/60",
                      "placeholder:text-muted-foreground/60",
                      "focus:outline-none focus:ring-1 focus:ring-ring focus:border-ring/50",
                      "transition-all duration-200"
                    )}
                  />
                </div>
              </div>
            </div>
          )}
        </div>

        {/* Footer actions */}
        <div className="flex items-center justify-end gap-2 px-5 py-4 border-t border-border/60 shrink-0">
          <button
            onClick={() => {
              resetForm()
              onClose()
            }}
            className="px-4 py-2 rounded-lg text-xs font-medium text-muted-foreground hover:bg-secondary transition-all duration-200"
          >
            取消
          </button>
          {mode === "manual" && (
            <button
              onClick={handleSubmit}
              disabled={submitting || !title.trim()}
              className={cn(
                "inline-flex items-center gap-1.5 px-4 py-2 rounded-lg text-xs font-medium",
                "bg-primary text-primary-foreground hover:bg-primary/90",
                "transition-all duration-200 disabled:opacity-50"
              )}
            >
              {submitting && <Loader2 className="w-3.5 h-3.5 animate-spin" strokeWidth={1.5} />}
              创建文章
            </button>
          )}
        </div>
      </div>
    </div>
  )
}
