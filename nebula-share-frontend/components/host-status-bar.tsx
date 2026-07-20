"use client"

import { useState, useEffect, useCallback } from "react"
import { ChevronDown, X, Search } from "lucide-react"
import { cn } from "@/lib/utils"

interface Process {
  pid: number
  name: string
  cpu: number
  memory: number
  runtime: string
}

interface CpuCore {
  id: number
  usage_percent: number | null
  frequency_mhz: number | null
}

interface TemperatureSensor {
  id: string
  label: string
  source: string
  temperature_c: number
  role: string
}

interface SystemStats {
  cpu_percent: number | null
  cpu_count: number
  cpu_cores: CpuCore[]
  mem_used: number
  mem_total: number
  mem_avail: number
  mem_percent: number
  temp_c: number | null
  temp_sensor_label: string | null
  temperature_sensors: TemperatureSensor[]
  disk_used: number
  disk_total: number
  disk_percent: number
  hdd_used: number | null
  hdd_total: number | null
  hdd_percent: number | null
  hdd_mounted: boolean
  uptime_s: number
  load_1: number
  load_5: number
  load_15: number
}

function formatUptime(seconds: number): string {
  const days = Math.floor(seconds / 86400)
  const hours = Math.floor((seconds % 86400) / 3600)
  const mins = Math.floor((seconds % 3600) / 60)
  if (days > 0) return `${days} 天 ${hours} 小时`
  if (hours > 0) return `${hours} 小时 ${mins} 分钟`
  return `${mins} 分钟`
}

function formatRuntime(seconds: number): string {
  const days = Math.floor(seconds / 86400)
  const hours = Math.floor((seconds % 86400) / 3600)
  const mins = Math.floor((seconds % 3600) / 60)
  if (days > 0) return `${days}d ${hours}h`
  if (hours > 0) return `${hours}h ${mins}m`
  return `${mins}m`
}

function formatBytes(bytes: number): string {
  const gb = bytes / (1024 * 1024 * 1024)
  if (gb >= 1) return `${gb.toFixed(1)}GB`
  const mb = bytes / (1024 * 1024)
  return `${mb.toFixed(0)}MB`
}

function getTempColor(temp: number | null): string {
  if (temp === null) return "text-foreground"
  if (temp >= 75) return "text-destructive"
  if (temp >= 60) return "text-warning"
  return "text-foreground"
}

