"use client"

import { ClaudeHistory } from "@/components/claude-history"

export default function ClaudePage() {
  return (
    <div className="p-6 sm:p-8 max-w-6xl mx-auto h-full">
      <div className="mb-6">
        <h1 className="text-2xl font-bold tracking-tight">Claude 历史</h1>
        <p className="text-sm text-muted-foreground mt-1">跨设备对话记录 · 行为分析</p>
      </div>
      <div className="bg-card rounded-2xl p-5 sm:p-6 shadow-[var(--shadow-card)] border border-border/40">
        <ClaudeHistory />
      </div>
    </div>
  )
}
