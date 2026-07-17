"use client"

import { useEffect, useState } from "react"
import {
  X,
  Star,
  Check,
  CheckCheck,
  Archive,
  ExternalLink,
  BookOpen,
  Sparkles,
  Loader2,
} from "lucide-react"
import { cn } from "@/lib/utils"
import type { Article, TagItem } from "./article-list-item"
import { TagSelector } from "./tag-selector"

const categoryDotColor: Record<string, string> = {
  AI: "bg-chart-1",
  互联网: "bg-chart-2",
  金融: "bg-chart-3",
  创投: "bg-chart-5",
  工具: "bg-chart-4",
  阅读: "bg-muted-foreground",
}

interface ArticleReaderProps {
  article: Article | null
  onClose: () => void
  onUpdate: (articleId: string, updates: Partial<Article>) => void
}

export function ArticleReader({ article, onClose, onUpdate }: ArticleReaderProps) {
  const [isVisible, setIsVisible] = useState(false)
  const [deepSummary, setDeepSummary] = useState<string | null>(null)
  const [isGenerating, setIsGenerating] = useState(false)
  const [generateError, setGenerateError] = useState<string | null>(null)

  useEffect(() => {
    if (article) {
      requestAnimationFrame(() => setIsVisible(true))
      // Reset deep summary state when article changes
      setDeepSummary(article.deep_summary || null)
      setGenerateError(null)
    } else {
      setIsVisible(false)
    }
  }, [article?.id])

  if (!article) {
    return (
      <div className="hidden md:flex flex-1 items-center justify-center bg-secondary/20 rounded-xl min-w-0">
        <div className="text-center">
          <BookOpen className="w-10 h-10 text-muted-foreground/40 mx-auto mb-3" strokeWidth={1.5} />
          <p className="text-sm text-muted-foreground">选择一篇文章开始阅读</p>
        </div>
      </div>
    )
  }

  const dotColor = categoryDotColor[article.category] || "bg-muted-foreground"

  const handleToggleRead = () => {
    onUpdate(article.id, { is_read: !article.is_read })
  }

  const handleToggleStar = () => {
    onUpdate(article.id, { is_starred: !article.is_starred })
  }

  const handleArchive = () => {
    onUpdate(article.id, { is_archived: !article.is_archived })
  }

  const handleGenerateDeepSummary = async () => {
    setIsGenerating(true)
    setGenerateError(null)
    try {
      const resp = await fetch(`/api/intel/articles/${article.id}/summarize`, {
        method: "POST",
      })
      const data = await resp.json()
      if (!resp.ok) {
        setGenerateError(data.error || "生成失败")
      } else {
        setDeepSummary(data.deep_summary)
        // Update parent article state
        onUpdate(article.id, { deep_summary: data.deep_summary })
      }
    } catch (err) {
      setGenerateError(String(err))
    } finally {
      setIsGenerating(false)
    }
  }

  // Parse deep summary sections for structured rendering
  const parsedSections = parseDeepSummary(deepSummary)

  return (
    <div
      className={cn(
        "fixed inset-0 z-50 md:static md:z-auto md:flex md:flex-1 md:min-w-0",
        "bg-background/80 backdrop-blur-sm md:bg-transparent md:backdrop-blur-none"
      )}
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose()
      }}
    >
      <div
        className={cn(
          "absolute right-0 top-0 bottom-0 w-full max-w-xl md:relative md:w-auto md:max-w-none",
          "flex flex-col bg-card rounded-l-2xl md:rounded-xl shadow-[var(--shadow-pop)] md:shadow-[var(--shadow-card)]",
          "border-l border-border/60 md:border",
          "transition-transform duration-300 ease-out",
          isVisible ? "translate-x-0" : "translate-x-full md:translate-x-0"
        )}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-border/60 shrink-0">
          <div className="flex items-center gap-2.5 min-w-0">
            <span className={cn("w-2 h-2 rounded-full shrink-0", dotColor)} />
            <span className="text-sm text-muted-foreground truncate">{article.source}</span>
          </div>
          <button
            onClick={onClose}
            className="p-2 hover:bg-secondary rounded-lg transition-colors shrink-0 ml-2"
          >
            <X className="w-4 h-4 text-muted-foreground" strokeWidth={1.5} />
          </button>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-auto px-5 py-6">
          {/* Title */}
          <h1 className="text-xl font-semibold tracking-tight text-balance mb-4 leading-snug">
            {article.title}
          </h1>

          {/* Author + Date */}
          <div className="flex items-center gap-3 mb-4 text-sm text-muted-foreground">
            {article.author && <span>{article.author}</span>}
            {article.author && <span className="text-border">·</span>}
            <span className="font-mono">{article.date}</span>
          </div>

          {/* Tags */}
          {(article.tags || []).length > 0 && (
            <div className="flex items-center gap-1.5 mb-5 flex-wrap">
              {(article.tags || []).map((tag) => (
                <span
                  key={tag.id}
                  className="px-2 py-0.5 rounded-md bg-secondary text-xs text-muted-foreground font-medium"
                >
                  {tag.name}
                </span>
              ))}
            </div>
          )}

          {/* Deep Summary */}
          {deepSummary ? (
            <div className="space-y-5">
              {/* Original summary as a compact header */}
              {article.summary && (
                <div className="p-3 rounded-lg bg-accent/20 border border-accent/15">
                  <p className="text-sm text-accent-foreground/80 leading-relaxed">
                    {article.summary}
                  </p>
                </div>
              )}

              {/* Structured deep summary sections */}
              {parsedSections.map((section, idx) => (
                <div key={idx} className="space-y-2">
                  <h2 className="text-sm font-semibold text-foreground flex items-center gap-2">
                    <span className="w-1 h-4 rounded-full bg-chart-1" />
                    {section.title}
                  </h2>
                  <div className="text-sm text-muted-foreground leading-relaxed pl-3">
                    {section.isList ? (
                      <ul className="space-y-1.5">
                        {section.items.map((item, i) => (
                          <li key={i} className="flex gap-2">
                            <span className="text-chart-1 mt-1.5 shrink-0">•</span>
                            <span>{item}</span>
                          </li>
                        ))}
                      </ul>
                    ) : (
                      <div className="whitespace-pre-wrap">{section.content}</div>
                    )}
                  </div>
                </div>
              ))}
            </div>
          ) : (
            /* No deep summary yet — show original summary + generate button */
            <div className="space-y-5">
              {article.summary && (
                <div className="p-4 rounded-xl bg-accent/30 border border-accent/20">
                  <p className="text-sm text-accent-foreground/90 leading-relaxed">
                    {article.summary}
                  </p>
                </div>
              )}

              {/* Generate deep summary CTA */}
              <div className="p-5 rounded-xl bg-secondary/40 border border-border/40 text-center space-y-3">
                <Sparkles className="w-5 h-5 text-chart-1 mx-auto" strokeWidth={1.5} />
                <p className="text-sm text-muted-foreground">
                  使用 Kimi K2.7 生成深度分析
                </p>
                <button
                  onClick={handleGenerateDeepSummary}
                  disabled={isGenerating}
                  className={cn(
                    "inline-flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-all",
                    isGenerating
                      ? "bg-muted text-muted-foreground cursor-not-allowed"
                      : "bg-chart-1/15 text-chart-1 hover:bg-chart-1/20"
                  )}
                >
                  {isGenerating ? (
                    <>
                      <Loader2 className="w-3.5 h-3.5 animate-spin" />
                      生成中...
                    </>
                  ) : (
                    <>
                      <Sparkles className="w-3.5 h-3.5" />
                      生成深度总结
                    </>
                  )}
                </button>
                {generateError && (
                  <p className="text-xs text-destructive">{generateError}</p>
                )}
              </div>
            </div>
          )}
        </div>

        {/* Action bar */}
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between px-5 py-3 border-t border-border/60 shrink-0 gap-3">
          <div className="flex items-center gap-1 flex-wrap">
            <button
              onClick={handleToggleRead}
              className={cn(
                "inline-flex items-center gap-1.5 px-3 py-2 rounded-lg text-xs font-medium transition-all duration-200",
                article.is_read
                  ? "bg-secondary text-muted-foreground hover:bg-secondary/80"
                  : "bg-chart-1/15 text-chart-1 hover:bg-chart-1/20"
              )}
            >
              {article.is_read ? (
                <>
                  <CheckCheck className="w-3.5 h-3.5" strokeWidth={1.5} />
                  标记未读
                </>
              ) : (
                <>
                  <Check className="w-3.5 h-3.5" strokeWidth={1.5} />
                  标记已读
                </>
              )}
            </button>

            <button
              onClick={handleToggleStar}
              className={cn(
                "inline-flex items-center gap-1.5 px-3 py-2 rounded-lg text-xs font-medium transition-all duration-200",
                article.is_starred
                  ? "bg-chart-4/15 text-chart-4 hover:bg-chart-4/20"
                  : "bg-secondary text-muted-foreground hover:bg-secondary/80"
              )}
            >
              <Star
                className="w-3.5 h-3.5"
                strokeWidth={1.5}
                fill={article.is_starred ? "currentColor" : "none"}
              />
              {article.is_starred ? "取消收藏" : "收藏"}
            </button>

            <button
              onClick={handleArchive}
              className={cn(
                "inline-flex items-center gap-1.5 px-3 py-2 rounded-lg text-xs font-medium transition-all duration-200",
                article.is_archived
                  ? "bg-muted text-muted-foreground hover:bg-muted/80"
                  : "bg-secondary text-muted-foreground hover:bg-secondary/80"
              )}
            >
              <Archive className="w-3.5 h-3.5" strokeWidth={1.5} />
              {article.is_archived ? "已归档" : "归档"}
            </button>

            <TagSelector
              articleId={article.id}
              selectedTags={article.tags}
              onChange={(tags: TagItem[]) => onUpdate(article.id, { tags })}
            />
          </div>

          {article.url && (
            <a
              href={article.url}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1.5 px-3 py-2 rounded-lg text-xs font-medium bg-secondary text-muted-foreground hover:bg-secondary/80 transition-all duration-200 shrink-0"
            >
              <ExternalLink className="w-3.5 h-3.5" strokeWidth={1.5} />
              原文
            </a>
          )}
        </div>
      </div>
    </div>
  )
}

