"use client"

import { useState, useEffect } from "react"
import { BookOpen, Eye, Star, BarChart3, Loader2 } from "lucide-react"

interface StatsData {
  total_articles: number
  unread_count: number
  starred_count: number
  category_breakdown: Record<string, number>
  source_breakdown: Record<string, number>
}

const API_BASE = "/api/intel"

function StatCard({
  icon: Icon,
  label,
  value,
  colorClass,
}: {
  icon: React.ElementType
  label: string
  value: number | string
  colorClass: string
}) {
  return (
    <div className="bg-card border border-border/40 rounded-xl p-4 flex items-center gap-4">
      <div className={`w-10 h-10 rounded-lg ${colorClass} flex items-center justify-center shrink-0`}>
        <Icon className="w-5 h-5" strokeWidth={1.5} />
      </div>
      <div>
        <p className="text-2xl font-bold tracking-tight">{value}</p>
        <p className="text-xs text-muted-foreground">{label}</p>
      </div>
    </div>
  )
}

export function StatsPanel() {
  const [stats, setStats] = useState<StatsData | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const fetchStats = async () => {
      try {
        const res = await fetch(`${API_BASE}/stats`)
        if (!res.ok) throw new Error(`HTTP ${res.status}`)
        const data = await res.json()
        setStats(data)
      } catch (err) {
        setError(err instanceof Error ? err.message : "加载失败")
      } finally {
        setLoading(false)
      }
    }

    fetchStats()
  }, [])

  if (loading) {
    return (
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
        {[...Array(4)].map((_, i) => (
          <div
            key={i}
            className="bg-card border border-border/40 rounded-xl p-4 flex items-center gap-4 animate-pulse"
          >
            <div className="w-10 h-10 rounded-lg bg-muted shrink-0" />
            <div className="space-y-2">
              <div className="w-12 h-6 bg-muted rounded" />
              <div className="w-20 h-3 bg-muted rounded" />
            </div>
          </div>
        ))}
      </div>
    )
  }

  if (error || !stats) {
    return (
      <div className="bg-card border border-border/40 rounded-xl p-4 mb-6 flex items-center gap-2 text-destructive text-sm">
        <Loader2 className="w-4 h-4 animate-spin" />
        统计加载失败
      </div>
    )
  }

  const topCategories = Object.entries(stats.category_breakdown)
    .sort(([, a], [, b]) => b - a)
    .slice(0, 3)

  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
      <StatCard
        icon={BookOpen}
        label="总文章数"
        value={stats.total_articles}
        colorClass="bg-primary/10 text-primary"
      />
      <StatCard
        icon={Eye}
        label="未读"
        value={stats.unread_count}
        colorClass="bg-chart-2/10 text-chart-2"
      />
      <StatCard
        icon={Star}
        label="星标"
        value={stats.starred_count}
        colorClass="bg-chart-4/10 text-chart-4"
      />
      <div className="bg-card border border-border/40 rounded-xl p-4 flex items-center gap-4">
        <div className="w-10 h-10 rounded-lg bg-chart-3/10 text-chart-3 flex items-center justify-center shrink-0">
          <BarChart3 className="w-5 h-5" strokeWidth={1.5} />
        </div>
        <div className="min-w-0 flex-1">
          {topCategories.length > 0 ? (
            <div className="space-y-1">
              {topCategories.map(([name, count]) => (
                <div key={name} className="flex items-center justify-between gap-2">
                  <span className="text-xs text-muted-foreground truncate">{name}</span>
                  <span className="text-xs font-medium tabular-nums">{count}</span>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-xs text-muted-foreground">暂无分类数据</p>
          )}
          <p className="text-xs text-muted-foreground mt-1">热门分类</p>
        </div>
      </div>
    </div>
  )
}
