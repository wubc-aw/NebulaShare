"use client"

import { useEffect, useState } from "react"
import { X, Plus, Trash2, Save, Activity, Pencil, Check } from "lucide-react"
import { cn } from "@/lib/utils"

interface ClientSheetProps {
  ip: string | null
  isOpen: boolean
  onClose: () => void
  client: any
  clientName?: string
  route: any
  groups: any[]
  globalRules: any[]
  chainLog: any[]
  onSave: (ip: string, overrides: Record<string, string>) => Promise<void>
  onSaveName: (ip: string, name: string) => Promise<void>
}

function getNodeColor(name: string) {
  if (name.includes("DIRECT")) return "text-success"
  if (name.includes("🇭🇰")) return "text-amber-400"
  if (name.includes("🇸🇬")) return "text-emerald-400"
  if (name.includes("🇺🇸")) return "text-blue-400"
  return "text-primary"
}

function formatTime(iso: string) {
  try {
    const d = new Date(iso)
    return d.toLocaleTimeString("zh-CN", { hour12: false })
  } catch {
    return "-"
  }
}

export function ClientSheet({
  ip,
  isOpen,
  onClose,
  client,
  clientName,
  route,
  groups,
  globalRules,
  chainLog,
  onSave,
  onSaveName,
}: ClientSheetProps) {
  const [editing, setEditing] = useState<Record<string, string>>({})
  const [saving, setSaving] = useState(false)
  const [editingAlias, setEditingAlias] = useState(false)
  const [aliasDraft, setAliasDraft] = useState("")
  const [aliasSaving, setAliasSaving] = useState(false)

  // Reset editing state when sheet opens
  useEffect(() => {
    if (isOpen && route?.overrides) {
      setEditing({ ...route.overrides })
    } else if (!isOpen) {
      setEditing({})
      setEditingAlias(false)
      setAliasDraft("")
    }
  }, [isOpen, route?.overrides])

  useEffect(() => {
    if (isOpen && clientName !== undefined) {
      setAliasDraft(clientName)
    }
  }, [isOpen, clientName])

  if (!isOpen || !ip || !client) return null

  const handleAdd = () => {
    setEditing((prev) => ({ ...prev, "": groups[0]?.name || "" }))
  }

  const handleChange = (oldPattern: string, field: "pattern" | "target", value: string) => {
    setEditing((prev) => {
      const copy = { ...prev }
      if (field === "pattern") {
        const target = copy[oldPattern]
        delete copy[oldPattern]
        copy[value] = target
      } else {
        copy[oldPattern] = value
      }
      return copy
    })
  }

  const handleDelete = (pattern: string) => {
    setEditing((prev) => {
      const copy = { ...prev }
      delete copy[pattern]
      return copy
    })
  }

  const handleSave = async () => {
    const cleaned: Record<string, string> = {}
    for (const [k, v] of Object.entries(editing)) {
      if (k.trim() && v.trim()) cleaned[k.trim()] = v.trim()
    }
    setSaving(true)
    try {
      await onSave(ip, cleaned)
    } finally {
      setSaving(false)
    }
  }

  const handleAliasSave = async () => {
    if (!ip) return
    setAliasSaving(true)
    try {
      await onSaveName(ip, aliasDraft.trim())
      setEditingAlias(false)
    } finally {
      setAliasSaving(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex flex-col justify-end">
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-black/40 backdrop-blur-sm"
        onClick={onClose}
      />

      {/* Sheet */}
      <div className="relative z-10 w-full max-w-2xl mx-auto bg-background rounded-t-2xl shadow-2xl max-h-[85vh] flex flex-col animate-in slide-in-from-bottom-10 duration-200">
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-border">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-lg bg-secondary/50 flex items-center justify-center shrink-0">
              <span className="text-sm font-mono font-semibold">{ip.split('.').pop()}</span>
            </div>
            <div className="flex-1 min-w-0">
              {editingAlias ? (
                <div className="flex items-center gap-2">
                  <input
                    autoFocus
                    value={aliasDraft}
                    onChange={(e) => setAliasDraft(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter") handleAliasSave()
                      if (e.key === "Escape") {
                        setEditingAlias(false)
                        setAliasDraft(clientName || "")
                      }
                    }}
                    placeholder="备注名称"
                    className="flex-1 min-w-0 px-2 py-1 text-sm bg-background rounded border border-border focus:outline-none focus:ring-1 focus:ring-primary"
                  />
                  <button
                    onClick={handleAliasSave}
                    disabled={aliasSaving}
                    className="p-1 rounded-md bg-success/10 text-success hover:bg-success/20 transition-colors disabled:opacity-50"
                  >
                    <Check className="w-3.5 h-3.5" strokeWidth={2} />
                  </button>
                  <button
                    onClick={() => {
                      setEditingAlias(false)
                      setAliasDraft(clientName || "")
                    }}
                    className="p-1 rounded-md bg-secondary/50 text-muted-foreground hover:text-foreground transition-colors"
                  >
                    <X className="w-3.5 h-3.5" strokeWidth={2} />
                  </button>
                </div>
              ) : (
                <button
                  onClick={() => setEditingAlias(true)}
                  className="group flex items-center gap-1.5 text-left"
                  title={clientName ? "点击修改备注" : "点击添加备注"}
                >
                  <p className="text-base font-semibold truncate">{clientName || ip}</p>
                  <Pencil className="w-3.5 h-3.5 text-muted-foreground opacity-0 group-hover:opacity-100 transition-opacity" strokeWidth={2} />
                </button>
              )}
              {clientName && <p className="text-sm text-muted-foreground font-mono">{ip}</p>}
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-2 hover:bg-secondary rounded-full transition-colors"
          >
            <X className="w-5 h-5" strokeWidth={1.5} />
          </button>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-auto p-5 space-y-6">
          {/* Current chain */}
          <div className="card-premium p-4">
            <h4 className="text-sm font-medium text-muted-foreground mb-2">当前主链路</h4>
            <p className={cn("text-sm font-mono break-all", getNodeColor(route?.primary_node || ""))}>
              {route?.primary_chain || "-"}
            </p>
            <div className="flex items-center justify-between mt-3 text-xs text-muted-foreground">
              <span>{client?.connections || 0} 连接</span>
              <span>最近: {route?.host_recent || "-"}</span>
            </div>
          </div>

          {/* Client overrides */}
          <div className="card-premium p-4">
            <div className="flex items-center justify-between mb-3">
              <h4 className="text-sm font-medium">该客户端路由规则</h4>
              <span className="text-xs text-muted-foreground">不配则走全局默认</span>
            </div>

            {Object.keys(editing).length === 0 ? (
              <p className="text-sm text-muted-foreground mb-3">暂无覆盖规则，使用全局默认</p>
            ) : (
              <div className="flex flex-col gap-2 mb-3">
                {Object.entries(editing).map(([pattern, target]) => (
                  <div key={pattern} className="flex items-center gap-2">
                    <input
                      type="text"
                      value={pattern}
                      onChange={(e) => handleChange(pattern, "pattern", e.target.value)}
                      placeholder="域名后缀，如 plex.tv"
                      className="flex-1 min-w-0 px-2 py-1.5 bg-secondary/50 rounded text-sm font-mono"
                    />
                    <select
                      value={target}
                      onChange={(e) => handleChange(pattern, "target", e.target.value)}
                      className="px-2 py-1.5 bg-secondary/50 rounded text-sm"
                    >
                      {groups.map((g) => (
                        <option key={g.name} value={g.name}>{g.name}</option>
                      ))}
                    </select>
                    <button
                      onClick={() => handleDelete(pattern)}
                      className="p-1.5 text-muted-foreground hover:text-destructive"
                    >
                      <Trash2 className="w-3.5 h-3.5" />
                    </button>
                  </div>
                ))}
              </div>
            )}

            <div className="flex items-center gap-2">
              <button
                onClick={handleAdd}
                className="flex items-center gap-1 px-3 py-1.5 text-xs text-primary hover:bg-primary/10 rounded-lg transition-colors"
              >
                <Plus className="w-3 h-3" />
                添加规则
              </button>
              <button
                onClick={handleSave}
                disabled={saving}
                className="flex items-center gap-1 px-3 py-1.5 bg-primary text-primary-foreground rounded-lg text-xs font-semibold hover:opacity-90 disabled:opacity-50"
              >
                <Save className="w-3 h-3" />
                {saving ? "保存中..." : "保存规则"}
              </button>
            </div>
          </div>

          {/* Global rules reference */}
          <div className="card-premium p-4">
            <h4 className="text-sm font-medium text-muted-foreground mb-3">全局默认规则</h4>
            <div className="flex flex-wrap gap-2">
              {globalRules.map((rule) => (
                <span
                  key={rule.name}
                  className="text-xs px-2 py-1 rounded-md bg-secondary/50 font-mono"
                >
                  {rule.name} → {rule.target}
                </span>
              ))}
            </div>
          </div>

          {/* Chain log */}
          <div className="card-premium p-4">
            <div className="flex items-center gap-2 mb-3">
              <Activity className="w-4 h-4 text-muted-foreground" strokeWidth={1.5} />
              <h4 className="text-sm font-medium">该客户端链路日志</h4>
              <span className="text-xs text-muted-foreground font-mono bg-secondary/50 px-2 py-0.5 rounded-md">
                {chainLog.length}
              </span>
            </div>

            {chainLog.length === 0 ? (
              <p className="text-sm text-muted-foreground">暂无链路日志</p>
            ) : (
              <div className="flex flex-col gap-2 max-h-64 overflow-auto pr-1">
                {chainLog.map((item, idx) => (
                  <div
                    key={idx}
                    className="flex flex-col gap-1 px-3 py-2 rounded-xl bg-secondary/20"
                  >
                    <div className="flex items-center justify-between gap-3">
                      <span className="text-xs text-muted-foreground font-mono">{formatTime(item.start)}</span>
                      <span className="text-xs font-medium truncate">{item.host}:{item.port}</span>
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
        </div>
      </div>
    </div>
  )
}
