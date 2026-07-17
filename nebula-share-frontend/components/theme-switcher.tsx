"use client"

import { useState, useEffect } from "react"
import { useTheme } from "next-themes"
import { cn } from "@/lib/utils"

const THEMES = [
  { id: "dark", label: "深空", swatch: "bg-[#3b82f6]" },
  { id: "light", label: "浅色", swatch: "bg-[#f5f5f7] border border-black/15" },
  {
    id: "vivid",
    label: "霓虹",
    swatch: "bg-gradient-to-br from-[#ff2e9a] via-[#8b5cf6] to-[#22d3ee]",
  },
  { id: "tron", label: "TRON", swatch: "bg-[#aacfd1]" },
] as const

export function ThemeSwitcher() {
  const { theme, setTheme } = useTheme()
  const [mounted, setMounted] = useState(false)

  useEffect(() => setMounted(true), [])

  return (
    <div className="grid grid-cols-4 gap-1">
      {THEMES.map((t) => {
        const active = mounted && theme === t.id
        return (
          <button
            key={t.id}
            type="button"
            title={`切换到「${t.label}」主题`}
            aria-pressed={active}
            onClick={() => setTheme(t.id)}
            className={cn(
              "flex flex-col items-center gap-1 rounded-md py-1.5 transition-all duration-200",
              active
                ? "bg-sidebar-accent/60 ring-1 ring-sidebar-ring"
                : "hover:bg-sidebar-accent/30"
            )}
          >
            <span className={cn("h-3.5 w-3.5 rounded-full shrink-0", t.swatch)} />
            <span
              className={cn(
                "text-[10px] leading-none",
                active ? "text-sidebar-foreground" : "text-sidebar-foreground/50"
              )}
            >
              {t.label}
            </span>
          </button>
        )
      })}
    </div>
  )
}
