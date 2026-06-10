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

  useEffect(() => {
    if (article) {
      // Small delay to trigger enter animation
      requestAnimationFrame(() => setIsVisible(true))
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
          {article.tags.length > 0 && (
            <div className="flex items-center gap-1.5 mb-5 flex-wrap">
              {article.tags.map((tag) => (
                <span
                  key={tag.id}
                  className="px-2 py-0.5 rounded-md bg-secondary text-xs text-muted-foreground font-medium"
                >
                  {tag.name}
                </span>
              ))}
            </div>
          )}

          {/* Summary box */}
          <div className="p-4 rounded-xl bg-accent/30 border border-accent/20 mb-6">
            <p className="text-sm text-accent-foreground/90 leading-relaxed">
              {article.summary}
            </p>
          </div>

          {/* Content */}
          {article.content ? (
            <div
              className="prose prose-sm dark:prose-invert max-w-none
                prose-headings:text-[15px] prose-headings:font-semibold prose-headings:tracking-tight
                prose-p:text-muted-foreground prose-p:leading-relaxed
                prose-a:text-chart-1 prose-a:no-underline hover:prose-a:underline
                prose-strong:text-foreground
                prose-ul:text-muted-foreground prose-ol:text-muted-foreground"
              dangerouslySetInnerHTML={{ __html: article.content }}
            />
          ) : (
            <div className="p-6 rounded-xl bg-secondary/40 text-center">
              <p className="text-sm text-muted-foreground">完整内容加载中...</p>
            </div>
          )}
        </div>

        {/* Action bar */}
        <div className="flex items-center justify-between px-5 py-3 border-t border-border/60 shrink-0 gap-2">
          <div className="flex items-center gap-1">
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
