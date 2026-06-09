"use client"

import { useState, useEffect } from "react"
import { HostStatusBar } from "@/components/host-status-bar"
import { ZoneNavigation, type Zone } from "@/components/zone-navigation"
import { FileHub } from "@/components/file-hub"
import { NetworkHub } from "@/components/network-hub"
import { IntelligenceCenter } from "@/components/intelligence-center"
import { ClaudeHistory } from "@/components/claude-history"
import { KnowledgeGraph } from "@/components/knowledge-graph"
import { ThemeToggle } from "@/components/theme-toggle"

function KnowledgeGraphWrapper() {
  const [data, setData] = useState<{ nodes: any[]; edges: any[] } | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    fetch("/api/knowledge/graph")
      .then((r) => r.json())
      .then((d) => {
        setData(d)
        setLoading(false)
      })
      .catch(() => setLoading(false))
  }, [])

  if (loading) {
    return (
      <div className="h-full flex items-center justify-center">
        <div className="w-8 h-8 border-2 border-primary/30 border-t-primary rounded-full animate-spin" />
      </div>
    )
  }

  if (!data || !data.nodes.length) {
    return (
      <div className="h-full flex items-center justify-center">
        <p className="text-sm text-muted-foreground">暂无知识图谱数据</p>
      </div>
    )
  }

  return <KnowledgeGraph data={data} />
}

export default function NebulaShareDashboard() {
  const [activeZone, setActiveZone] = useState<Zone>("files")

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.metaKey || e.ctrlKey) {
        switch (e.key) {
          case "1":
            e.preventDefault()
            setActiveZone("files")
            break
          case "2":
            e.preventDefault()
            setActiveZone("network")
            break
          case "3":
            e.preventDefault()
            setActiveZone("intelligence")
            break
          case "4":
            e.preventDefault()
            setActiveZone("history")
            break
          case "5":
            e.preventDefault()
            setActiveZone("knowledge")
            break
        }
      }
    }

    window.addEventListener("keydown", handleKeyDown)
    return () => window.removeEventListener("keydown", handleKeyDown)
  }, [])

  return (
    <div className="min-h-screen flex flex-col bg-background">
      {/* Persistent Host Status Bar */}
      <HostStatusBar />

      {/* Main Content */}
      <main className="flex-1 flex flex-col">
        {/* Header */}
        <header className="px-6 pt-6 pb-4 flex items-center justify-between gap-4">
          <div className="flex items-center gap-3 shrink-0">
            <div className="w-10 h-10 rounded-[0.875rem] bg-foreground flex items-center justify-center shadow-sm">
              <span className="text-background font-bold text-base">N</span>
            </div>
            <div className="hidden lg:block">
              <h1 className="text-lg font-semibold tracking-tight leading-none">NebulaShare</h1>
              <p className="text-sm text-muted-foreground mt-1">星云互传 · AW 的指挥中心</p>
            </div>
          </div>

          {/* Zone Navigation */}
          <ZoneNavigation activeZone={activeZone} onZoneChange={setActiveZone} />

          {/* Right cluster: theme toggle + user */}
          <div className="flex items-center gap-3 shrink-0">
            <ThemeToggle />
            <div className="w-px h-6 bg-border hidden sm:block" />
            <div className="text-right hidden sm:block">
              <p className="text-sm font-semibold leading-none">AW</p>
              <p className="text-xs text-muted-foreground mt-1">管理员</p>
            </div>
            <div className="relative w-9 h-9 rounded-full bg-secondary flex items-center justify-center text-secondary-foreground font-bold text-xs shadow-sm">
              AW
              <span className="absolute -bottom-0.5 -right-0.5 w-2.5 h-2.5 rounded-full bg-success border-2 border-card" />
            </div>
          </div>
        </header>

        {/* Zone Content */}
        <div className="flex-1 px-6 pb-6">
          <div className="h-full min-h-[calc(100vh-200px)] bg-card rounded-2xl p-5 sm:p-6 shadow-[var(--shadow-card)]">
            <div key={activeZone} className="animate-zone-in h-full">
              {activeZone === "files" && <FileHub />}
              {activeZone === "network" && <NetworkHub />}
              {activeZone === "intelligence" && <IntelligenceCenter />}
              {activeZone === "history" && <ClaudeHistory />}
              {activeZone === "knowledge" && <KnowledgeGraphWrapper />}
            </div>
          </div>
        </div>
      </main>

      {/* Footer */}
      <footer className="px-6 py-3 flex items-center justify-between text-xs text-muted-foreground">
        <div className="flex items-center gap-3">
          <span className="font-medium">NebulaShare v2.0</span>
          <span className="hidden sm:inline opacity-40">·</span>
          <span className="hidden sm:inline">Raspberry Pi 4B</span>
        </div>
        <div className="flex items-center gap-1.5">
          <span className="w-1.5 h-1.5 rounded-full bg-success animate-pulse-soft" />
          <span>系统正常</span>
        </div>
      </footer>
    </div>
  )
}
