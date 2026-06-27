"use client"

import { NetworkHub } from "@/components/network-hub"

export default function NetworkPage() {
  return (
    <div className="p-6 sm:p-8 max-w-6xl mx-auto h-full">
      <div className="mb-6">
        <h1 className="text-2xl font-bold tracking-tight">网络枢纽</h1>
        <p className="text-sm text-muted-foreground mt-1">代理节点 · 速度测试 · 可达性检查</p>
      </div>
      <div className="bg-card rounded-2xl p-5 sm:p-6 shadow-[var(--shadow-card)] border border-border/40">
        <NetworkHub />
      </div>
    </div>
  )
}
