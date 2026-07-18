"use client"

import { usePathname } from "next/navigation"
import Link from "next/link"
import { useEffect, useState } from "react"
import { HostStatusBar } from "@/components/host-status-bar"
import { ThemeSwitcher } from "@/components/theme-switcher"
import { ThemeBackdrop } from "@/components/theme-backdrop"
import { cn } from "@/lib/utils"
import {
  FolderOpen,
  Network,
  Lightbulb,
  History,
  GitBranch,
  Home,
  Hexagon,
  Wrench,
  BookOpen,
  ChevronDown,
  Menu,
  Terminal,
  X,
} from "lucide-react"

export type Zone = "files" | "network" | "intelligence" | "history" | "knowledge" | "sdk" | "mcp"

interface NavItem {
  id: string
  label: string
  icon: React.ElementType
  href: string
  shortcut?: string
  external?: boolean
  children?: { id: string; label: string; href: string }[]
}

// agent-terminal (SoA-Web) 服务端口，部署端口变化时同步调整；
// 服务监听 0.0.0.0，入口跟随当前访问 Nebula 的主机名（局域网/ Tailscale 各自直连）
const TERMINAL_PORT = 7332

function getTerminalUrl() {
  if (typeof window === "undefined") return `http://127.0.0.1:${TERMINAL_PORT}`
  return `${window.location.protocol}//${window.location.hostname}:${TERMINAL_PORT}`
}

