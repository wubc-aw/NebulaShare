"use client"

import { SkillsCenter } from "@/components/skills-center"

export default function SkillsPage() {
  return (
    <div className="p-6 sm:p-8 max-w-6xl mx-auto h-full">
      <div className="bg-card rounded-2xl p-5 sm:p-6 shadow-[var(--shadow-card)] border border-border/40 h-full">
        <SkillsCenter />
      </div>
    </div>
  )
}
