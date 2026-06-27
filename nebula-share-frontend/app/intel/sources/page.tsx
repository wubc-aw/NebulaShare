"use client"

import { useState, useEffect, useCallback } from "react"
import { Plus, Loader2, ArrowLeft, Radio } from "lucide-react"
import Link from "next/link"
import { SourceManager, type Source } from "@/components/intel/source-manager"
import { SourceForm, type SourceFormData } from "@/components/intel/source-form"
import { cn } from "@/lib/utils"

const API_BASE = "/api/intel"

export default function SourcesPage() {
  const [sources, setSources] = useState<Source[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // Modal state
  const [showForm, setShowForm] = useState(false)
  const [editingSource, setEditingSource] = useState<SourceFormData | null>(null)

  // Fetch sources
  const fetchSources = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const res = await fetch(`${API_BASE}/sources`)
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      const data = await res.json()
      setSources(data.sources || [])
    } catch (err) {
      setError(err instanceof Error ? err.message : "加载失败")
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchSources()
  }, [fetchSources])

  // Toggle active (pause/resume)
  const handleToggleActive = useCallback(async (source: Source) => {
    const res = await fetch(`${API_BASE}/sources/${source.id}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ is_active: !source.is_active }),
    })
    if (!res.ok) throw new Error(`HTTP ${res.status}`)
    await fetchSources()
  }, [fetchSources])

  // Delete source
  const handleDelete = useCallback(async (sourceId: number) => {
    const res = await fetch(`${API_BASE}/sources/${sourceId}`, {
      method: "DELETE",
    })
    if (!res.ok) throw new Error(`HTTP ${res.status}`)
    await fetchSources()
  }, [fetchSources])

  // Open edit modal
  const handleEdit = useCallback((source: Source) => {
    setEditingSource({
      id: source.id,
      name: source.name,
      url: source.url || "",
      category: (source.config?.category as string) || "阅读",
    })
    setShowForm(true)
  }, [])

  // Open add modal
  const handleAdd = useCallback(() => {
    setEditingSource(null)
    setShowForm(true)
  }, [])

  // Close modal
  const handleCloseForm = useCallback(() => {
    setShowForm(false)
    setEditingSource(null)
  }, [])

  // After save
  const handleSaved = useCallback(() => {
    fetchSources()
  }, [fetchSources])

  const rssCount = sources.filter((s) => s.type === "rss").length
  const activeCount = sources.filter((s) => s.is_active).length

  return (
    <div className="p-6 sm:p-8 max-w-4xl mx-auto h-full flex flex-col">
      {/* Header */}
      <div className="flex items-center justify-between mb-6 shrink-0">
        <div className="flex items-center gap-3">
          <Link
            href="/intel"
            className="p-2 rounded-xl hover:bg-secondary transition-colors"
            title="返回情报站"
          >
            <ArrowLeft className="w-4 h-4 text-muted-foreground" strokeWidth={1.5} />
          </Link>
          <div>
            <h1 className="text-2xl font-bold tracking-tight">信息源管理</h1>
            <p className="text-sm text-muted-foreground mt-1">
              {sources.length} 个源 · {rssCount} 个 RSS · {activeCount} 个活跃
            </p>
          </div>
        </div>
        <button
          onClick={handleAdd}
          className={cn(
            "flex items-center gap-1.5 px-4 py-2 rounded-xl text-sm font-medium",
            "bg-chart-4/10 text-chart-4 hover:bg-chart-4/15 transition-colors"
          )}
        >
          <Plus className="w-4 h-4" strokeWidth={1.5} />
          新增 RSS 源
        </button>
      </div>

      {/* Main card */}
      <div className="flex-1 flex flex-col min-h-0 bg-card rounded-2xl shadow-[var(--shadow-card)] border border-border/40 overflow-hidden">
        {/* Content area */}
        <div className="flex-1 overflow-auto p-5">
          {error ? (
            <div className="flex-1 flex items-center justify-center min-h-[200px]">
              <div className="text-center">
                <Radio className="w-8 h-8 text-destructive/40 mx-auto mb-3" strokeWidth={1.5} />
                <p className="text-sm text-destructive">{error}</p>
              </div>
            </div>
          ) : (
            <SourceManager
              sources={sources}
              loading={loading}
              onToggleActive={handleToggleActive}
              onDelete={handleDelete}
              onEdit={handleEdit}
            />
          )}
        </div>
      </div>

      {/* SourceForm modal */}
      {showForm && (
        <SourceForm
          source={editingSource}
          onClose={handleCloseForm}
          onSaved={handleSaved}
        />
      )}
    </div>
  )
}
