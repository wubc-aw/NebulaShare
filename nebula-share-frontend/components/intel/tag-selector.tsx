"use client"

import { useState, useEffect, useRef, useCallback } from "react"
import { Tag, Plus, X, Loader2 } from "lucide-react"
import { cn } from "@/lib/utils"

export interface TagItem {
  id: number
  name: string
  color: string
  usage_count?: number
}

interface TagSelectorProps {
  articleId: number
  selectedTags: TagItem[]
  onChange: (tags: TagItem[]) => void
}

const API_BASE = "/api/intel"

export function TagSelector({ articleId, selectedTags, onChange }: TagSelectorProps) {
  const [isOpen, setIsOpen] = useState(false)
  const [allTags, setAllTags] = useState<TagItem[]>([])
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [isCreating, setIsCreating] = useState(false)
  const [newTagName, setNewTagName] = useState("")
  const [creating, setCreating] = useState(false)
  const popoverRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  // Fetch all tags on mount and when opened
  const fetchTags = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const res = await fetch(`${API_BASE}/tags`)
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      const data = await res.json()
      setAllTags(data.tags || [])
    } catch (err) {
      setError(err instanceof Error ? err.message : "加载失败")
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    if (isOpen) {
      fetchTags()
    }
  }, [isOpen, fetchTags])

  // Focus input when creating new tag
  useEffect(() => {
    if (isCreating && inputRef.current) {
      inputRef.current.focus()
    }
  }, [isCreating])

  // Close popover on outside click
  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (popoverRef.current && !popoverRef.current.contains(e.target as Node)) {
        setIsOpen(false)
        setIsCreating(false)
        setNewTagName("")
      }
    }
    if (isOpen) {
      document.addEventListener("mousedown", handleClickOutside)
    }
    return () => document.removeEventListener("mousedown", handleClickOutside)
  }, [isOpen])

  const selectedTagIds = new Set(selectedTags.map((t) => t.id))

  const handleToggleTag = async (tag: TagItem) => {
    const newSelected = selectedTagIds.has(tag.id)
      ? selectedTags.filter((t) => t.id !== tag.id)
      : [...selectedTags, tag]

    // Optimistic update
    onChange(newSelected)
    setSaving(true)

    try {
      const res = await fetch(`${API_BASE}/articles/${articleId}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ tags: newSelected.map((t) => t.id) }),
      })
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
    } catch (err) {
      // Revert on error
      onChange(selectedTags)
      setError(err instanceof Error ? err.message : "保存失败")
    } finally {
      setSaving(false)
    }
  }

  const handleCreateTag = async () => {
    const name = newTagName.trim()
    if (!name) return

    setCreating(true)
    setError(null)
    try {
      const res = await fetch(`${API_BASE}/tags`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name }),
      })
      if (!res.ok) {
        if (res.status === 400) {
          const data = await res.json()
          throw new Error(data.error || "标签名无效")
        }
        throw new Error(`HTTP ${res.status}`)
      }
      const newTag: TagItem = await res.json()
      setAllTags((prev) => [...prev, newTag])
      setNewTagName("")
      setIsCreating(false)
      // Auto-select the new tag
      handleToggleTag(newTag)
    } catch (err) {
      setError(err instanceof Error ? err.message : "创建失败")
    } finally {
      setCreating(false)
    }
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter") {
      e.preventDefault()
      handleCreateTag()
    }
    if (e.key === "Escape") {
      setIsCreating(false)
      setNewTagName("")
    }
  }

  return (
    <div className="relative" ref={popoverRef}>
      {/* Trigger button */}
      <button
        onClick={() => setIsOpen(!isOpen)}
        className={cn(
          "inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-xs font-medium transition-all duration-200",
          isOpen
            ? "bg-chart-1/15 text-chart-1 border border-chart-1/30"
            : "bg-secondary/60 text-muted-foreground hover:bg-secondary hover:text-foreground border border-transparent"
        )}
      >
        <Tag className="w-3 h-3" strokeWidth={1.5} />
        {selectedTags.length > 0 ? `${selectedTags.length} 个标签` : "标签"}
        {saving && <Loader2 className="w-3 h-3 animate-spin" strokeWidth={1.5} />}
      </button>

      {/* Popover */}
      {isOpen && (
        <div
          className={cn(
            "absolute z-50 mt-2 w-64",
            "bg-card rounded-xl shadow-[var(--shadow-pop)] border border-border/60",
            "p-3 flex flex-col gap-2"
          )}
        >
          {loading ? (
            <div className="flex items-center justify-center py-4">
              <Loader2 className="w-4 h-4 text-muted-foreground animate-spin" strokeWidth={1.5} />
            </div>
          ) : error ? (
            <div className="text-xs text-destructive text-center py-2">{error}</div>
          ) : (
            <>
              {/* Tag pills */}
              <div className="flex flex-wrap gap-1.5 max-h-40 overflow-y-auto">
                {allTags.length === 0 ? (
                  <span className="text-xs text-muted-foreground py-1">暂无标签</span>
                ) : (
                  allTags.map((tag) => {
                    const isSelected = selectedTagIds.has(tag.id)
                    return (
                      <button
                        key={tag.id}
                        onClick={() => handleToggleTag(tag)}
                        className={cn(
                          "inline-flex items-center gap-1 px-2 py-1 rounded-md text-xs font-medium transition-all duration-200",
                          isSelected
                            ? "text-white shadow-[0_0_8px_rgba(0,0,0,0.15)]"
                            : "bg-secondary/60 text-muted-foreground hover:bg-secondary hover:text-foreground"
                        )}
                        style={
                          isSelected
                            ? { backgroundColor: tag.color }
                            : undefined
                        }
                      >
                        {tag.name}
                        {isSelected && <X className="w-2.5 h-2.5" strokeWidth={2} />}
                      </button>
                    )
                  })
                )}
              </div>

              {/* Create new tag */}
              {isCreating ? (
                <div className="flex items-center gap-1.5 mt-1">
                  <input
                    ref={inputRef}
                    type="text"
                    value={newTagName}
                    onChange={(e) => setNewTagName(e.target.value)}
                    onKeyDown={handleKeyDown}
                    placeholder="标签名称"
                    className={cn(
                      "flex-1 px-2 py-1 rounded-lg text-xs",
                      "bg-secondary/60 border border-border/60",
                      "placeholder:text-muted-foreground/60",
                      "focus:outline-none focus:ring-1 focus:ring-ring focus:border-ring/50"
                    )}
                  />
                  <button
                    onClick={handleCreateTag}
                    disabled={creating || !newTagName.trim()}
                    className="p-1.5 rounded-lg bg-chart-1/15 text-chart-1 hover:bg-chart-1/20 transition-colors disabled:opacity-50"
                  >
                    {creating ? (
                      <Loader2 className="w-3 h-3 animate-spin" strokeWidth={1.5} />
                    ) : (
                      <Plus className="w-3 h-3" strokeWidth={1.5} />
                    )}
                  </button>
                </div>
              ) : (
                <button
                  onClick={() => setIsCreating(true)}
                  className="inline-flex items-center gap-1.5 px-2 py-1 rounded-lg text-xs font-medium text-muted-foreground hover:text-foreground hover:bg-secondary/60 transition-all duration-200 mt-1"
                >
                  <Plus className="w-3 h-3" strokeWidth={1.5} />
                  新建标签
                </button>
              )}
            </>
          )}
        </div>
      )}
    </div>
  )
}
