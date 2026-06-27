"use client"

import { useState } from "react"
import { RefreshCw, Loader2 } from "lucide-react"
import { cn } from "@/lib/utils"

interface SyncButtonProps {
  onSync: () => Promise<void>
}

export function SyncButton({ onSync }: SyncButtonProps) {
  const [isSyncing, setIsSyncing] = useState(false)

  const handleClick = async () => {
    if (isSyncing) return
    setIsSyncing(true)
    try {
      await onSync()
    } finally {
      setIsSyncing(false)
    }
  }

  return (
    <button
      onClick={handleClick}
      disabled={isSyncing}
      className={cn(
        "inline-flex items-center gap-1.5 px-3 py-2 rounded-xl text-xs font-medium transition-all duration-200",
        "bg-secondary/60 text-muted-foreground hover:bg-secondary hover:text-foreground",
        "disabled:opacity-60 disabled:cursor-not-allowed"
      )}
    >
      {isSyncing ? (
        <>
          <Loader2 className="w-3.5 h-3.5 animate-spin" strokeWidth={1.5} />
          同步中...
        </>
      ) : (
        <>
          <RefreshCw className="w-3.5 h-3.5" strokeWidth={1.5} />
          同步
        </>
      )}
    </button>
  )
}
