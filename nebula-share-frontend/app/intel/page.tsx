"use client"

import { IntelligenceCenter } from "@/components/intelligence-center"

export default function IntelPage() {
  return (
    <div className="p-6 sm:p-8 max-w-6xl mx-auto h-full">
      <div className="mb-6">
        <h1 className="text-2xl font-bold tracking-tight">情报站</h1>
        <p className="text-sm text-muted-foreground mt-1">每日简报 · AI 聚合资讯</p>
      </div>
      <div className="bg-card rounded-2xl p-5 sm:p-6 shadow-[var(--shadow-card)] border border-border/40">
        <IntelligenceCenter />
      </div>
    </div>
  )
}
