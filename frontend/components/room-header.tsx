'use client'

import { Pause, PanelRight, Trash2, VolumeX } from 'lucide-react'

function IconButton({
  label,
  children,
  danger,
}: {
  label: string
  children: React.ReactNode
  danger?: boolean
}) {
  return (
    <button
      type="button"
      aria-label={label}
      title={label}
      className={`flex size-8 items-center justify-center rounded-md border border-panel-border bg-secondary/50 text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground ${
        danger ? 'hover:border-destructive/50 hover:text-destructive' : ''
      }`}
    >
      {children}
    </button>
  )
}

export function RoomHeader({ onOpenStudio }: { onOpenStudio: () => void }) {
  return (
    <header className="flex items-center justify-between gap-4 border-b border-[#16161a] bg-panel px-5 py-3">
      {/* Left: title + actions */}
      <div className="flex items-center gap-3">
        <span className="size-2 rounded-full bg-green-500 pulse-dot" aria-hidden />
        <h1 className="text-[15px] font-semibold tracking-tight">Production Deployment Analyzer</h1>
        <div className="ml-2 hidden items-center gap-1.5 md:flex">
          <IconButton label="Pause Room">
            <Pause className="size-4" />
          </IconButton>
          <IconButton label="Mute Grid">
            <VolumeX className="size-4" />
          </IconButton>
          <IconButton label="Delete Room" danger>
            <Trash2 className="size-4" />
          </IconButton>
        </div>
      </div>

      {/* Right: taxi-meter + mobile studio toggle */}
      <div className="flex items-center gap-2">
        <div className="flex items-center gap-2 rounded-lg border border-[#FFF41F] bg-[#FFF41F] px-3.5 py-2 dark:border-[#FFF41F]/70 dark:bg-[#FFF41F]/[0.06]">
          <span className="text-[11px] font-medium uppercase tracking-wider text-[#111111]/70 dark:text-[#FFF41F]/80">
            Room Cost
          </span>
          <span className="font-mono text-[15px] font-semibold tabular-nums text-[#111111] dark:text-[#FFF41F]">
            $4.271
          </span>
          <span className="text-[11px] font-light text-[#111111]/70 dark:text-[#FFF41F]/70">USD</span>
        </div>
        <button
          type="button"
          onClick={onOpenStudio}
          aria-label="Open agent studio"
          title="Open agent studio"
          className="flex size-9 items-center justify-center rounded-md border border-panel-border bg-secondary/50 text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground lg:hidden"
        >
          <PanelRight className="size-4" />
        </button>
      </div>
    </header>
  )
}
