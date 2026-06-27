"use client"

import { useState } from "react"
import { ChevronDown, Plus, Trash2, Save } from "lucide-react"
import { cn } from "@/lib/utils"

interface ClientRouteData {
  ip: string
  name: string
  primary_chain: string
  primary_node: string
  connections: number
  rules_hit: Record<string, number>
  host_recent: string
  overrides: Record<string, string>
}

interface GlobalRule {
  name: string
  type: string
  target: string
}

interface ClientRoutesProps {
  clients: any[]
  groups: any[]
  routesData: { clients: ClientRouteData[]; global_rules: GlobalRule[] } | null
  onSave: (ip: string, overrides: Record<string, string>) => Promise<void>
}

function getNodeColor(name: string) {
  if (name.includes("DIRECT")) return "text-success"
  if (name.includes("🇭🇰")) return "text-amber-400"
  if (name.includes("🇸🇬")) return "text-emerald-400"
  if (name.includes("🇺🇸")) return "text-blue-400"
  return "text-primary"
}

export function ClientRoutes({ clients, groups, routesData, onSave }: ClientRoutesProps) {
  const [expanded, setExpanded] = useState<Set<string>>(new Set())
  const [editing, setEditing] = useState<Record<string, Record<string, string>>>({})
  const [saving, setSaving] = useState<string | null>(null)

  const toggle = (ip: string) => {
    const next = new Set(expanded)
    if (next.has(ip)) next.delete(ip)
    else next.add(ip)
    setExpanded(next)
  }

  const handleAdd = (ip: string) => {
    setEditing((prev) => ({
      ...prev,
      [ip]: { ...prev[ip], "": groups[0]?.name || "" },
    }))
  }

  const handleChange = (ip: string, oldPattern: string, field: "pattern" | "target", value: string) => {
    setEditing((prev) => {
      const copy = { ...prev[ip] }
      if (field === "pattern") {
        const target = copy[oldPattern]
        delete copy[oldPattern]
        copy[value] = target
      } else {
        copy[oldPattern] = value
      }
      return { ...prev, [ip]: copy }
    })
  }

  const handleDelete = (ip: string, pattern: string) => {
    setEditing((prev) => {
      const copy = { ...prev[ip] }
      delete copy[pattern]
      return { ...prev, [ip]: copy }
    })
  }

  const handleSave = async (ip: string, currentOverrides: Record<string, string>) => {
    setSaving(ip)
    try {
      const overrides = editing[ip] ?? currentOverrides
      const cleaned: Record<string, string> = {}
      for (const [k, v] of Object.entries(overrides)) {
        if (k.trim() && v.trim()) cleaned[k.trim()] = v.trim()
      }
      await onSave(ip, cleaned)
      setEditing((prev) => ({ ...prev, [ip]: {} }))
    } finally {
      setSaving(null)
    }
  }

  const clientMap = new Map((routesData?.clients || []).map((c) => [c.ip, c]))

  return (
    <div className="card-premium p-4">
      <div className="flex items-center gap-2 mb-4">
        <h3 className="text-sm font-semibold">客户端路由</h3>
        <span className="text-xs text-muted-foreground font-mono bg-secondary/50 px-2 py-0.5 rounded-md">
          {routesData?.clients.length || 0}
        </span>
      </div>
      <p className="text-xs text-muted-foreground mb-4">
        全局规则为默认；客户端覆盖规则优先级更高，仅对指定设备生效。
      </p>

      <div className="flex flex-col gap-3">
        {clients.length === 0 ? (
          <p className="text-sm text-muted-foreground">暂无活动客户端</p>
        ) : (
          clients.map((client) => {
            const ip = client.ip
            const route = clientMap.get(ip)
            const isExpanded = expanded.has(ip)
            const overrides = editing[ip] ?? route?.overrides ?? {}
            return (
              <div key={ip} className="rounded-xl bg-secondary/20 overflow-hidden">
                <button
                  onClick={() => toggle(ip)}
                  className="w-full flex items-center justify-between px-4 py-3 text-left hover:bg-secondary/30 transition-colors"
                >
                  <div className="flex items-center gap-3 min-w-0">
                    <div className="w-8 h-8 rounded-lg bg-secondary/50 flex items-center justify-center shrink-0">
                      <span className="text-xs font-mono font-semibold">{ip.split('.').pop()}</span>
                    </div>
                    <div className="min-w-0">
                      <div className="flex items-center gap-2">
                        <span className="text-sm font-medium font-mono">{ip}</span>
                        {client.name && <span className="text-xs text-muted-foreground">{client.name}</span>}
                      </div>
                      <div className="flex items-center gap-2 mt-0.5">
                        <span className={cn("text-xs font-mono", getNodeColor(route?.primary_node || ""))}>
                          {route?.primary_node || "-"}
                        </span>
                        <span className="text-xs text-muted-foreground">{client.connections} 连接</span>
                      </div>
                    </div>
                  </div>
                  <ChevronDown
                    className={cn(
                      "w-4 h-4 text-muted-foreground shrink-0 transition-transform",
                      isExpanded && "rotate-180"
                    )}
                    strokeWidth={1.5}
                  />
                </button>

                {isExpanded && route && (
                  <div className="px-4 pb-4 flex flex-col gap-4">
                    <div>
                      <h4 className="text-xs font-medium text-muted-foreground mb-2">当前主链路</h4>
                      <p className="text-sm font-mono break-all">{route.primary_chain}</p>
                    </div>

                    <div>
                      <div className="flex items-center justify-between mb-2">
                        <h4 className="text-xs font-medium text-muted-foreground">客户端覆盖规则</h4>
                        <button
                          onClick={() => handleAdd(ip)}
                          className="flex items-center gap-1 text-xs text-primary hover:text-primary/80"
                        >
                          <Plus className="w-3 h-3" />
                          添加
                        </button>
                      </div>

                      {Object.keys(overrides).length === 0 ? (
                        <p className="text-xs text-muted-foreground">暂无覆盖规则</p>
                      ) : (
                        <div className="flex flex-col gap-2">
                          {Object.entries(overrides).map(([pattern, target]) => (
                            <div key={pattern} className="flex items-center gap-2">
                              <input
                                type="text"
                                value={pattern}
                                onChange={(e) => handleChange(ip, pattern, "pattern", e.target.value)}
                                placeholder="域名后缀，如 plex.tv"
                                className="flex-1 min-w-0 px-2 py-1.5 bg-secondary/50 rounded text-sm font-mono"
                              />
                              <select
                                value={target}
                                onChange={(e) => handleChange(ip, pattern, "target", e.target.value)}
                                className="px-2 py-1.5 bg-secondary/50 rounded text-sm"
                              >
                                {groups.map((g) => (
                                  <option key={g.name} value={g.name}>{g.name}</option>
                                ))}
                              </select>
                              <button
                                onClick={() => handleDelete(ip, pattern)}
                                className="p-1.5 text-muted-foreground hover:text-destructive"
                              >
                                <Trash2 className="w-3.5 h-3.5" />
                              </button>
                            </div>
                          ))}
                        </div>
                      )}

                      <button
                        onClick={() => handleSave(ip, route.overrides)}
                        disabled={saving === ip}
                        className="mt-3 flex items-center gap-1.5 px-3 py-1.5 bg-primary text-primary-foreground rounded-lg text-xs font-semibold hover:opacity-90 disabled:opacity-50"
                      >
                        <Save className="w-3 h-3" />
                        {saving === ip ? "保存中..." : "保存覆盖规则"}
                      </button>
                    </div>

                    <div>
                      <h4 className="text-xs font-medium text-muted-foreground mb-2">全局规则（默认）</h4>
                      <div className="flex flex-wrap gap-2">
                        {(routesData?.global_rules || []).map((rule) => (
                          <span
                            key={rule.name}
                            className="text-xs px-2 py-1 rounded-md bg-secondary/50 font-mono"
                            title={rule.type}
                          >
                            {rule.name} → {rule.target}
                          </span>
                        ))}
                      </div>
                    </div>
                  </div>
                )}
              </div>
            )
          })
        )}
      </div>
    </div>
  )
}
