"use client"

import { useState, useEffect, useCallback } from "react"
import { Loader2, BookOpen, Plus, Tag } from "lucide-react"
import { SearchBar } from "@/components/intel/search-bar"
import { ArticleList } from "@/components/intel/article-list"
import { ArticleReader } from "@/components/intel/article-reader"
import { SyncButton } from "@/components/intel/sync-button"
import { ArticleForm } from "@/components/intel/article-form"
import { TagSelector } from "@/components/intel/tag-selector"
import { StatsPanel } from "@/components/intel/stats-panel"
import type { Article } from "@/components/intel/article-list-item"

const API_BASE = "/api/intel"

export default function IntelPage() {
  const [articles, setArticles] = useState<Article[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // Filters
  const [search, setSearch] = useState("")
  const [category, setCategory] = useState("")
  const [starredOnly, setStarredOnly] = useState(false)
  const [unreadOnly, setUnreadOnly] = useState(false)

  // Selection
  const [selectedArticle, setSelectedArticle] = useState<Article | null>(null)

  // Form modal
  const [showForm, setShowForm] = useState(false)

  // Fetch articles
  const fetchArticles = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const params = new URLSearchParams()
      if (search) params.append("search", search)
      if (category) params.append("category", category)
      if (starredOnly) params.append("starred", "true")
      if (unreadOnly) params.append("unread", "true")

      const res = await fetch(`${API_BASE}/articles?${params.toString()}`)
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      const data = await res.json()
      setArticles(data.articles || [])
    } catch (err) {
      setError(err instanceof Error ? err.message : "加载失败")
    } finally {
      setLoading(false)
    }
  }, [search, category, starredOnly, unreadOnly])

  useEffect(() => {
    fetchArticles()
  }, [fetchArticles])

  // Update article (read/star/archive)
  const handleUpdate = useCallback(async (articleId: string, updates: Partial<Article>) => {
    // Optimistic update
    setArticles((prev) =>
      prev.map((a) => (a.id === articleId ? { ...a, ...updates } : a))
    )
    if (selectedArticle?.id === articleId) {
      setSelectedArticle((prev) => (prev ? { ...prev, ...updates } : prev))
    }

    try {
      const res = await fetch(`${API_BASE}/articles/${articleId}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(updates),
      })
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
    } catch (err) {
      // Revert on error — re-fetch to restore truth
      fetchArticles()
    }
  }, [selectedArticle, fetchArticles])

  // Select article + auto-mark as read
  const handleSelect = useCallback((article: Article) => {
    setSelectedArticle(article)
    if (!article.is_read) {
      handleUpdate(article.id, { is_read: true })
    }
  }, [handleUpdate])

  // Toggle star
  const handleToggleStar = useCallback((articleId: string) => {
    const article = articles.find((a) => a.id === articleId)
    if (article) {
      handleUpdate(articleId, { is_starred: !article.is_starred })
    }
  }, [articles, handleUpdate])

  // Sync
  const handleSync = useCallback(async () => {
    const res = await fetch(`${API_BASE}/sync`, { method: "POST" })
    if (!res.ok) throw new Error(`Sync failed: HTTP ${res.status}`)
    await fetchArticles()
  }, [fetchArticles])

  const unreadCount = articles.filter((a) => !a.is_read).length

  return (
    <div className="p-6 sm:p-8 max-w-6xl mx-auto h-full flex flex-col">
      {/* Header */}
      <div className="flex items-center justify-between mb-6 shrink-0">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">情报站</h1>
          <p className="text-sm text-muted-foreground mt-1">
            {articles.length} 篇文章 · {unreadCount} 篇未读
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => setShowForm(true)}
            className="flex items-center gap-1.5 px-4 py-2 rounded-xl text-sm font-medium bg-chart-4/10 text-chart-4 hover:bg-chart-4/15 transition-colors"
          >
            <Plus className="w-4 h-4" strokeWidth={1.5} />
            新建
          </button>
          <SyncButton onSync={handleSync} />
        </div>
      </div>

      {/* Stats panel */}
      <StatsPanel />

      {/* Main card */}
      <div className="flex-1 flex flex-col min-h-0 bg-card rounded-2xl shadow-[var(--shadow-card)] border border-border/40 overflow-hidden">
        {/* Search bar */}
        <div className="px-5 pt-5 pb-3 shrink-0">
          <SearchBar
            search={search}
            onSearchChange={setSearch}
            category={category}
            onCategoryChange={setCategory}
            starredOnly={starredOnly}
            onStarredChange={setStarredOnly}
            unreadOnly={unreadOnly}
            onUnreadChange={setUnreadOnly}
          />
        </div>

        {/* Content area */}
        <div className="flex-1 flex min-h-0 px-5 pb-5">
          {/* Article list */}
          <div className={"flex-1 flex flex-col min-w-0" + (selectedArticle ? " hidden md:flex" : "")}>
            {loading ? (
              <div className="flex-1 flex items-center justify-center min-h-[200px]">
                <Loader2 className="w-6 h-6 text-muted-foreground animate-spin" strokeWidth={1.5} />
              </div>
            ) : error ? (
              <div className="flex-1 flex items-center justify-center min-h-[200px]">
                <p className="text-sm text-destructive">{error}</p>
              </div>
            ) : (
              <ArticleList
                articles={articles}
                selectedId={selectedArticle?.id || null}
                onSelect={handleSelect}
                onToggleStar={handleToggleStar}
              />
            )}
          </div>

          {/* Reader panel */}
          <ArticleReader
            article={selectedArticle}
            onClose={() => setSelectedArticle(null)}
            onUpdate={handleUpdate}
          />
        </div>
      </div>

      {/* ArticleForm modal */}
      {showForm && (
        <ArticleForm
          onClose={() => setShowForm(false)}
          onCreated={() => { setShowForm(false); fetchArticles() }}
        />
      )}
    </div>
  )
}
