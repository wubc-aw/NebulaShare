"use client"

import { cn } from "@/lib/utils"
import { FolderOpen, Network, Lightbulb, History, GitBranch } from "lucide-react"

export type Zone = "files" | "network" | "intelligence" | "history" | "knowledge"

interface ZoneNavigationProps {
  activeZone: Zone
  onZoneChange: (zone: Zone) => void
}

const zones = [
  { id: "files" as const, label: "文件中心", icon: FolderOpen, shortcut: "1" },
  { id: "network" as const, label: "网络枢纽", icon: Network, shortcut: "2" },
  { id: "intelligence" as const, label: "情报站", icon: Lightbulb, shortcut: "3" },
  { id: "history" as const, label: "Claude 历史", icon: History, shortcut: "4" },
  { id: "knowledge" as const, label: "知识图谱", icon: GitBranch, shortcut: "5" },
]

export function ZoneNavigation({ activeZone, onZoneChange }: ZoneNavigationProps) {
  const activeIndex = zones.findIndex((z) => z.id === activeZone)

  return (
    <nav className="relative flex items-center gap-0.5 rounded-xl bg-secondary/60 p-1">
      {/* Sliding active surface — subtle, near-grayscale */}
      <div
        className="absolute top-1 bottom-1 rounded-lg bg-card shadow-card transition-[left,width] duration-[400ms]"
        style={{
          left: `calc(${activeIndex} * (100% - 0.5rem) / ${zones.length} + 0.25rem)`,
          width: `calc((100% - 0.5rem) / ${zones.length})`,
          transitionTimingFunction: "cubic-bezier(0.25, 0.1, 0.25, 1)",
        }}
      />

      {zones.map((zone) => {
        const Icon = zone.icon
        const isActive = activeZone === zone.id
        return (
          <button
            key={zone.id}
            onClick={() => onZoneChange(zone.id)}
            className={cn(
              "relative z-10 flex flex-1 items-center justify-center gap-2 px-4 py-2 rounded-lg transition-colors duration-300",
              isActive ? "text-foreground" : "text-muted-foreground hover:text-foreground",
            )}
          >
            <Icon className="w-[18px] h-[18px]" strokeWidth={1.5} />
            <span className="text-sm font-medium hidden sm:inline whitespace-nowrap">{zone.label}</span>
            <kbd
              className={cn(
                "hidden md:inline-flex items-center px-1.5 py-0.5 rounded text-xs font-mono transition-colors",
                isActive ? "text-muted-foreground" : "text-muted-foreground/70",
              )}
            >
              ⌘{zone.shortcut}
            </kbd>
          </button>
        )
      })}
    </nav>
  )
}
