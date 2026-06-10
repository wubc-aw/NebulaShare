"use client"

import { useState } from "react"
import {
  Pause,
  Play,
  Pencil,
  Trash2,
  AlertTriangle,
  CheckCircle2,
  XCircle,
  Loader2,
  Rss,
  Globe,
  FileText,
} from "lucide-react"
import { cn } from "@/lib/utils"

export interface Source {
  id: number
  name: string
  type: "hermes" | "rss" | "manual"
  url?: string
  is_active: boolean
  last_fetch_at?: string
  last_error?: string
  error_count: number
  article_count: number
  config?: Record<string, unknown>
  created_at?: string
}

interface SourceManagerProps {
  sources: Source[]
  loading: boolean
  onToggleActive: (source: Source) => Promise<void>
  onDelete: (sourceId: number) => Promise<void>
  onEdit: (source: Source) => void
}

const typeConfig: Record<
  string,
  { label: string; icon: React.ReactNode; color: string }
> = {
  hermes: {
    label: "hermes",
    icon: <Globe className="w-3 h-3" strokeWidth={1.5} />,
    color: "bg-chart-2/15 text-chart-2 border-chart-2/30",
  },
  rss: {
    label: "rss",
    icon: <Rss className="w-3 h-3" strokeWidth={1.5} />,
    color: "bg-chart-4/15 text-chart-4 border-chart-4/30",
  },
  manual: {
    label: "manual",
    icon: <FileText className="w-3 h-3" strokeWidth={1.5} />,
    color: "bg-muted/60 text-muted-foreground border-muted/40",
  },
}

function formatLastSync(lastFetchAt?: string): string {
  if (!lastFetchAt) return "从未同步"
  const date = new Date(lastFetchAt)
  const now = new Date()
  const diffMs = now.getTime() - date.getTime()
  const diffMins = Math.floor(diffMs / 60000)
  const diffHours = Math.floor(diffMs / 3600000)
  const diffDays = Math.floor(diffMs / 86400000)

  if (diffMins < 1) return "刚刚"
  if (diffMins < 60) return `${diffMins} 分钟前`
  if (diffHours < 24) return `${diffHours} 小时前`
  if (diffDays < 7) return `${diffDays} 天前`
  return date.toLocaleDateString("zh-CN", { month: "short", day: "numeric" })
}

