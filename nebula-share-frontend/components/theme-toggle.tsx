"use client"

import { useState, useEffect } from "react"
import { useTheme } from "next-themes"
import { Sun, Moon } from "lucide-react"
import { cn } from "@/lib/utils"

export function ThemeToggle({ className }: { className?: string }) {
  const { resolvedTheme, setTheme } = useTheme()
  const [mounted, setMounted] = useState(false)

  useEffect(() => setMounted(true), [])

  const isDark = resolvedTheme === "dark"

  return (
    <button
      type="button"
      aria-label={isDark ? "切换到浅色模式" : "切换到深色模式"}
      onClick={() => setTheme(isDark ? "light" : "dark")}
      className={cn(
        "relative inline-flex h-8 w-8 items-center justify-center rounded-lg",
        "text-muted-foreground transition-colors duration-200 hover:bg-accent hover:text-foreground",
        className,
      )}
    >
      {/* Render a stable icon until mounted to avoid hydration mismatch */}
      {mounted ? (
        isDark ? (
          <Moon className="h-[18px] w-[18px]" strokeWidth={1.5} />
        ) : (
          <Sun className="h-[18px] w-[18px]" strokeWidth={1.5} />
        )
      ) : (
        <Sun className="h-[18px] w-[18px]" strokeWidth={1.5} />
      )}
    </button>
  )
}
