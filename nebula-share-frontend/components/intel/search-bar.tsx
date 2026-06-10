"use client"

import { Search, X, Star, Check } from "lucide-react"
import { cn } from "@/lib/utils"

const categories = ["全部", "AI", "互联网", "金融", "创投", "工具", "阅读"]

interface SearchBarProps {
  search: string
  onSearchChange: (value: string) => void
  category: string
  onCategoryChange: (value: string) => void
  starredOnly: boolean
  onStarredChange: (value: boolean) => void
  unreadOnly: boolean
  onUnreadChange: (value: boolean) => void
}

export function SearchBar({
  search,
  onSearchChange,
  category,
  onCategoryChange,
  starredOnly,
  onStarredChange,
  unreadOnly,
  onUnreadChange,
}: SearchBarProps) {
  return (
    <div className="flex flex-col gap-3">
      {/* Search input */}
      <div className="relative">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" strokeWidth={1.5} />
        <input
          type="text"
          value={search}
          onChange={(e) => onSearchChange(e.target.value)}
          placeholder="搜索文章..."
          className={cn(
            "w-full pl-9 pr-9 py-2.5 rounded-xl text-sm",
            "bg-secondary/60 border border-border/60",
            "placeholder:text-muted-foreground/60",
            "focus:outline-none focus:ring-1 focus:ring-ring focus:border-ring/50",
            "transition-all duration-200"
          )}
        />
        {search && (
          <button
            onClick={() => onSearchChange("")}
            className="absolute right-3 top-1/2 -translate-y-1/2 p-0.5 rounded-md text-muted-foreground hover:text-foreground hover:bg-secondary transition-colors"
          >
            <X className="w-3.5 h-3.5" strokeWidth={1.5} />
          </button>
        )}
      </div>

      {/* Filters row */}
      <div className="flex items-center gap-2 flex-wrap">
        {/* Category pills */}
        <div className="flex items-center gap-1.5 flex-wrap">
          {categories.map((cat) => (
            <button
              key={cat}
              onClick={() => onCategoryChange(cat === "全部" ? "" : cat)}
              className={cn(
                "px-2.5 py-1 rounded-lg text-xs font-medium transition-all duration-200",
                (cat === "全部" ? category === "" : category === cat)
                  ? "bg-primary text-primary-foreground shadow-[0_0_12px_rgba(59,130,246,0.25)]"
                  : "bg-secondary/60 text-muted-foreground hover:bg-secondary hover:text-foreground"
              )}
            >
              {cat}
            </button>
          ))}
        </div>

        <div className="w-px h-4 bg-border/60 mx-1" />

        {/* Toggle buttons */}
        <button
          onClick={() => onStarredChange(!starredOnly)}
          className={cn(
            "inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-xs font-medium transition-all duration-200",
            starredOnly
              ? "bg-chart-4/15 text-chart-4 border border-chart-4/30"
              : "bg-secondary/60 text-muted-foreground hover:bg-secondary hover:text-foreground border border-transparent"
          )}
        >
          <Star className="w-3 h-3" strokeWidth={1.5} fill={starredOnly ? "currentColor" : "none"} />
          收藏
        </button>

        <button
          onClick={() => onUnreadChange(!unreadOnly)}
          className={cn(
            "inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-xs font-medium transition-all duration-200",
            unreadOnly
              ? "bg-chart-1/15 text-chart-1 border border-chart-1/30"
              : "bg-secondary/60 text-muted-foreground hover:bg-secondary hover:text-foreground border border-transparent"
          )}
        >
          <Check className="w-3 h-3" strokeWidth={1.5} />
          未读
        </button>
      </div>
    </div>
  )
}
