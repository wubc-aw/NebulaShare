"use client"

import { useState, useCallback, useEffect } from "react"
import {
  Upload,
  Download,
  Trash2,
  QrCode,
  Clock,
  File,
  FileText,
  FileImage,
  FileArchive,
  Folder,
  ChevronRight,
  HardDrive,
  Plus,
  MoreHorizontal,
  Loader2,
} from "lucide-react"
import { cn } from "@/lib/utils"

interface ApiFile {
  filename: string
  size_human: string
  mtime_iso: string
  remain_hours: number
}

interface StorageRoot {
  path: string
  label: string
  total: number
  used: number
  percent: number
  used_human: string
  total_human: string
}

interface StorageItem {
  name: string
  type: "dir" | "file"
  size_human: string
  mtime_iso: string
}

interface ExchangeFile {
  id: string
  name: string
  size: string
  uploadTime: string
  expiresIn: string
  type: "file" | "image" | "document" | "archive"
}

type FileType = "file" | "image" | "document" | "archive"

function inferFileType(name: string): FileType {
  const lower = name.toLowerCase()
  if (/\.(png|jpe?g|gif|webp|bmp|svg)$/.test(lower)) return "image"
  if (/\.(pdf|docx?|txt|md|csv|json|yaml|yml)$/.test(lower)) return "document"
  if (/\.(zip|rar|7z|tar\.gz|tgz|bz2)$/.test(lower)) return "archive"
  return "file"
}

function formatRemain(hours: number): string {
  if (hours <= 0) return "即将过期"
  if (hours < 1) return "< 1 小时"
  if (hours < 24) return `${hours} 小时`
  const days = Math.floor(hours / 24)
  return `${days} 天 ${hours % 24} 小时`
}

function formatUploadTime(iso: string): string {
  const then = new Date(iso.replace(" ", "T"))
  const now = new Date()
  const diffMin = Math.floor((now.getTime() - then.getTime()) / 60000)
  if (diffMin < 1) return "刚刚"
  if (diffMin < 60) return `${diffMin} 分钟前`
  const diffH = Math.floor(diffMin / 60)
  if (diffH < 24) return `${diffH} 小时前`
  const diffD = Math.floor(diffH / 24)
  if (diffD === 1) return "昨天"
  return `${diffD} 天前`
}

const getFileIcon = (type: FileType) => {
  switch (type) {
    case "image":
      return FileImage
    case "document":
      return FileText
    case "archive":
      return FileArchive
    default:
      return File
  }
}

function Tabs({
  tabs,
  active,
  onChange,
}: {
  tabs: { id: string; label: string }[]
  active: string
  onChange: (id: string) => void
}) {
  return (
    <div className="inline-flex items-center gap-0.5 rounded-xl bg-secondary/60 p-1">
      {tabs.map((tab) => (
        <button
          key={tab.id}
          onClick={() => onChange(tab.id)}
          className={cn(
            "px-3.5 py-1.5 text-sm rounded-lg transition-colors",
            active === tab.id
              ? "bg-card text-foreground shadow-card"
              : "text-muted-foreground hover:text-foreground",
          )}
        >
          {tab.label}
        </button>
      ))}
    </div>
  )
}

