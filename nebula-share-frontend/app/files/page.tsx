"use client"

import { FileHub } from "@/components/file-hub"

export default function FilesPage() {
  return (
    <div className="p-6 sm:p-8 max-w-6xl mx-auto h-full">
      <div className="mb-6">
        <h1 className="text-2xl font-bold tracking-tight">文件中心</h1>
        <p className="text-sm text-muted-foreground mt-1">临时文件快速交换 · 7 天后自动清理</p>
      </div>
      <div className="bg-card rounded-2xl p-5 sm:p-6 shadow-[var(--shadow-card)] border border-border/40">
        <FileHub />
      </div>
    </div>
  )
}