// ── Helpers ─────────────────────────────────────────────────────────

interface SummarySection {
  title: string
  content: string
  isList: boolean
  items: string[]
}

function parseDeepSummary(text: string | null): SummarySection[] {
  if (!text) return []

  const sections: SummarySection[] = []
  const lines = text.split("\n")
  let currentSection: SummarySection | null = null

  for (const line of lines) {
    const trimmed = line.trim()
    if (!trimmed) continue

    // Match markdown headers like ## 核心要点
    const headerMatch = trimmed.match(/^#{2,}\s+(.+)$/)
    if (headerMatch) {
      if (currentSection) {
        sections.push(currentSection)
      }
      currentSection = {
        title: headerMatch[1],
        content: "",
        isList: false,
        items: [],
      }
      continue
    }

    if (!currentSection) continue

    // Match bullet points
    const bulletMatch = trimmed.match(/^[-•*]\s+(.+)$/)
    if (bulletMatch) {
      currentSection.isList = true
      currentSection.items.push(bulletMatch[1])
      continue
    }

    // Match numbered lists
    const numberedMatch = trimmed.match(/^\d+\.\s+(.+)$/)
    if (numberedMatch) {
      currentSection.isList = true
      currentSection.items.push(numberedMatch[1])
      continue
    }

    // Regular content line
    if (currentSection.content) {
      currentSection.content += "\n" + trimmed
    } else {
      currentSection.content = trimmed
    }
  }

  if (currentSection) {
    sections.push(currentSection)
  }

  return sections
}