const navItems: NavItem[] = [
  { id: "home", label: "主页", icon: Home, href: "/", shortcut: undefined },
  { id: "files", label: "文件中心", icon: FolderOpen, href: "/files", shortcut: "1" },
  { id: "network", label: "网络枢纽", icon: Network, href: "/network", shortcut: "2" },
  { id: "intelligence", label: "情报站", icon: Lightbulb, href: "/intel", shortcut: "3" },
  { id: "history", label: "Claude 历史", icon: History, href: "/claude", shortcut: "4" },
  {
    id: "knowledge",
    label: "知识图谱",
    icon: GitBranch,
    href: "/knowledge",
    shortcut: "5",
    children: [
      { id: "knowledge-cloud", label: "Cloud历史", href: "/knowledge" },
      { id: "knowledge-sdk", label: "SDK", href: "/knowledge/sdk" },
    ],
  },
  { id: "mcp", label: "MCP工具", icon: Wrench, href: "/mcp", shortcut: "6" },
  { id: "skills", label: "Skill 中心", icon: BookOpen, href: "/skills", shortcut: "7" },
  { id: "terminal", label: "终端", icon: Terminal, href: "/terminal", shortcut: "8", external: true },
]

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname()
  const [expandedGroups, setExpandedGroups] = useState<Record<string, boolean>>({
    knowledge: true,
  })
  const [mobileOpen, setMobileOpen] = useState(false)
  // 终端入口地址：初始值与预渲染保持一致，挂载后替换为当前访问主机名
  const [terminalHref, setTerminalHref] = useState(`http://127.0.0.1:${TERMINAL_PORT}`)

  const isActive = (href: string) => {
    if (href === "/") return pathname === "/"
    return pathname.startsWith(href)
  }

  const toggleGroup = (id: string) => {
    setExpandedGroups((prev) => ({ ...prev, [id]: !prev[id] }))
  }

  // Close mobile sidebar on route change
  useEffect(() => {
    setMobileOpen(false)
  }, [pathname])

  // Prevent body scroll when mobile sidebar is open
  useEffect(() => {
    if (mobileOpen) {
      document.body.style.overflow = "hidden"
    } else {
      document.body.style.overflow = ""
    }
    return () => {
      document.body.style.overflow = ""
    }
  }, [mobileOpen])

  // Resolve terminal URL against the host the page was reached on
  useEffect(() => {
    setTerminalHref(getTerminalUrl())
  }, [])

  // Keyboard shortcuts ⌘1-8 for zone pages
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.metaKey || e.ctrlKey) {
        const zoneItem = navItems.find((n) => n.shortcut === e.key && n.id !== "home")
        if (zoneItem) {
          e.preventDefault()
          window.location.href = zoneItem.external ? getTerminalUrl() : zoneItem.href
        }
      }
    }
    window.addEventListener("keydown", handleKeyDown)
    return () => window.removeEventListener("keydown", handleKeyDown)
  }, [])

  return (
    <div className="min-h-screen flex bg-background app-shell-root">
      <ThemeBackdrop />
      {/* ─── Mobile overlay ───────────────────────── */}
      {mobileOpen && (
        <div
          className="fixed inset-0 bg-black/50 backdrop-blur-sm z-40 lg:hidden"
          onClick={() => setMobileOpen(false)}
        />
      )}

      {/* ─── Sidebar ─────────────────────────────── */}
      <aside
        className={cn(
          "fixed lg:static inset-y-0 left-0 z-50 w-[240px] lg:w-[200px] shrink-0 flex flex-col bg-sidebar border-r border-sidebar-border/60 app-sidebar",
          "transition-transform duration-300 ease-out",
          mobileOpen ? "translate-x-0" : "-translate-x-full lg:translate-x-0"
        )}
      >
        {/* Logo */}
        <div className="px-5 py-5 flex items-center gap-3">
          <div className="w-9 h-9 rounded-xl bg-foreground flex items-center justify-center shadow-sm shrink-0">
            <Hexagon className="w-5 h-5 text-background" strokeWidth={2} />
          </div>
          <span className="text-base font-semibold tracking-tight brand-name">Nebula</span>
          <button
            onClick={() => setMobileOpen(false)}
            className="lg:hidden ml-auto p-1.5 rounded-lg hover:bg-sidebar-accent/40 text-sidebar-foreground/70"
          >
            <X className="w-4 h-4" strokeWidth={1.5} />
          </button>
        </div>

        {/* Navigation */}
        <nav className="flex-1 px-3 py-2 space-y-0.5 overflow-auto">
          {navItems.map((item) => {
            const Icon = item.icon
            const active = item.external ? false : isActive(item.href)
            const hasChildren = !!item.children?.length
            const isExpanded = expandedGroups[item.id]

            return (
              <div key={item.id}>
                {/* Parent item */}
                {hasChildren ? (
                  <button
                    onClick={() => toggleGroup(item.id)}
                    className={cn(
                      "w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-all duration-200 group relative",
                      active
                        ? "text-sidebar-primary-foreground bg-sidebar-primary/10"
                        : "text-sidebar-foreground/70 hover:text-sidebar-foreground hover:bg-sidebar-accent/40"
                    )}
                  >
                    {/* Active indicator bar */}
                    {active && (
                      <span className="absolute left-0 top-1/2 -translate-y-1/2 w-[3px] h-5 rounded-r-full bg-gradient-to-b from-primary to-chart-2 active-bar" />
                    )}
                    <Icon
                      className={cn(
                        "w-[18px] h-[18px] shrink-0 transition-colors",
                        active ? "text-primary" : "text-sidebar-foreground/50 group-hover:text-sidebar-foreground/80"
                      )}
                      strokeWidth={1.5}
                    />
                    <span className="flex-1 text-left nav-label">{item.label}</span>
                    <ChevronDown
                      className={cn(
                        "w-3.5 h-3.5 text-sidebar-foreground/40 transition-transform duration-200",
                        !isExpanded && "-rotate-90"
                      )}
                      strokeWidth={1.5}
                    />
                    {item.shortcut && (
                      <kbd className="hidden text-[10px] font-mono text-sidebar-foreground/40 group-hover:text-sidebar-foreground/60 px-1 py-0.5 rounded bg-sidebar-accent/30">
                        ⌘{item.shortcut}
                      </kbd>
                    )}
                  </button>
                ) : item.external ? (
                  <a
                    href={terminalHref}
                    className={cn(
                      "flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-all duration-200 group relative",
                      active
                        ? "text-sidebar-primary-foreground bg-sidebar-primary/10"
                        : "text-sidebar-foreground/70 hover:text-sidebar-foreground hover:bg-sidebar-accent/40"
                    )}
                  >
                    <Icon
                      className={cn(
                        "w-[18px] h-[18px] shrink-0 transition-colors",
                        active ? "text-primary" : "text-sidebar-foreground/50 group-hover:text-sidebar-foreground/80"
                      )}
                      strokeWidth={1.5}
                    />
                    <span className="flex-1 nav-label">{item.label}</span>
                    {item.shortcut && (
                      <kbd className="hidden text-[10px] font-mono text-sidebar-foreground/40 group-hover:text-sidebar-foreground/60 px-1 py-0.5 rounded bg-sidebar-accent/30">
                        ⌘{item.shortcut}
                      </kbd>
                    )}
                  </a>
                ) : (
                  <Link
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
                      <span className="absolute left-0 top-1/2 -translate-y-1/2 w-[3px] h-5 rounded-r-full bg-gradient-to-b from-primary to-chart-2 active-bar" />
                    )}
                    <Icon
                      className={cn(
                        "w-[18px] h-[18px] shrink-0 transition-colors",
                        active ? "text-primary" : "text-sidebar-foreground/50 group-hover:text-sidebar-foreground/80"
                      )}
                      strokeWidth={1.5}
                    />
                    <span className="flex-1 nav-label">{item.label}</span>
                    {item.shortcut && (
                      <kbd className="hidden text-[10px] font-mono text-sidebar-foreground/40 group-hover:text-sidebar-foreground/60 px-1 py-0.5 rounded bg-sidebar-accent/30">
                        ⌘{item.shortcut}
                      </kbd>
                    )}
                  </Link>
                )}

                {/* Children */}
                {hasChildren && isExpanded && (
                  <div className="ml-4 mt-0.5 space-y-0.5 border-l border-sidebar-border/30 pl-2">
                    {item.children?.map((child) => {
                      const childActive = pathname === child.href || (child.href !== "/" && pathname.startsWith(child.href))
                      return (
                        <Link
                          key={child.id}
                          href={child.href}
                          className={cn(
                            "flex items-center gap-2 px-3 py-2 rounded-lg text-sm transition-all duration-200",
                            childActive
                              ? "text-sidebar-primary-foreground bg-sidebar-primary/10 font-medium"
                              : "text-sidebar-foreground/60 hover:text-sidebar-foreground hover:bg-sidebar-accent/30"
                          )}
                        >
                          <span className="w-1.5 h-1.5 rounded-full shrink-0 bg-sidebar-foreground/30" />
                          <span>{child.label}</span>
                        </Link>
                      )
                    })}
                  </div>
                )}
              </div>
            )
          })}
        </nav>

        {/* Bottom cluster */}
        <div className="px-4 py-4 border-t border-sidebar-border/40 space-y-3">
          <div>
            <p className="text-[10px] text-sidebar-foreground/40 mb-1.5 px-0.5">界面风格</p>
            <ThemeSwitcher />
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
      <div className="flex-1 flex flex-col min-w-0 min-h-screen">
        {/* Mobile header */}
        <div className="lg:hidden flex items-center justify-between px-4 py-3 border-b border-border/40 bg-background/80 backdrop-blur-sm sticky top-0 z-30">
          <button
            onClick={() => setMobileOpen(true)}
            className="p-2 -ml-2 rounded-lg hover:bg-secondary transition-colors"
            aria-label="打开菜单"
          >
            <Menu className="w-5 h-5" strokeWidth={1.5} />
          </button>
          <div className="flex items-center gap-2">
            <div className="w-7 h-7 rounded-lg bg-foreground flex items-center justify-center">
              <Hexagon className="w-4 h-4 text-background" strokeWidth={2} />
            </div>
            <span className="text-sm font-semibold tracking-tight">Nebula</span>
          </div>
          <div className="w-9" />
        </div>

        <HostStatusBar />
        <main className="flex-1 overflow-auto">
          {children}
        </main>
        <footer className="px-4 sm:px-6 py-2.5 flex flex-col sm:flex-row items-center justify-between gap-1 text-[11px] text-muted-foreground border-t border-border/40">
          <div className="flex items-center gap-2">
            <span className="font-medium">Nebula v2.0</span>
            <span className="opacity-40 hidden sm:inline">·</span>
            <span className="opacity-70 hidden sm:inline">Raspberry Pi 4B</span>
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
