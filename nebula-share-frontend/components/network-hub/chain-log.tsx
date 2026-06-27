"use client"

import { useState, useEffect, useCallback, useRef } from "react"
import { cn } from "@/lib/utils"
import { Activity, Trash2, RefreshCw } from "lucide-react"

interface ChainLogItem {
  id: string
  time: string
  src: string
  host: string
  port: string
  rule: string
  rule_payload: string
  chain: string
}

interface RawConnection {
  src: string
  host: string
  port: string
  rule: string
  rule_payload: string
  chain: string
  start: string
}

function makeKey(item: ChainLogItem) {
  return `${item.src}::${item.host}:${item.port}`
}

function formatTime(iso: string) {
  const d = new Date(iso)
  return d.toLocaleTimeString("zh-CN", { hour12: false })
}

export function ChainLog({ className }: { className?: string }) {
  const [items, setItems] = useState<ChainLogItem[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const seenRef = useRef<Record<string, string>>({})

  const fetchConnections = useCallback(async () => {
    try {
      const res = await fetch("/api/mihomo/connections/recent?limit=50")
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      const data = await res.json()
      if (!data.ok) throw new Error("Backend returned ok: false")

      const incoming: RawConnection[] = data.items || []
      const updates: ChainLogItem[] = []

      for (const c of incoming) {
        const item: ChainLogItem = {
          id: `${c.src}-${c.host}-${c.port}-${Date.now()}`,
          time: formatTime(c.start || new Date().toISOString()),
          src: c.src,
          host: c.host,
          port: c.port,
          rule: c.rule || "-",
          rule_payload: c.rule_payload || "",
          chain: c.chain || "DIRECT",
        }
        const key = makeKey(item)
        const previous = seenRef.current[key]
        if (previous !== item.chain) {
          seenRef.current[key] = item.chain
          updates.push(item)
        }
      }

      if (updates.length > 0) {
        setItems((prev) => {
          const map = new Map(prev.map((i) => [makeKey(i), i]))
          for (const u of updates) {
            map.set(makeKey(u), u)
          }
          return Array.from(map.values()).sort((a, b) => b.id.localeCompare(a.id)).slice(0, 100)
        })
      }
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to fetch connections")
    }
  }, [])

  const handleRefresh = async () => {
    setLoading(true)
    await fetchConnections()
    setLoading(false)
  }

  const handleClear = () => {
    setItems([])
    seenRef.current = {}
  }

  useEffect(() => {
    fetchConnections()
    const interval = setInterval(fetchConnections, 3000)
    return () => clearInterval(interval)
  }, [fetchConnections])

  return (
    <div className={cn("card-premium p-4", className)}>
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <Activity className="w-4 h-4 text-muted-foreground" strokeWidth={1.5} />
          <h3 className="text-sm font-semibold">链路日志</h3>
          <span className="text-xs text-muted-foreground font-mono bg-secondary/50 px-2 py-0.5 rounded-md">
            {items.length}
          </span>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={handleClear}
            className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg bg-secondary/50 text-xs text-muted-foreground hover:text-foreground transition-colors"
          >
            <Trash2 className="w-3 h-3" strokeWidth={1.5} />
            清空
          </button>
          <button
            onClick={handleRefresh}
            disabled={loading}
            className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg bg-secondary/50 text-xs text-muted-foreground hover:text-foreground transition-colors disabled:opacity-50"
          >
            <RefreshCw className={cn("w-3 h-3", loading && "animate-spin")} strokeWidth={1.5} />
            刷新
          </button>
        </div>
      </div>

      {error && (
        <p className="text-sm text-destructive mb-3">{error}</p>
      )}

      {items.length === 0 ? (
        <p className="text-sm text-muted-foreground">暂无链路变化记录</p>
      ) : (
        <div className="flex flex-col gap-2 max-h-[360px] overflow-auto pr-1">
          {items.map((item) => (
            <div
              key={item.id}
              className="flex flex-col gap-1 px-3 py-2 rounded-xl bg-secondary/20"
            >
              <div className="flex items-center justify-between gap-3">
                <div className="flex items-center gap-2 min-w-0">
                  <span className="text-xs text-muted-foreground font-mono shrink-0">{item.time}</span>
                  <span className="text-xs font-medium truncate">{item.host}:{item.port}</span>
                </div>
                <span className="text-[11px] text-muted-foreground font-mono shrink-0">{item.src}</span>
              </div>
              <div className="flex items-center justify-between gap-3">
                <span className="text-xs text-muted-foreground font-mono truncate">
                  {item.rule_payload ? `${item.rule} / ${item.rule_payload}` : item.rule}
                </span>
                <span className={cn(
                  "text-xs font-mono shrink-0",
                  item.chain.includes("DIRECT") ? "text-success" : "text-primary"
                )}>
                  {item.chain}
                </span>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
