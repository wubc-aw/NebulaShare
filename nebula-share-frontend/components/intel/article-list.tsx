"use client"

import { Newspaper } from "lucide-react"
import { ArticleListItem, type Article } from "./article-list-item"

interface ArticleListProps {
  articles: Article[]
  selectedId: string | null
  onSelect: (article: Article) => void
  onToggleStar: (articleId: string) => void
}

export function ArticleList({ articles, selectedId, onSelect, onToggleStar }: ArticleListProps) {
  if (articles.length === 0) {
    return (
      <div className="flex-1 flex items-center justify-center min-h-[200px]">
        <div className="text-center">
          <Newspaper className="w-10 h-10 text-muted-foreground/40 mx-auto mb-3" strokeWidth={1.5} />
          <p className="text-sm text-muted-foreground">暂无文章</p>
        </div>
      </div>
    )
  }

  return (
    <div className="flex-1 overflow-auto space-y-1 cascade">
      {articles.map((article) => (
        <ArticleListItem
          key={article.id}
          article={article}
          selected={selectedId === article.id}
          onClick={() => onSelect(article)}
          onToggleStar={(e) => {
            e.stopPropagation()
            onToggleStar(article.id)
          }}
        />
      ))}
    </div>
  )
}