export function SourceManager({
  sources,
  loading,
  onToggleActive,
  onDelete,
  onEdit,
}: SourceManagerProps) {
  const [togglingId, setTogglingId] = useState<number | null>(null)
  const [deletingId, setDeletingId] = useState<number | null>(null)

  const handleToggle = async (source: Source) => {
    if (source.type !== "rss" || togglingId === source.id) return
    setTogglingId(source.id)
    try {
      await onToggleActive(source)
    } finally {
      setTogglingId(null)
    }
  }

  const handleDelete = async (source: Source) => {
    if (source.type !== "rss" || deletingId === source.id) return
    setDeletingId(source.id)
    try {
      await onDelete(source.id)
    } finally {
      setDeletingId(null)
    }
  }

  if (loading) {
    return (
      <div className="flex-1 flex items-center justify-center min-h-[200px]">
        <Loader2 className="w-6 h-6 text-muted-foreground animate-spin" strokeWidth={1.5} />
      </div>
    )
  }

  if (sources.length === 0) {
    return (
      <div className="flex-1 flex items-center justify-center min-h-[200px]">
        <div className="text-center">
          <Rss className="w-8 h-8 text-muted-foreground/40 mx-auto mb-3" strokeWidth={1.5} />
          <p className="text-sm text-muted-foreground">暂无信息源</p>
          <p className="text-xs text-muted-foreground/60 mt-1">
            点击右上角按钮添加 RSS 源
          </p>
        </div>
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-2">
      {sources.map((source) => {
        const typeCfg = typeConfig[source.type] || typeConfig.manual
        const isHermes = source.type === "hermes"
        const isRss = source.type === "rss"
        const isInactive = !source.is_active
        const hasError = !!source.last_error && source.error_count > 0
        const isAutoPaused = isInactive && hasError && source.error_count >= 3

        return (
          <div
            key={source.id}
            className={cn(
              "group relative flex items-center gap-4 px-4 py-3.5 rounded-xl",
              "border border-border/40 transition-all duration-200",
              isInactive
                ? "bg-secondary/30 opacity-70"
                : "bg-card hover:bg-secondary/20 hover:shadow-[var(--shadow-card)]"
            )}
          >
            {/* Active status indicator */}
            <div className="shrink-0">
              {isInactive ? (
                <XCircle
                  className={cn(
                    "w-4 h-4",
                    isAutoPaused ? "text-destructive" : "text-muted-foreground/50"
                  )}
                  strokeWidth={1.5}
                />
              ) : (
                <CheckCircle2 className="w-4 h-4 text-emerald-500" strokeWidth={1.5} />
              )}
            </div>

            {/* Source info */}
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2 mb-1">
                <span className="text-sm font-medium truncate">{source.name}</span>
                <span
                  className={cn(
                    "inline-flex items-center gap-1 px-1.5 py-0.5 rounded-md text-[10px] font-medium border",
                    typeCfg.color
                  )}
                >
                  {typeCfg.icon}
                  {typeCfg.label}
                </span>
                {isAutoPaused && (
                  <span
                    className="inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded-md text-[10px] font-medium bg-destructive/10 text-destructive border border-destructive/20"
                    title="连续失败多次，已自动暂停"
                  >
                    <AlertTriangle className="w-3 h-3" strokeWidth={1.5} />
                    自动暂停
                  </span>
                )}
              </div>

              <div className="flex items-center gap-3 text-xs text-muted-foreground">
                <span>{source.article_count} 篇文章</span>
                <span className="text-border">·</span>
                <span>上次同步: {formatLastSync(source.last_fetch_at)}</span>
                {hasError && (
                  <>
                    <span className="text-border">·</span>
                    <span className="text-destructive/80 truncate max-w-[200px]" title={source.last_error}>
                      {source.last_error}
                    </span>
                  </>
                )}
              </div>
            </div>

            {/* Actions */}
            <div className="flex items-center gap-1 shrink-0 opacity-0 group-hover:opacity-100 transition-opacity duration-200">
              {/* Pause/Resume — RSS only */}
              {isRss && (
                <button
                  onClick={() => handleToggle(source)}
                  disabled={togglingId === source.id}
                  className={cn(
                    "p-2 rounded-lg transition-all duration-200",
                    isInactive
                      ? "text-emerald-500 hover:bg-emerald-500/10"
                      : "text-amber-500 hover:bg-amber-500/10",
                    "disabled:opacity-50"
                  )}
                  title={isInactive ? "恢复同步" : "暂停同步"}
                >
                  {togglingId === source.id ? (
                    <Loader2 className="w-3.5 h-3.5 animate-spin" strokeWidth={1.5} />
                  ) : isInactive ? (
                    <Play className="w-3.5 h-3.5" strokeWidth={1.5} />
                  ) : (
                    <Pause className="w-3.5 h-3.5" strokeWidth={1.5} />
                  )}
                </button>
              )}

              {/* Edit — RSS only */}
              {isRss && (
                <button
                  onClick={() => onEdit(source)}
                  className="p-2 rounded-lg text-muted-foreground hover:text-foreground hover:bg-secondary transition-all duration-200"
                  title="编辑"
                >
                  <Pencil className="w-3.5 h-3.5" strokeWidth={1.5} />
                </button>
              )}

              {/* Delete — RSS only */}
              {isRss && (
                <button
                  onClick={() => handleDelete(source)}
                  disabled={deletingId === source.id}
                  className="p-2 rounded-lg text-muted-foreground hover:text-destructive hover:bg-destructive/10 transition-all duration-200 disabled:opacity-50"
                  title="删除"
                >
                  {deletingId === source.id ? (
                    <Loader2 className="w-3.5 h-3.5 animate-spin" strokeWidth={1.5} />
                  ) : (
                    <Trash2 className="w-3.5 h-3.5" strokeWidth={1.5} />
                  )}
                </button>
              )}

              {/* Hermes is read-only — no actions */}
              {isHermes && (
                <span className="text-[10px] text-muted-foreground/50 px-2">
                  系统源
                </span>
              )}
            </div>
          </div>
        )
      })}
    </div>
  )
}
