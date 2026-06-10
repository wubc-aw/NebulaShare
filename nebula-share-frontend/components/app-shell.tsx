"use client"

import { usePathname } from "next/navigation"
import Link from "next/link"
import { useEffect } from "react"
import { HostStatusBar } from "@/components/host-status-bar"
import { ThemeToggle } from "@/components/theme-toggle"
import { cn } from "@/lib/utils"
import {
  FolderOpen,
  Network,
  Lightbulb,
  History,
  GitBranch,
  Home,
  Hexagon,
  Cpu,
  Wrench,
} from "lucide-react"

export type Zone = "files" | "network" | "intelligence" | "history" | "knowledge" | "sdk" | "mcp"

const navItems = [
  { id: "home" as const, label: "主页", icon: Home, href: "/", shortcut: undefined },
  { id: "files" as const, label: "文件中心", icon: FolderOpen, href: "/files", shortcut: "1" },
  { id: "network" as const, label: "网络枢纽", icon: Network, href: "/network", shortcut: "2" },
  { id: "intelligence" as const, label: "情报站", icon: Lightbulb, href: "/intel", shortcut: "3" },
  { id: "history" as const, label: "Claude 历史", icon: History, href: "/claude", shortcut: "4" },
  { id: "knowledge" as const, label: "Cloud历史知识图谱", icon: GitBranch, href: "/knowledge", shortcut: "5" },
  { id: "sdk" as const, label: "SDK知识图谱", icon: Cpu, href: "/knowledge/sdk", shortcut: "6" },
  { id: "mcp" as const, label: "MCP工具", icon: Wrench, href: "/mcp", shortcut: "7" },
]

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname()

  const isActive = (href: string) => {
    if (href === "/") return pathname === "/"
    return pathname.startsWith(href)
  }

  // Keyboard shortcuts ⌘1-5 for zone pages
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.metaKey || e.ctrlKey) {
        const zoneItem = navItems.find((n) => n.shortcut === e.key && n.id !== "home")
        if (zoneItem) {
          e.preventDefault()
          window.location.href = zoneItem.href
        }
      }
    }
    window.addEventListener("keydown", handleKeyDown)
    return () => window.removeEventListener("keydown", handleKeyDown)
  }, [])

  return (
    <div className="min-h-screen flex bg-background">
      {/* ─── Sidebar ─────────────────────────────── */}
      <aside className="w-[200px] shrink-0 flex flex-col bg-sidebar border-r border-sidebar-border/60">
        {/* Logo */}
        <div className="px-5 py-5 flex items-center gap-3">
          <div className="w-9 h-9 rounded-xl bg-foreground flex items-center justify-center shadow-sm shrink-0">
            <Hexagon className="w-5 h-5 text-background" strokeWidth={2} />
          </div>
          <span className="text-base font-semibold tracking-tight">Nebula</span>
        </div>

        {/* Navigation */}
        <nav className="flex-1 px-3 py-2 space-y-0.5">
          {navItems.map((item) => {
            const Icon = item.icon
            const active = isActive(item.href)
            return (
              <Link
                key={item.id}
                href={item.href}
                className={cn(
                  "flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-all duration-200 group relative",
                  active
                    ? "text-sidebar-primary-foreground bg-sidebar-primary/10"
                    : "text-sidebar-foreground/70 hover:text-sidebar-foreground hover:bg-sidebar-accent/40"
                )}
              >
                {/* Active indicator bar */}
                {active && (
                  <span className="absolute left-0 top-1/2 -translate-y-1/2 w-[3px] h-5 rounded-r-full bg-gradient-to-b from-primary to-chart-2" />
                )}
                <Icon
                  className={cn(
                    "w-[18px] h-[18px] shrink-0 transition-colors",
                    active ? "text-primary" : "text-sidebar-foreground/50 group-hover:text-sidebar-foreground/80"
                  )}
                  strokeWidth={1.5}
                />
                <span className="flex-1">{item.label}</span>
                {item.shortcut && (
                  <kbd className="hidden text-[10px] font-mono text-sidebar-foreground/40 group-hover:text-sidebar-foreground/60 px-1 py-0.5 rounded bg-sidebar-accent/30">
                    ⌘{item.shortcut}
                  </kbd>
                )}
              </Link>
            )
          })}
        </nav>

        {/* Bottom cluster */}
        <div className="px-4 py-4 border-t border-sidebar-border/40 space-y-3">
          <div className="flex items-center gap-3">
            <ThemeToggle />
            <span className="text-xs text-sidebar-foreground/50">主题</span>
          </div>
          <div className="flex items-center gap-3">
            <div className="relative w-8 h-8 rounded-full bg-sidebar-accent flex items-center justify-center text-sidebar-accent-foreground font-bold text-[10px] shrink-0">
              AW
              <span className="absolute -bottom-0.5 -right-0.5 w-2.5 h-2.5 rounded-full bg-success border-2 border-sidebar" />
            </div>
            <div className="min-w-0">
              <p className="text-sm font-medium leading-none truncate">AW</p>
              <p className="text-[11px] text-sidebar-foreground/50 mt-0.5">管理员</p>
            </div>
          </div>
        </div>
      </aside>

      {/* ─── Main area ───────────────────────────── */}
      <div className="flex-1 flex flex-col min-w-0">
        <HostStatusBar />
        <main className="flex-1 overflow-auto">
          {children}
        </main>
        <footer className="px-6 py-2.5 flex items-center justify-between text-[11px] text-muted-foreground border-t border-border/40">
          <div className="flex items-center gap-2">
            <span className="font-medium">Nebula v2.0</span>
            <span className="opacity-40">·</span>
            <span className="opacity-70">Raspberry Pi 4B</span>
          </div>
          <div className="flex items-center gap-1.5">
            <span className="w-1.5 h-1.5 rounded-full bg-success animate-pulse-soft" />
            <span>系统正常</span>
          </div>
        </footer>
      </div>
    </div>
  )
}