export function FileHub() {
  const [activeTab, setActiveTab] = useState<"exchange" | "storage">("exchange")
  const [isDragging, setIsDragging] = useState(false)
  const [currentPath, setCurrentPath] = useState("")
  const [selectedDevice, setSelectedDevice] = useState("")

  // Exchange tab state
  const [exchangeFiles, setExchangeFiles] = useState<ExchangeFile[]>([])
  const [exchangeLoading, setExchangeLoading] = useState(false)
  const [exchangeQuota, setExchangeQuota] = useState({ used: "", max: "", percent: 0 })

  // Storage tab state
  const [storageRoots, setStorageRoots] = useState<StorageRoot[]>([])
  const [storageItems, setStorageItems] = useState<StorageItem[]>([])
  const [storageLoading, setStorageLoading] = useState(false)
  const [storageError, setStorageError] = useState("")
  const [storageRefreshKey, setStorageRefreshKey] = useState(0)

  // Fetch exchange files
  useEffect(() => {
    if (activeTab !== "exchange") return
    let cancelled = false
    setExchangeLoading(true)
    fetch("/api/files")
      .then((r) => r.json())
      .then((data) => {
        if (cancelled) return
        const mapped: ExchangeFile[] = (data.files || []).map((f: ApiFile) => ({
          id: f.filename,
          name: f.filename,
          size: f.size_human,
          uploadTime: formatUploadTime(f.mtime_iso),
          expiresIn: formatRemain(f.remain_hours),
          type: inferFileType(f.filename),
        }))
        setExchangeFiles(mapped)
        const total = data.total_size_human || "0 B"
        const max = data.max_size_human || "1 GB"
        // Parse percent from used/total if available, else fallback
        const usedBytes = data.total_size || 0
        const maxBytes = data.max_size || 1024 * 1024 * 1024
        const pct = maxBytes > 0 ? Math.round((usedBytes / maxBytes) * 100) : 0
        setExchangeQuota({ used: total, max, percent: pct })
      })
      .catch(() => {
        if (!cancelled) setExchangeFiles([])
      })
      .finally(() => {
        if (!cancelled) setExchangeLoading(false)
      })
    return () => { cancelled = true }
  }, [activeTab])

  // Fetch storage roots
  useEffect(() => {
    let cancelled = false
    fetch("/api/storage/roots")
      .then((r) => r.json())
      .then((data) => {
        if (cancelled) return
        const roots: StorageRoot[] = data.roots || []
        setStorageRoots(roots)
        if (roots.length > 0 && !selectedDevice) {
          setSelectedDevice(roots[0].path)
        }
      })
      .catch(() => {
        if (!cancelled) setStorageRoots([])
      })
    return () => { cancelled = true }
  }, [selectedDevice])

  // Fetch storage files when device or path changes
  useEffect(() => {
    if (activeTab !== "storage" || !selectedDevice) return
    let cancelled = false
    setStorageLoading(true)
    setStorageError("")
    const qs = new URLSearchParams({ root: selectedDevice, path: currentPath })
    fetch(`/api/storage/files?${qs}`)
      .then((r) => r.json())
      .then((data) => {
        if (cancelled) return
        if (data.ok === false) {
          setStorageError(data.error || "加载失败")
          setStorageItems([])
        } else {
          setStorageItems(data.items || [])
        }
      })
      .catch(() => {
        if (!cancelled) {
          setStorageError("网络错误")
          setStorageItems([])
        }
      })
      .finally(() => {
        if (!cancelled) setStorageLoading(false)
      })
    return () => { cancelled = true }
  }, [activeTab, selectedDevice, currentPath, storageRefreshKey])

  const handleDelete = useCallback(async (filename: string) => {
    if (!confirm(`删除 ${filename}？`)) return
    try {
      const r = await fetch(`/api/files/${encodeURIComponent(filename)}`, { method: "DELETE" })
      const data = await r.json()
      if (data.ok) {
        setExchangeFiles((prev) => prev.filter((f) => f.name !== filename))
      }
    } catch {
      // ignore
    }
  }, [])

  const handleDownload = useCallback((filename: string) => {
    window.open(`/api/download/${encodeURIComponent(filename)}`, "_blank")
  }, [])

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    setIsDragging(true)
  }, [])

  const handleDragLeave = useCallback(() => setIsDragging(false), [])

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    setIsDragging(false)
    const files = e.dataTransfer.files
    if (files.length > 0) {
      // Upload first file
      const file = files[0]
      const form = new FormData()
      form.append("file", file)
      fetch("/api/upload", { method: "POST", body: form })
        .then((r) => r.json())
        .then(() => {
          // Refresh file list
          setExchangeLoading(true)
          return fetch("/api/files")
        })
        .then((r) => r.json())
        .then((data) => {
          const mapped: ExchangeFile[] = (data.files || []).map((f: ApiFile) => ({
            id: f.filename,
            name: f.filename,
            size: f.size_human,
            uploadTime: formatUploadTime(f.mtime_iso),
            expiresIn: formatRemain(f.remain_hours),
            type: inferFileType(f.filename),
          }))
          setExchangeFiles(mapped)
          const total = data.total_size_human || "0 B"
          const max = data.max_size_human || "1 GB"
          const usedBytes = data.total_size || 0
          const maxBytes = data.max_size || 1024 * 1024 * 1024
          const pct = maxBytes > 0 ? Math.round((usedBytes / maxBytes) * 100) : 0
          setExchangeQuota({ used: total, max, percent: pct })
        })
        .catch(() => {})
        .finally(() => setExchangeLoading(false))
    }
  }, [])

  const handleFileInput = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    const form = new FormData()
    form.append("file", file)
    fetch("/api/upload", { method: "POST", body: form })
      .then((r) => r.json())
      .then(() => {
        setExchangeLoading(true)
        return fetch("/api/files")
      })
      .then((r) => r.json())
      .then((data) => {
        const mapped: ExchangeFile[] = (data.files || []).map((f: ApiFile) => ({
          id: f.filename,
          name: f.filename,
          size: f.size_human,
          uploadTime: formatUploadTime(f.mtime_iso),
          expiresIn: formatRemain(f.remain_hours),
          type: inferFileType(f.filename),
        }))
        setExchangeFiles(mapped)
        const total = data.total_size_human || "0 B"
        const max = data.max_size_human || "1 GB"
        const usedBytes = data.total_size || 0
        const maxBytes = data.max_size || 1024 * 1024 * 1024
        const pct = maxBytes > 0 ? Math.round((usedBytes / maxBytes) * 100) : 0
        setExchangeQuota({ used: total, max, percent: pct })
      })
      .catch(() => {})
      .finally(() => setExchangeLoading(false))
    e.target.value = ""
  }, [])

  const handleStorageFileInput = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file || !selectedDevice) return
    setStorageLoading(true)
    const form = new FormData()
    form.append("file", file)
    const qs = new URLSearchParams({ root: selectedDevice, path: currentPath })
    fetch(`/api/storage/upload?${qs}`, { method: "POST", body: form })
      .then((r) => r.json())
      .then((data) => {
        if (data.ok === false) {
          setStorageError(data.error || "上传失败")
          setStorageLoading(false)
        } else {
          setStorageRefreshKey((k) => k + 1)
        }
      })
      .catch(() => {
        setStorageError("网络错误")
        setStorageLoading(false)
      })
    e.target.value = ""
  }, [selectedDevice, currentPath])

  const handleStorageNavigate = useCallback((name: string) => {
    setCurrentPath((prev) => (prev ? `${prev}/${name}` : name))
  }, [])

  const handleStorageBreadcrumb = useCallback((idx: number, segments: string[]) => {
    if (idx < 0) {
      setCurrentPath("")
    } else {
      setCurrentPath(segments.slice(0, idx + 1).join("/"))
    }
  }, [])

  const selectedRoot = storageRoots.find((r) => r.path === selectedDevice)
  const pathSegments = currentPath.split("/").filter(Boolean)

  return (
    <div className="h-full flex flex-col">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h2 className="text-lg font-semibold tracking-tight">文件中心</h2>
          <p className="text-sm text-muted-foreground mt-1">快速交换与长期存储</p>
        </div>
        <Tabs
          tabs={[
            { id: "exchange", label: "快速交换" },
            { id: "storage", label: "长期存储" },
          ]}
          active={activeTab}
          onChange={(id) => setActiveTab(id as "exchange" | "storage")}
        />
      </div>

      {activeTab === "exchange" ? (
        <div className="flex-1 flex flex-col gap-4 cascade">
          {/* Upload Zone */}
          <div
            onDragOver={handleDragOver}
            onDragLeave={handleDragLeave}
            onDrop={handleDrop}
            className={cn(
              "relative rounded-xl p-10 text-center transition-colors",
              isDragging ? "dash-flow bg-secondary/40" : "bg-secondary/30",
            )}
          >
            {!isDragging && (
              <div className="absolute inset-0 rounded-xl border border-dashed border-border pointer-events-none" />
            )}
            <Upload
              className={cn("w-7 h-7 mx-auto mb-4", isDragging ? "text-foreground" : "text-muted-foreground")}
              strokeWidth={1.5}
            />
            <p className="text-sm text-muted-foreground mb-3">拖拽文件到这里，或者</p>
            <label className="px-4 py-1.5 bg-foreground text-background rounded-lg text-sm font-medium hover:opacity-90 transition-opacity cursor-pointer inline-block">
              选择文件
              <input type="file" className="hidden" onChange={handleFileInput} />
            </label>
            <p className="text-sm text-muted-foreground/70 mt-4">文件将在 24 小时后自动删除</p>
          </div>

          {/* Storage Quota */}
          <div className="flex items-center justify-between py-3">
            <div className="flex items-center gap-2">
              <HardDrive className="w-4 h-4 text-muted-foreground" strokeWidth={1.5} />
              <span className="text-sm text-muted-foreground">临时空间</span>
            </div>
            <div className="flex items-center gap-3">
              <div className="w-32 h-1 bg-secondary rounded-full overflow-hidden">
                <div
                  className="h-full bg-chart-1 rounded-full"
                  style={{ width: `${exchangeQuota.percent}%` }}
                />
              </div>
              <span className="text-sm font-mono text-muted-foreground">
                {exchangeQuota.used} / {exchangeQuota.max}
              </span>
            </div>
          </div>

          <div className="divider-x" />

          {/* File List */}
          <div className="flex-1 overflow-auto">
            <div className="flex items-center justify-between mb-3">
              <h3 className="text-sm font-medium text-muted-foreground">文件列表</h3>
              <button className="flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground transition-colors">
                <QrCode className="w-3.5 h-3.5" strokeWidth={1.5} />
                生成二维码
              </button>
            </div>

            {exchangeLoading && (
              <div className="flex items-center justify-center py-12">
                <Loader2 className="w-5 h-5 animate-spin text-muted-foreground" />
              </div>
            )}

            {!exchangeLoading && exchangeFiles.length === 0 && (
              <div className="text-center py-12 text-muted-foreground text-sm">
                暂无文件，拖拽或点击上传
              </div>
            )}

            {!exchangeLoading && exchangeFiles.length > 0 && (
              <div className="flex flex-col">
                {exchangeFiles.map((file, i) => {
                  const Icon = getFileIcon(file.type)
                  return (
                    <div
                      key={file.id}
                      className={cn(
                        "flex items-center justify-between py-3 group transition-colors rounded-lg px-2 -mx-2 hover:bg-secondary/50",
                        i !== 0 && "border-t border-border/60",
                      )}
                    >
                      <div className="flex items-center gap-3">
                        <Icon className="w-4 h-4 text-muted-foreground" strokeWidth={1.5} />
                        <div>
                          <p className="text-sm font-medium">{file.name}</p>
                          <p className="text-sm text-muted-foreground font-mono mt-0.5">
                            {file.size} · {file.uploadTime}
                          </p>
                        </div>
                      </div>
                      <div className="flex items-center gap-3">
                        <div className="flex items-center gap-1 text-sm text-muted-foreground font-mono">
                          <Clock className="w-3 h-3" strokeWidth={1.5} />
                          {file.expiresIn}
                        </div>
                        <div className="flex items-center gap-0.5 opacity-0 group-hover:opacity-100 transition-opacity">
                          <button
                            onClick={() => handleDownload(file.name)}
                            className="p-1.5 hover:bg-accent rounded-lg transition-colors"
                          >
                            <Download className="w-4 h-4" strokeWidth={1.5} />
                          </button>
                          <button
                            onClick={() => handleDelete(file.name)}
                            className="p-1.5 hover:bg-destructive/10 text-destructive rounded-lg transition-colors"
                          >
                            <Trash2 className="w-4 h-4" strokeWidth={1.5} />
                          </button>
                        </div>
                      </div>
                    </div>
                  )
                })}
              </div>
            )}
          </div>
        </div>
      ) : (
        <div className="flex-1 flex flex-col gap-4 cascade">
          {/* Device Selector */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            {storageRoots.length === 0 && !storageLoading && (
              <div className="col-span-full text-center py-6 text-muted-foreground text-sm">
                无可用存储设备
              </div>
            )}
            {storageRoots.map((device) => {
              const isActive = selectedDevice === device.path
              return (
                <button
                  key={device.path}
                  onClick={() => {
                    setSelectedDevice(device.path)
                    setCurrentPath("")
                  }}
                  className={cn(
                    "relative p-4 rounded-xl text-left transition-colors bg-secondary/30 hover:bg-secondary/50",
                  )}
                >
                  {isActive && <span className="absolute left-0 top-4 bottom-4 w-0.5 rounded-full bg-chart-1" />}
                  <div className="flex items-center justify-between mb-3">
                    <div className="flex items-center gap-2">
                      <HardDrive className="w-4 h-4 text-muted-foreground" strokeWidth={1.5} />
                      <span className="text-sm font-medium">{device.label}</span>
                    </div>
                    <span className="text-xs font-mono uppercase text-muted-foreground tracking-wider">
                      {device.path === "/" ? "ssd" : "hdd"}
                    </span>
                  </div>
                  <div className="w-full h-1 bg-secondary rounded-full overflow-hidden">
                    <div
                      className="h-full bg-chart-1 rounded-full"
                      style={{ width: `${device.percent}%` }}
                    />
                  </div>
                  <p className="text-sm text-muted-foreground font-mono mt-2">
                    {device.used_human} / {device.total_human}
                  </p>
                </button>
              )
            })}
          </div>

          {/* Path Navigation */}
          <div className="flex items-center gap-2 py-1">
            <Folder className="w-4 h-4 text-muted-foreground" strokeWidth={1.5} />
            <button
              onClick={() => setCurrentPath("")}
              className="text-sm font-mono text-muted-foreground hover:text-foreground transition-colors"
            >
              {selectedRoot?.label || "root"}
            </button>
            {pathSegments.map((segment, i) => (
              <div key={i} className="flex items-center gap-2">
                <ChevronRight className="w-3.5 h-3.5 text-muted-foreground/60" strokeWidth={1.5} />
                <button
                  onClick={() => handleStorageBreadcrumb(i, pathSegments)}
                  className="text-sm font-mono text-muted-foreground hover:text-foreground transition-colors"
                >
                  {segment}
                </button>
              </div>
            ))}
          </div>

          {/* Actions */}
          <div className="flex items-center gap-2">
            <label className="flex items-center gap-2 px-3 py-1.5 bg-foreground text-background rounded-lg text-sm font-medium hover:opacity-90 transition-opacity cursor-pointer">
              <Upload className="w-4 h-4" strokeWidth={1.5} />
              上传
              <input type="file" className="hidden" onChange={handleStorageFileInput} />
            </label>
            <button className="flex items-center gap-2 px-3 py-1.5 bg-secondary/60 rounded-lg text-sm hover:bg-secondary transition-colors">
              <Plus className="w-4 h-4" strokeWidth={1.5} />
              新建文件夹
            </button>
          </div>

          <div className="divider-x" />

          {/* File Browser */}
          <div className="flex-1 overflow-auto">
            {storageLoading && (
              <div className="flex items-center justify-center py-12">
                <Loader2 className="w-5 h-5 animate-spin text-muted-foreground" />
              </div>
            )}

            {!storageLoading && storageError && (
              <div className="text-center py-12 text-destructive text-sm">
                {storageError}
              </div>
            )}

            {!storageLoading && !storageError && storageItems.length === 0 && (
              <div className="text-center py-12 text-muted-foreground text-sm">
                空文件夹
              </div>
            )}

            {!storageLoading && !storageError && storageItems.length > 0 && (
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                {storageItems.map((item) =>
                  item.type === "dir" ? (
                    <button
                      key={item.name}
                      onClick={() => handleStorageNavigate(item.name)}
                      className="p-4 bg-secondary/30 rounded-xl hover:bg-secondary/50 transition-colors text-left"
                    >
                      <Folder className="w-7 h-7 text-muted-foreground mb-3" strokeWidth={1.5} />
                      <p className="text-sm font-medium truncate">{item.name}</p>
                      <p className="text-sm text-muted-foreground font-mono mt-0.5">文件夹</p>
                    </button>
                  ) : (
                    <div
                      key={item.name}
                      className="p-4 bg-secondary/30 rounded-xl hover:bg-secondary/50 transition-colors group relative"
                    >
                      {(() => {
                        const Icon = getFileIcon(inferFileType(item.name))
                        return <Icon className="w-7 h-7 text-muted-foreground mb-3" strokeWidth={1.5} />
                      })()}
                      <p className="text-sm font-medium truncate">{item.name}</p>
                      <p className="text-sm text-muted-foreground font-mono mt-0.5">{item.size_human}</p>
                      <button className="absolute top-2 right-2 p-1 opacity-0 group-hover:opacity-100 hover:bg-accent rounded-md transition-all">
                        <MoreHorizontal className="w-4 h-4" strokeWidth={1.5} />
                      </button>
                    </div>
                  ),
                )}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
