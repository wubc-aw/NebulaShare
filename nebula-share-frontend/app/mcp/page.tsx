"use client"

import { useState } from "react"
import { Wrench, Search, GitBranch, AlertTriangle, Zap, Activity, FolderTree, MessageSquare, ArrowRight, Loader2 } from "lucide-react"
import { cn } from "@/lib/utils"

interface MCPTool {
  id: string
  name: string
  description: string
  icon: React.ReactNode
  params: { name: string; label: string; type: "text" | "select"; options?: string[]; required?: boolean }[]
}

const tools: MCPTool[] = [
  {
    id: "list_fault_codes",
    name: "列出故障码",
    description: "按类别列出所有充电桩故障码",
    icon: <AlertTriangle className="w-5 h-5" />,
    params: [
      { name: "category", label: "类别", type: "select", options: ["全部", "常规停止", "平台异常", "设备异常", "电源异常", "车辆故障", "模块告警", "BMS安全监控", "业务分析", "内部使用"], required: false },
    ],
  },
  {
    id: "search_fault_codes",
    name: "搜索故障码",
    description: "按关键词搜索故障码",
    icon: <Search className="w-5 h-5" />,
    params: [{ name: "keyword", label: "关键词", type: "text", required: true }],
  },
  {
    id: "find_interface",
    name: "查找接口",
    description: "查询函数的调用关系和依赖",
    icon: <GitBranch className="w-5 h-5" />,
    params: [{ name: "name", label: "函数名", type: "text", required: true }],
  },
  {
    id: "query_protocol",
    name: "查询协议",
    description: "查询协议帧定义和交互流程",
    icon: <MessageSquare className="w-5 h-5" />,
    params: [{ name: "frame_type", label: "帧类型/命令号", type: "text", required: true }],
  },
  {
    id: "trace_call_path",
    name: "调用链追踪",
    description: "从入口函数追踪完整调用树",
    icon: <ArrowRight className="w-5 h-5" />,
    params: [
      { name: "entry", label: "入口函数", type: "text", required: true },
    ],
  },
  {
    id: "what_do_i_need",
    name: "功能推荐",
    description: "根据功能描述推荐需要的接口和模块",
    icon: <Zap className="w-5 h-5" />,
    params: [{ name: "feature", label: "功能描述", type: "text", required: true }],
  },
  {
    id: "get_state_machine",
    name: "状态机",
    description: "获取充电桩完整状态机",
    icon: <Activity className="w-5 h-5" />,
    params: [],
  },
  {
    id: "list_modules",
    name: "模块列表",
    description: "列出所有代码模块",
    icon: <FolderTree className="w-5 h-5" />,
    params: [],
  },
  {
    id: "get_protocol_flow",
    name: "协议流程",
    description: "获取协议交互流程",
    icon: <ArrowRight className="w-5 h-5" />,
    params: [{ name: "flow_name", label: "流程名称(可选)", type: "text", required: false }],
  },
]

