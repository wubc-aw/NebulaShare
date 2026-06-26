"use client"

import { Star } from "lucide-react"
import { cn } from "@/lib/utils"

export interface TagItem {
  id: number
  name: string
  color: string
}

export interface Article {
  id: number
  title: string
  summary: string
  deep_summary?: string
  content?: string
  source: string
  category: string
  tags: TagItem[]
  author?: string
  date: string
  url?: string
  is_read: boolean
  is_starred: boolean
  is_archived: boolean
}

const categoryDotColor: Record<string, string> = {
  AI: "bg-chart-1",
  互联网: "bg-chart-2",
  金融: "bg-chart-3",
  创投: "bg-chart-5",
  工具: "bg-chart-4",
  阅读: "bg-muted-foreground",
}

interface ArticleListItemProps {
  article: Article
  selected: boolean
  onClick: () => void
  onToggleStar: (e: React.MouseEvent) => void
}

export function ArticleListItem({ article, selected, onClick, onToggleStar }: ArticleListItemProps) {
  const dotColor = categoryDotColor[article.category] || "bg-muted-foreground"

  return (
    <button
      onClick={onClick}
      className={cn(
        "relative w-full px-4 py-4 text-left transition-all duration-200 group rounded-xl",
        selected
          ? "bg-secondary/60 shadow-[var(--shadow-card)]"
          : "hover:bg-secondary/40"
      )}
    >
      {/* Selected indicator */}
      {selected && (
        <span className="absolute left-0 top-3 bottom-3 w-0.5 rounded-full bg-chart-1" />
      )}

      <div className="flex items-start gap-3">
        {/* Unread dot */}
        <div className="pt-1.5 shrink-0">
          {!article.is_read ? (
            <span className="block w-2 h-2 rounded-full bg-chart-1 shadow-[0_0_6px_rgba(59,130,246,0.5)]" />
          ) : (
            <span className="block w-2 h-2 rounded-full bg-transparent" />
          )}
        </div>

        <div className="flex-1 min-w-0">
          {/* Meta row: source, category, tags */}
          <div className="flex items-center gap-2 mb-2 flex-wrap">
            <span className="text-xs text-muted-foreground font-medium">{article.source}</span>
            <span className="text-border">·</span>
            <span className="inline-flex items-center gap-1">
              <span className={cn("w-1.5 h-1.5 rounded-full", dotColor)} />
              <span className="text-xs text-muted-foreground">{article.category}</span>
            </span>
            {(article.tags || []).map((tag) => (
              <span
                key={tag.id}
                className="px-1.5 py-0.5 rounded-md bg-secondary/80 text-[10px] text-muted-foreground font-medium"
              >
                {tag.name}
              </span>
            ))}
          </div>

          {/* Title */}
          <h3
            className={cn(
              "text-[15px] leading-snug mb-1.5 line-clamp-1",
              !article.is_read ? "font-semibold text-foreground" : "font-medium text-foreground/80"
            )}
          >
            {article.title}
          </h3>

          {/* Summary */}
          <p className="text-sm text-muted-foreground line-clamp-2 leading-relaxed">
            {article.summary}
          </p>
        </div>

        {/* Right side: date + star */}
        <div className="flex flex-col items-end gap-2 shrink-0 pt-0.5">
          <span className="text-xs text-muted-foreground font-mono whitespace-nowrap">
            {article.date}
          </span>
          <button
            onClick={onToggleStar}
            className={cn(
              "p-1.5 rounded-lg transition-all duration-200 opacity-0 group-hover:opacity-100",
              article.is_starred
                ? "opacity-100 text-chart-4 hover:text-chart-4/80"
                : "text-muted-foreground hover:text-chart-4 hover:bg-chart-4/10"
            )}
            title={article.is_starred ? "取消收藏" : "收藏"}
          >
            <Star
              className="w-3.5 h-3.5"
              strokeWidth={1.5}
              fill={article.is_starred ? "currentColor" : "none"}
            />
          </button>
        </div>
      </div>
    </button>
  )
}
