"use client"

import { useState } from "react"
import { Newspaper, Download, ExternalLink, ChevronRight } from "lucide-react"
import { cn } from "@/lib/utils"

interface NewsDigest {
  id: string
  date: string
  title: string
  category: string
  summary: string
  content?: string
}

const mockDigests: NewsDigest[] = [
  {
    id: "1",
    date: "2026-06-05",
    title: "AI 周报：OpenAI 发布 GPT-5 Turbo",
    category: "AI",
    summary: "本周 AI 领域最重要的进展包括 OpenAI 新模型发布、Google DeepMind 的突破性研究...",
    content: `
      <h2>本周要闻</h2>
      <p>OpenAI 于本周二正式发布了 GPT-5 Turbo 模型，该模型在推理能力和上下文窗口方面都有显著提升...</p>
      <h2>行业动态</h2>
      <p>Google DeepMind 宣布其最新的 AlphaFold 3 在蛋白质结构预测方面取得了突破性进展...</p>
    `,
  },
  {
    id: "2",
    date: "2026-06-04",
    title: "科技简报：苹果 WWDC 2026 前瞻",
    category: "科技",
    summary: "苹果 WWDC 2026 将于下周召开，预计将发布 iOS 20、macOS 17 以及全新的 AR 眼镜...",
  },
  {
    id: "3",
    date: "2026-06-03",
    title: "金融日报：央行降息 25 个基点",
    category: "金融",
    summary: "中国人民银行宣布下调贷款市场报价利率(LPR) 25 个基点，这是今年第二次降息...",
  },
  {
    id: "4",
    date: "2026-06-02",
    title: "创投周刊：本周 10 起重大融资",
    category: "创投",
    summary: "本周全球科技创投市场共发生 10 起超过 1 亿美元的融资事件，涵盖 AI、新能源、生物科技等领域...",
  },
  {
    id: "5",
    date: "2026-06-01",
    title: "AI 周报：Anthropic 推出 Claude 4",
    category: "AI",
    summary: "Anthropic 发布了全新的 Claude 4 模型，在安全性和可控性方面有了重大改进...",
  },
]

// Category dot colors — low saturation functional accents
const categoryDot: Record<string, string> = {
  AI: "bg-chart-1",
  科技: "bg-chart-2",
  金融: "bg-chart-3",
  创投: "bg-chart-5",
}

function CategoryPill({ category }: { category: string }) {
  return (
    <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded bg-secondary/70 text-xs font-medium text-muted-foreground tracking-wide">
      <span className={cn("w-1.5 h-1.5 rounded-full", categoryDot[category] || "bg-muted-foreground")} />
      {category}
    </span>
  )
}

export function IntelligenceCenter() {
  const [selectedDigest, setSelectedDigest] = useState<NewsDigest | null>(null)

  return (
    <div className="h-full flex flex-col">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h2 className="text-lg font-semibold tracking-tight">情报站</h2>
          <p className="text-sm text-muted-foreground mt-1">每日新闻简报</p>
        </div>
        <span className="text-sm text-muted-foreground font-mono">{mockDigests.length} 篇未读</span>
      </div>

      <div className="flex-1 flex flex-col md:flex-row gap-4 min-h-0">
        {/* Digest List */}
        <div className={cn("flex-1 flex flex-col min-w-0", selectedDigest && "hidden md:flex")}>
          <div className="flex-1 overflow-auto cascade">
            {mockDigests.map((digest, i) => (
              <button
                key={digest.id}
                onClick={() => setSelectedDigest(digest)}
                className={cn(
                  "relative w-full px-3 py-4 text-left transition-colors group rounded-lg hover:bg-secondary/50",
                  i !== 0 && "border-t border-border/60",
                )}
              >
                {selectedDigest?.id === digest.id && (
                  <span className="absolute left-0 top-3 bottom-3 w-0.5 rounded-full bg-chart-1" />
                )}
                <div className="flex items-start justify-between gap-3">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-2">
                      <CategoryPill category={digest.category} />
                      <span className="text-sm text-muted-foreground font-mono">{digest.date}</span>
                    </div>
                    <h3 className="text-base font-medium mb-1 line-clamp-1">{digest.title}</h3>
                    <p className="text-sm text-muted-foreground line-clamp-2 leading-relaxed">{digest.summary}</p>
                  </div>
                  <ChevronRight
                    className="w-4 h-4 text-muted-foreground/50 opacity-0 group-hover:opacity-100 transition-opacity shrink-0 mt-1"
                    strokeWidth={1.5}
                  />
                </div>
              </button>
            ))}
          </div>
        </div>

        {/* Reading View */}
        {selectedDigest && (
          <div className="flex-1 flex flex-col bg-secondary/30 rounded-xl overflow-hidden min-w-0">
            <div className="flex items-center justify-between px-4 py-3 border-b border-border/60">
              <button
                onClick={() => setSelectedDigest(null)}
                className="md:hidden flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
              >
                <ChevronRight className="w-4 h-4 rotate-180" strokeWidth={1.5} />
                返回列表
              </button>
              <div className="hidden md:flex items-center gap-2">
                <CategoryPill category={selectedDigest.category} />
                <span className="text-sm text-muted-foreground font-mono">{selectedDigest.date}</span>
              </div>
              <div className="flex items-center gap-0.5">
                <button className="p-2 hover:bg-accent rounded-lg transition-colors" title="下载">
                  <Download className="w-4 h-4" strokeWidth={1.5} />
                </button>
                <button className="p-2 hover:bg-accent rounded-lg transition-colors" title="在新窗口打开">
                  <ExternalLink className="w-4 h-4" strokeWidth={1.5} />
                </button>
              </div>
            </div>

            <div className="flex-1 overflow-auto p-6">
              <h1 className="text-xl font-semibold mb-5 text-balance tracking-tight">{selectedDigest.title}</h1>

              {selectedDigest.content ? (
                <div
                  className="prose prose-sm dark:prose-invert max-w-none prose-headings:text-[15px] prose-headings:font-semibold prose-p:text-muted-foreground prose-p:leading-relaxed"
                  dangerouslySetInnerHTML={{ __html: selectedDigest.content }}
                />
              ) : (
                <div className="space-y-4">
                  <p className="text-muted-foreground leading-relaxed">{selectedDigest.summary}</p>
                  <div className="p-4 bg-card rounded-lg">
                    <p className="text-sm text-muted-foreground text-center">完整内容加载中...</p>
                  </div>
                </div>
              )}
            </div>
          </div>
        )}

        {/* Empty State for Desktop */}
        {!selectedDigest && (
          <div className="hidden md:flex flex-1 items-center justify-center bg-secondary/30 rounded-xl">
            <div className="text-center">
              <Newspaper className="w-9 h-9 text-muted-foreground/50 mx-auto mb-3" strokeWidth={1.5} />
              <p className="text-sm text-muted-foreground">选择一篇文章开始阅读</p>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