export function HostStatusBar() {
  const [isExpanded, setIsExpanded] = useState(false)
  const [searchQuery, setSearchQuery] = useState("")
  const [stats, setStats] = useState<SystemStats | null>(null)
  const [processes, setProcesses] = useState<Process[]>([])
  const [loadingStats, setLoadingStats] = useState(true)
  const [loadingProcesses, setLoadingProcesses] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const fetchStats = useCallback(async () => {
    try {
      const res = await fetch("/api/system/stats")
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      const data = await res.json()
      setStats(data.stats)
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : "获取状态失败")
    } finally {
      setLoadingStats(false)
    }
  }, [])

  const fetchProcesses = useCallback(async () => {
    try {
      setLoadingProcesses(true)
      const res = await fetch("/api/system/processes")
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      const data = await res.json()
      const mapped: Process[] = data.processes.map((p: any) => ({
        pid: p.pid,
        name: p.service_name || p.name,
        cpu: p.cpu_percent,
        memory: p.mem_bytes,
        runtime: formatRuntime(p.runtime_seconds),
      }))
      setProcesses(mapped)
    } catch (err) {
      console.error("Failed to fetch processes:", err)
    } finally {
      setLoadingProcesses(false)
    }
  }, [])

  const killProcess = useCallback(async (pid: number) => {
    if (!confirm(`确定要终止进程 ${pid} 吗？`)) return
    try {
      const res = await fetch(`/api/system/process/${pid}/kill`, { method: "POST" })
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      await fetchProcesses()
    } catch (err) {
      alert("终止进程失败: " + (err instanceof Error ? err.message : "未知错误"))
    }
  }, [fetchProcesses])

  // Poll stats every 3 seconds
  useEffect(() => {
    fetchStats()
    const interval = setInterval(fetchStats, 3000)
    return () => clearInterval(interval)
  }, [fetchStats])

  // Fetch processes when expanded
  useEffect(() => {
    if (isExpanded) {
      fetchProcesses()
    }
  }, [isExpanded, fetchProcesses])

  const filteredProcesses = processes.filter((p) =>
    p.name.toLowerCase().includes(searchQuery.toLowerCase()),
  )

  const displayStats = stats
    ? {
        cpu: stats.cpu_percent !== null ? stats.cpu_percent.toFixed(1) : "--",
        memory: formatBytes(stats.mem_used),
        temp: stats.temp_c,
        up: stats.load_1.toFixed(2),
        down: stats.load_5.toFixed(2),
        uptime: formatUptime(stats.uptime_s),
      }
    : {
        cpu: "--",
        memory: "--",
        temp: null,
        up: "--",
        down: "--",
        uptime: "--",
      }

  return (
    <div className="relative host-status-bar">
      {/* Main Status Bar — full width, hairline divider beneath */}
      <button
        onClick={() => setIsExpanded(!isExpanded)}
        className={cn(
          "w-full flex items-center justify-center gap-x-2 sm:gap-x-3 px-3 sm:px-8 h-11",
          "border-b border-border bg-background/80 backdrop-blur-sm",
          "hover:bg-secondary/40 transition-colors cursor-pointer",
        )}
      >
        {/* Live dot */}
        <span className={cn(
          "w-1.5 h-1.5 rounded-full animate-pulse-soft shrink-0",
          loadingStats && !stats ? "bg-muted-foreground" : "bg-success"
        )} />

        {/* Inline metrics, monospace numbers */}
        <div className="flex items-center gap-x-2 text-sm text-muted-foreground font-mono overflow-x-auto whitespace-nowrap scrollbar-hide">
            <span>
              CPU <span className="text-foreground">{displayStats.cpu}{displayStats.cpu === "--" ? "" : "%"}</span>
          </span>
          <span className="text-border">·</span>
          <span>
            RAM <span className="text-foreground">{displayStats.memory}</span>
          </span>
          <span className="text-border">·</span>
            <span>
              <span className={cn(getTempColor(displayStats.temp))}>
              {displayStats.temp !== null ? `CPU ${displayStats.temp}°C` : "CPU --°C"}
            </span>
          </span>
          <span className="text-border">·</span>
          <span className="inline-flex items-center gap-1">
            <span aria-hidden>↑</span>
            <span className="text-foreground">{displayStats.up}</span>
            <span aria-hidden>↓</span>
            <span className="text-foreground">{displayStats.down}</span>
            <span className="text-muted-foreground/70">MB/s</span>
          </span>
        </div>

        <ChevronDown
          className={cn(
            "w-3.5 h-3.5 text-muted-foreground transition-transform shrink-0",
            isExpanded && "rotate-180",
          )}
          strokeWidth={1.5}
        />
      </button>

      {/* Expanded Panel */}
      {isExpanded && (
        <div className="absolute top-full left-0 right-0 z-50 bg-popover border-b border-border shadow-pop">
          <div className="p-4 sm:p-6 max-w-5xl mx-auto">
            {/* Header */}
            <div className="flex items-center justify-between mb-4">
              <div>
                <h3 className="text-base font-medium">系统进程</h3>
                <p className="text-sm text-muted-foreground mt-0.5">在线时间 · {displayStats.uptime}</p>
              </div>
              <button
                onClick={(e) => {
                  e.stopPropagation()
                  setIsExpanded(false)
                }}
                className="p-1.5 hover:bg-accent rounded-lg transition-colors"
              >
                <X className="w-4 h-4" strokeWidth={1.5} />
              </button>
            </div>

            {/* System Details */}
            {stats && (
              <section className="mb-6 space-y-3">
                <div className="flex items-center justify-between">
                  <h4 className="text-sm font-medium">系统状态</h4>
                  <span className="text-xs text-muted-foreground font-mono">{stats.cpu_count} 核 CPU</span>
                </div>
                <div className="grid gap-3 md:grid-cols-2">
                  <div className="rounded-lg border border-border/60 bg-secondary/30 p-3">
                    <div className="flex items-center justify-between text-sm">
                      <span className="text-muted-foreground">CPU 总负载</span>
                      <span className="font-mono">{displayStats.cpu}{displayStats.cpu === "--" ? "" : "%"}</span>
                    </div>
                    <div className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-4">
                      {stats.cpu_cores.map((core) => (
                        <div key={core.id} className="rounded-md bg-background/60 px-2 py-1.5">
                          <div className="flex justify-between text-[11px] text-muted-foreground">
                            <span>Core {core.id}</span>
                            <span>{core.frequency_mhz ? `${core.frequency_mhz}MHz` : "--"}</span>
                          </div>
                          <div className="mt-1.5 h-1.5 overflow-hidden rounded-full bg-muted">
                            <div
                              className={cn("h-full rounded-full", (core.usage_percent ?? 0) >= 85 ? "bg-destructive" : (core.usage_percent ?? 0) >= 60 ? "bg-warning" : "bg-success")}
                              style={{ width: `${core.usage_percent ?? 0}%` }}
                            />
                          </div>
                          <div className="mt-1 text-right text-xs font-mono">{core.usage_percent !== null ? `${core.usage_percent}%` : "--"}</div>
                        </div>
                      ))}
                    </div>
                  </div>

                  <div className="rounded-lg border border-border/60 bg-secondary/30 p-3">
                    <div className="flex items-center justify-between text-sm">
                      <span className="text-muted-foreground">内存占用</span>
                      <span className="font-mono">{stats.mem_percent.toFixed(1)}%</span>
                    </div>
                    <div className="mt-2 h-2 overflow-hidden rounded-full bg-muted">
                      <div className="h-full rounded-full bg-primary" style={{ width: `${stats.mem_percent}%` }} />
                    </div>
                    <div className="mt-2 flex justify-between text-xs text-muted-foreground font-mono">
                      <span>已用 {formatBytes(stats.mem_used)}</span>
                      <span>可用 {formatBytes(stats.mem_avail)}</span>
                    </div>
                  </div>

                  <div className="rounded-lg border border-border/60 bg-secondary/30 p-3 md:col-span-2">
                    <div className="flex items-center justify-between text-sm">
                      <span className="text-muted-foreground">温度传感器</span>
                      <span className={cn("font-mono", getTempColor(stats.temp_c))}>
                        {stats.temp_sensor_label ?? "CPU Package"} {stats.temp_c !== null ? `${stats.temp_c}°C` : "--"}
                      </span>
                    </div>
                    <div className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-4">
                      {stats.temperature_sensors.map((sensor) => (
                        <div key={sensor.id} className="rounded-md bg-background/60 px-2.5 py-2">
                          <div className="truncate text-xs text-muted-foreground" title={sensor.source}>{sensor.label}</div>
                          <div className={cn("mt-1 text-sm font-mono", getTempColor(sensor.temperature_c))}>{sensor.temperature_c.toFixed(1)}°C</div>
                        </div>
                      ))}
                      {stats.temperature_sensors.length === 0 && (
                        <div className="text-sm text-muted-foreground">未检测到温度传感器</div>
                      )}
                    </div>
                  </div>
                </div>
              </section>
            )}

            <div className="mb-3 flex items-center justify-between">
              <h4 className="text-sm font-medium">进程列表</h4>
              <span className="text-xs text-muted-foreground">按 CPU 与内存占用排序</span>
            </div>

            {/* Search */}
            <div className="relative mb-4">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" strokeWidth={1.5} />
              <input
                type="text"
                placeholder="搜索进程"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="w-full pl-9 pr-4 py-2 bg-secondary/60 rounded-lg text-base focus:outline-none focus:ring-1 focus:ring-ring transition-shadow"
              />
            </div>

            {/* Process Table */}
            <div className="overflow-x-auto -mx-4 sm:mx-0 max-h-64">
              <div className="min-w-[640px] px-4 sm:px-0">
                {loadingProcesses ? (
                  <div className="py-8 text-center text-sm text-muted-foreground">加载中...</div>
                ) : (
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="text-left text-muted-foreground">
                        <th className="pb-2 font-medium font-mono">PID</th>
                        <th className="pb-2 font-medium">进程名</th>
                        <th className="pb-2 font-medium text-right">CPU</th>
                        <th className="pb-2 font-medium text-right">内存</th>
                        <th className="pb-2 font-medium text-right">运行时间</th>
                        <th className="pb-2 font-medium text-right">操作</th>
                      </tr>
                    </thead>
                    <tbody>
                      {filteredProcesses.map((process) => (
                        <tr key={process.pid} className="border-t border-border/60 hover:bg-secondary/40 transition-colors">
                          <td className="py-2 font-mono text-muted-foreground">{process.pid}</td>
                          <td className="py-2 font-mono">{process.name}</td>
                          <td className="py-2 text-right font-mono">
                            <span className={cn(process.cpu > 10 ? "text-warning" : "text-foreground")}>
                              {process.cpu.toFixed(1)}%
                            </span>
                          </td>
                          <td className="py-2 text-right font-mono text-muted-foreground">{formatBytes(process.memory)}</td>
                          <td className="py-2 text-right font-mono text-muted-foreground">{process.runtime}</td>
                          <td className="py-2 text-right">
                            <button
                              onClick={() => killProcess(process.pid)}
                              className="px-2 py-1 text-sm text-destructive hover:bg-destructive/10 rounded-md transition-colors"
                            >
                              终止
                            </button>
                          </td>
                        </tr>
                      ))}
                      {filteredProcesses.length === 0 && (
                        <tr>
                          <td colSpan={6} className="py-8 text-center text-muted-foreground">
                            无匹配进程
                          </td>
                        </tr>
                      )}
                    </tbody>
                  </table>
                )}
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