export default function MCPPage() {
  const [selectedTool, setSelectedTool] = useState<MCPTool | null>(null)
  const [formValues, setFormValues] = useState<Record<string, string>>({})
  const [result, setResult] = useState<unknown | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const handleExecute = async () => {
    if (!selectedTool) return
    setLoading(true)
    setError(null)
    setResult(null)

    try {
      const params = new URLSearchParams()
      Object.entries(formValues).forEach(([k, v]) => {
        if (v) params.append(k, v)
      })

      const url = `/api/mcp/${selectedTool.id}?${params.toString()}`
      const res = await fetch(url)
      const data = await res.json()
      if (!res.ok) throw new Error(data.error || `HTTP ${res.status}`)
      setResult(data)
    } catch (err) {
      setError(err instanceof Error ? err.message : "执行失败")
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="p-6 sm:p-8 max-w-6xl mx-auto h-full flex flex-col">
      {/* Page Header */}
      <div className="mb-6">
        <h1 className="text-2xl font-bold tracking-tight">🛠 MCP 工具</h1>
        <p className="text-sm text-muted-foreground mt-1">
          充电桩 SDK 4.0 知识图谱查询工具 · 故障码 · 接口 · 协议 · 状态机
        </p>
      </div>

      <div className="flex flex-col lg:flex-row gap-6 flex-1 min-h-0">
        {/* Tool Cards */}
        <div className="lg:w-80 shrink-0 overflow-auto">
          <div className="grid grid-cols-1 gap-2">
            {tools.map((tool) => (
              <button
                key={tool.id}
                onClick={() => {
                  setSelectedTool(tool)
                  setFormValues({})
                  setResult(null)
                  setError(null)
                }}
                className={cn(
                  "flex items-start gap-3 p-4 rounded-xl border text-left transition-all",
                  selectedTool?.id === tool.id
                    ? "bg-primary/10 border-primary/40 shadow-sm"
                    : "bg-card border-border/40 hover:border-primary/30 hover:bg-secondary/50"
                )}
              >
                <div
                  className={cn(
                    "w-9 h-9 rounded-lg flex items-center justify-center shrink-0",
                    selectedTool?.id === tool.id
                      ? "bg-primary/20 text-primary"
                      : "bg-secondary text-muted-foreground"
                  )}
                >
                  {tool.icon}
                </div>
                <div className="min-w-0">
                  <p className="text-sm font-medium">{tool.name}</p>
                  <p className="text-xs text-muted-foreground mt-0.5">{tool.description}</p>
                </div>
              </button>
            ))}
          </div>
        </div>

        {/* Tool Execution Panel */}
        <div className="flex-1 min-h-0 overflow-auto">
          {!selectedTool ? (
            <div className="h-full flex items-center justify-center text-muted-foreground">
              <div className="text-center">
                <Wrench className="w-10 h-10 mx-auto mb-3 opacity-40" />
                <p className="text-sm">选择一个 MCP 工具开始查询</p>
              </div>
            </div>
          ) : (
            <div className="space-y-4">
              {/* Form */}
              <div className="bg-card rounded-xl p-5 border border-border/40">
                <div className="flex items-center gap-3 mb-4">
                  <div className="w-8 h-8 rounded-lg bg-primary/20 flex items-center justify-center text-primary">
                    {selectedTool.icon}
                  </div>
                  <div>
                    <h2 className="text-lg font-semibold">{selectedTool.name}</h2>
                    <p className="text-xs text-muted-foreground">{selectedTool.description}</p>
                  </div>
                </div>

                {selectedTool.params.length > 0 && (
                  <div className="space-y-3 mb-4">
                    {selectedTool.params.map((param) => (
                      <div key={param.name}>
                        <label className="text-sm font-medium mb-1.5 block">
                          {param.label}
                          {param.required && <span className="text-red-500 ml-0.5">*</span>}
                        </label>
                        {param.type === "select" ? (
                          <select
                            className="w-full px-3 py-2 rounded-lg bg-secondary border border-border/40 text-sm focus:outline-none focus:ring-1 focus:ring-primary/30"
                            value={formValues[param.name] || ""}
                            onChange={(e) =>
                              setFormValues((prev) => ({ ...prev, [param.name]: e.target.value }))
                            }
                          >
                            {param.options?.map((opt) => (
                              <option key={opt} value={opt === "全部" ? "" : opt}>
                                {opt}
                              </option>
                            ))}
                          </select>
                        ) : (
                          <input
                            type="text"
                            className="w-full px-3 py-2 rounded-lg bg-secondary border border-border/40 text-sm placeholder:text-muted-foreground/40 focus:outline-none focus:ring-1 focus:ring-primary/30"
                            placeholder={`输入${param.label}...`}
                            value={formValues[param.name] || ""}
                            onChange={(e) =>
                              setFormValues((prev) => ({ ...prev, [param.name]: e.target.value }))
                            }
                          />
                        )}
                      </div>
                    ))}
                  </div>
                )}

                <button
                  onClick={handleExecute}
                  disabled={loading}
                  className="flex items-center gap-2 px-4 py-2 rounded-lg bg-primary text-primary-foreground text-sm font-medium hover:bg-primary/90 disabled:opacity-50 transition-colors"
                >
                  {loading ? (
                    <>
                      <Loader2 className="w-4 h-4 animate-spin" />
                      执行中...
                    </>
                  ) : (
                    <>
                      <Zap className="w-4 h-4" />
                      执行查询
                    </>
                  )}
                </button>
              </div>

              {/* Error */}
              {error && (
                <div className="bg-red-500/10 border border-red-500/20 rounded-xl p-4 text-red-500 text-sm">
                  {error}
                </div>
              )}

              {/* Result */}
              {result && (
                <div className="bg-card rounded-xl p-5 border border-border/40">
                  <h3 className="text-sm font-semibold mb-3">📋 查询结果</h3>
                  <pre className="text-xs text-muted-foreground overflow-auto max-h-[500px] bg-secondary/50 rounded-lg p-4">
                    {JSON.stringify(result, null, 2)}
                  </pre>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
