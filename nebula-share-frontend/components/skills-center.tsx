"use client"

import { useEffect, useMemo, useState } from "react"
import { CheckSquare, Download, RefreshCw, Square, Terminal } from "lucide-react"
import { Button } from "@/components/ui/button"
import { cn } from "@/lib/utils"

interface Skill {
  name: string
  displayName: string
  description: string
  files: string[]
  category?: string
}

const categoryLabel = (cat?: string) => {
  if (cat === "commands") return "命令"
  return "Skill"
}

const categoryClass = (cat?: string) => {
  if (cat === "commands") return "bg-chart-3/15 text-chart-3"
  return "bg-chart-1/15 text-chart-1"
}

export function SkillsCenter() {
  const [skills, setSkills] = useState<Skill[]>([])
  const [loading, setLoading] = useState(true)
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [refreshing, setRefreshing] = useState(false)
  const [command, setCommand] = useState<string | null>(null)

  const fetchSkills = async () => {
    setLoading(true)
    try {
      const r = await fetch("/api/skills")
      const d = await r.json()
      setSkills(d.skills || [])
    } catch {
      setSkills([])
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchSkills()
  }, [])

  const toggle = (name: string) => {
    setSelected((prev) => {
      const next = new Set(prev)
      if (next.has(name)) next.delete(name)
      else next.add(name)
      return next
    })
  }

  const toggleAll = () => {
    if (selected.size === skills.length) setSelected(new Set())
    else setSelected(new Set(skills.map((s) => s.name)))
  }

  const refresh = async () => {
    setRefreshing(true)
    try {
      await fetch("/api/skills/refresh", { method: "POST" })
      await fetchSkills()
    } finally {
      setRefreshing(false)
    }
  }

  const selectedNames = useMemo(() => Array.from(selected).join(","), [selected])

  const installCommand = useMemo(() => {
    if (selected.size === 0) return ""
    return `python3 tools/skill-sync/install_skills.py --server http://<NEBULA_IP>:8080 install --names ${selectedNames}`
  }, [selected, selectedNames])

  const bundleUrl = useMemo(() => {
    if (selected.size === 0) return ""
    return `/api/skills/bundle?names=${encodeURIComponent(selectedNames)}&target=claude`
  }, [selected, selectedNames])

  if (loading) {
    return (
      <div className="h-full flex items-center justify-center">
        <div className="w-8 h-8 border-2 border-primary/30 border-t-primary rounded-full animate-spin" />
      </div>
    )
  }

  return (
    <div className="h-full flex flex-col gap-4">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold tracking-tight">Skill 中心</h2>
          <p className="text-sm text-muted-foreground mt-0.5">集中管理各终端 Claude Code / Codex skill</p>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" onClick={toggleAll}>
            {selected.size === skills.length ? "取消全选" : "全选"}
          </Button>
          <Button variant="outline" size="sm" onClick={refresh} disabled={refreshing}>
            <RefreshCw className={cn("w-3.5 h-3.5 mr-1", refreshing && "animate-spin")} />
            刷新
          </Button>
        </div>
      </div>

      {skills.length === 0 ? (
        <div className="flex-1 flex items-center justify-center text-muted-foreground">
          暂无 skill，点击刷新从服务器本地扫描
        </div>
      ) : (
        <div className="flex-1 overflow-auto">
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3">
            {skills.map((skill) => {
              const isSelected = selected.has(skill.name)
              return (
                <div
                  key={skill.name}
                  onClick={() => toggle(skill.name)}
                  className={cn(
                    "cursor-pointer rounded-xl border p-4 transition-all hover:border-primary/40",
                    isSelected ? "border-primary bg-primary/5" : "border-border/40 bg-card"
                  )}
                >
                  <div className="flex items-start gap-3">
                    <div className="mt-0.5">
                      {isSelected ? (
                        <CheckSquare className="w-4 h-4 text-primary" />
                      ) : (
                        <Square className="w-4 h-4 text-muted-foreground" />
                      )}
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2">
                        <h3 className="font-medium text-sm truncate">{skill.displayName}</h3>
                        <span className={cn("text-[10px] px-1.5 py-0.5 rounded font-medium shrink-0", categoryClass(skill.category))}>
                          {categoryLabel(skill.category)}
                        </span>
                      </div>
                      <p className="text-xs text-muted-foreground mt-1 h-9 overflow-hidden text-ellipsis">
                        {skill.description}
                      </p>
                      <p className="text-[10px] text-muted-foreground/60 mt-2">{skill.files.length} 个文件</p>
                    </div>
                  </div>
                </div>
              )
            })}
          </div>
        </div>
      )}

      {selected.size > 0 && (
        <div className="rounded-xl border border-border/40 bg-card p-4 space-y-3">
          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
            <span className="text-sm font-medium">已选择 {selected.size} 个 skill</span>
            <div className="flex items-center gap-2">
              <Button size="sm" variant="secondary" onClick={() => (window.location.href = bundleUrl)}>
                <Download className="w-3.5 h-3.5 mr-1" />
                下载 bundle
              </Button>
              <Button size="sm" onClick={() => setCommand(installCommand)}>
                <Terminal className="w-3.5 h-3.5 mr-1" />
                生成安装命令
              </Button>
            </div>
          </div>
          {command && (
            <div className="relative rounded-lg bg-secondary/50 p-3">
              <code className="text-xs font-mono break-all whitespace-pre-wrap">{command}</code>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
