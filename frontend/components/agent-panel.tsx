'use client'

import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { agents as defaultAgents, builderLog, builderModels, llmModels } from '@/lib/agenlate-data'
import { ArrowLeft, Send, X } from 'lucide-react'
import { useMemo, useState } from 'react'

const MAX_INSTRUCTIONS = 8000

function ModelSelect({
  value,
  onValueChange,
  ariaLabel,
}: {
  value: string
  onValueChange: (value: string | null, eventDetails?: any) => void
  ariaLabel: string
}) {
  return (
    <Select value={value} onValueChange={onValueChange}>
      <SelectTrigger
        aria-label={ariaLabel}
        className="h-12 w-full rounded-lg border border-[#16161a] bg-[#141414] text-[15px] font-medium tracking-tight text-white focus:border-[#FFF41F]/50 focus:ring-0"
      >
        <SelectValue />
      </SelectTrigger>
      <SelectContent className="border-[#16161a] bg-[#141414]">
        {llmModels.map((m) => (
          <SelectItem key={m.value} value={m.value} className="text-[14px] py-2.5">
            <span className="flex flex-col gap-0.5">
              <span className="font-semibold text-white">{m.label}</span>
              <span className="text-[11px] font-light text-[#7d7d82]">{m.tier}</span>
            </span>
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  )
}

function PanelShell({
  title,
  subtitle,
  onClose,
  children,
}: {
  title?: string
  subtitle?: string
  onClose?: () => void
  children: React.ReactNode
}) {
  return (
    <aside className="flex h-full min-w-0 flex-1 flex-col bg-panel">
      {title && (
        <div className="flex items-center justify-between border-b border-[#16161a] px-5 py-4">
          <div className="flex flex-col leading-tight">
            <span className="text-[15px] font-semibold tracking-tight">{title}</span>
            {subtitle && (
              <span className="text-[11px] font-light text-muted-foreground">{subtitle}</span>
            )}
          </div>
          {onClose && (
            <button
              type="button"
              aria-label="Close studio"
              onClick={onClose}
              className="flex size-8 items-center justify-center rounded-md border border-panel-border text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground lg:hidden"
            >
              <X className="size-4" />
            </button>
          )}
        </div>
      )}
      {children}
    </aside>
  )
}

const AGENT_COLORS = ['#FFF41F', '#34D399', '#60A5FA', '#F472B6', '#FF6B35', '#A78BFA']

function BuilderFeed({ intro }: { intro?: React.ReactNode }) {
  return (
    <div className="scrollbar-thin flex-1 space-y-3.5 overflow-y-auto px-5 py-4">
      {intro}
      {builderLog.map((turn) =>
        turn.from === 'human' ? (
          <div key={turn.id} className="flex justify-end">
            <p
              className="max-w-[85%] rounded-2xl rounded-br-sm px-3.5 py-2.5 text-[12.5px] font-light leading-relaxed text-white bg-[#2F2F33]"
            >
              {turn.text}
            </p>
          </div>
        ) : (
          <div key={turn.id}>
            <p className="px-3.5 py-2.5 text-[12.5px] font-light leading-relaxed text-[#d4d4d8]">
              {turn.text}
            </p>
          </div>
        ),
      )}
    </div>
  )
}

function BuilderInput({
  draft,
  setDraft,
  base,
  placeholder,
}: {
  draft: string
  setDraft: (v: string) => void
  base: number
  placeholder: string
}) {
  const mass = base + draft.length
  const [builderModel, setBuilderModel] = useState(builderModels[0].value)

  return (
    <div className="relative px-5 pb-3 pt-2">
      <span
        aria-hidden
        className="pointer-events-none absolute right-6 top-0 select-none font-mono text-[11px] font-light tabular-nums text-[#7d7d82]"
      >
        {mass.toLocaleString()} / {MAX_INSTRUCTIONS.toLocaleString()} characters
      </span>
      <div className="mt-3 flex items-center gap-2">
        <input
          value={draft}
          onChange={(e) => setDraft(e.target.value.slice(0, Math.max(0, MAX_INSTRUCTIONS - base)))}
          placeholder={placeholder}
          className="min-w-0 flex-1 rounded-lg border border-[#16161a] bg-[#141414] px-3.5 py-2.5 text-[13px] font-light text-white outline-none transition-colors placeholder:text-zinc-500 focus:border-[#FFF41F]/50 dark:border-[#16161a] dark:bg-[#141414] dark:focus:border-[#FFF41F]/50"
        />

        {/* Builder Model Selector — compact */}
        <div className="shrink-0">
          <Select value={builderModel} onValueChange={(v) => v && setBuilderModel(v)}>
            <SelectTrigger
              aria-label="Builder model intelligence"
              className="h-10 w-[145px] rounded-lg border border-[#16161a] bg-[#141414] text-[12px] font-light text-[#7d7d82] transition-colors hover:text-white focus:border-[#FFF41F]/50 focus:ring-0"
            >
              <span className="flex items-center gap-1.5">
                <span className="truncate">{builderModels.find((m) => m.value === builderModel)?.label}</span>
              </span>
            </SelectTrigger>
            <SelectContent className="border-[#16161a] bg-[#141414]">
              {builderModels.map((m) => (
                <SelectItem key={m.value} value={m.value} className="text-[12px]">
                  <span className="flex flex-col">
                    <span className="font-medium">{m.label}</span>
                    <span className="text-[10px] font-light text-muted-foreground">{m.tier}</span>
                  </span>
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        <button
          type="button"
          aria-label="Send message to builder"
          className="flex size-10 shrink-0 items-center justify-center rounded-lg border border-transparent bg-[#FFF41F] text-[#111111] transition-all hover:brightness-95 dark:text-[#0A0A0A]"
        >
          <Send className="size-4" />
        </button>
      </div>
    </div>
  )
}

/* STATE A — Existing agent selected */
function ExistingAgentStudio({
  agent,
  isEditing,
  onClose,
  onColorChange,
  onSave,
}: {
  agent: (typeof defaultAgents)[number]
  isEditing: boolean
  onClose?: () => void
  onColorChange?: (agentId: string, newColor: string) => void
  onSave?: (agentId: string, name: string, role: string) => void
}) {
  const [model, setModel] = useState(agent.model)
  const [draft, setDraft] = useState('')
  const [accentColor, setAccentColor] = useState(agent.color)
  const [editName, setEditName] = useState(agent.name)
  const [editRole, setEditRole] = useState(agent.role)

  /* ─── NORMAL MODE (chat view) ─────────────────────────────────────────── */
  if (!isEditing) {
    return (
      <PanelShell onClose={onClose}>
        {/* Minimal header — avatar, name, role only, NO accent bar, NO model */}
        <div className="border-b border-[#16161a] px-5 py-4">
          <div className="flex items-center gap-3">
            <span
              className="flex size-9 shrink-0 items-center justify-center rounded-md text-[12px] font-semibold text-primary-foreground"
              style={{ backgroundColor: accentColor }}
              aria-hidden
            >
              {agent.initials}
            </span>
            <div className="min-w-0 flex-1 leading-tight">
              <div className="truncate text-[14px] font-semibold text-white">{agent.name}</div>
              <div className="truncate text-[11px] font-light text-[#7d7d82]">
                {agent.role}
              </div>
            </div>
          </div>
        </div>

        {/* Chat — flat, borderless, no accent tint */}
        <BuilderFeed />
        <div className="border-t border-[#16161a]">
          <BuilderInput
            draft={draft}
            setDraft={setDraft}
            base={312}
            placeholder="Continue refining this agent's behavior..."
          />
        </div>
      </PanelShell>
    )
  }

  /* ─── EDIT MODE (configuration view) ──────────────────────────────────── */
  return (
    <PanelShell onClose={onClose}>
      {/* Header — "Edit Agent" + Back to Chat */}
      <div className="border-b border-[#16161a] px-5 py-4">
        <div className="flex items-center gap-3">
          <button
            type="button"
            aria-label="Back to chat"
            onClick={() => onClose?.()}
            className="flex size-7 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-[#EBEBEB] hover:text-foreground dark:hover:bg-[#1a1a1a]"
          >
            <ArrowLeft className="size-4" strokeWidth={1.5} />
          </button>
          <span className="text-[15px] font-semibold tracking-tight text-white">Edit Agent</span>
        </div>
        {/* Accent color selector — visible ONLY in edit/create mode */}
        <div className="mt-10 flex items-center gap-2">
          <span className="text-[10px] font-light uppercase tracking-wider text-white">
            Accent
          </span>
          <div className="flex items-center gap-1.5">
            {AGENT_COLORS.map((color) => (
              <button
                key={color}
                type="button"
                aria-label={`Set accent to ${color}`}
                onClick={() => {
                  setAccentColor(color)
                  onColorChange?.(agent.id, color)
                }}
                className={`rounded-full transition-all ${
                  accentColor === color
                    ? 'size-7 scale-110'
                    : 'size-6 hover:scale-110'
                }`}
                style={{ backgroundColor: color }}
              />
            ))}
          </div>
        </div>

        {/* Form sections — uniform spacing */}
        <div className="flex flex-col gap-6 py-6">
          {/* Agent Name — flat minimal input */}
          <div>
            <label className="block text-[10px] font-light uppercase tracking-wider text-white">
              Agent Name
            </label>
            <input
              type="text"
              value={editName}
              onChange={(e) => setEditName(e.target.value)}
              className="w-full rounded-lg border border-[#16161a] bg-[#141414] px-3.5 py-2.5 text-[13px] font-medium text-white outline-none transition-colors placeholder:text-zinc-500 focus:border-[#FFF41F]/50"
              placeholder="e.g. Supervisor"
            />
          </div>

          {/* Role Description — flat minimal textarea */}
          <div>
            <label className="block text-[10px] font-light uppercase tracking-wider text-white">
              Role Description
            </label>
            <textarea
              value={editRole}
              onChange={(e) => setEditRole(e.target.value)}
              rows={2}
              className="w-full resize-none rounded-lg border border-[#16161a] bg-[#141414] px-3.5 py-2.5 text-[12.5px] font-light text-white outline-none transition-colors placeholder:text-zinc-500 focus:border-[#FFF41F]/50"
              placeholder="Describe this agent's primary responsibility..."
            />
          </div>

          {/* Builder Model — prominent architectural selector */}
          <div>
            <label className="block text-[10px] font-light uppercase tracking-wider text-white mb-3">
              BUILDER MODEL INTELLIGENCE
            </label>
            <div className="w-full">
              <ModelSelect
                value={model}
                onValueChange={(v) => v && setModel(v)}
                ariaLabel="Builder model intelligence"
              />
            </div>
          </div>
        </div>
      </div>

      {/* Compact Save / action */}
      <div className="flex items-center justify-center px-5 py-4">
        <button
          type="button"
          onClick={() => onSave?.(agent.id, editName, editRole)}
          className="rounded-lg bg-[#FFF41F] px-5 py-2 text-[13px] font-bold text-black transition-[filter] hover:brightness-90"
        >
          Save
        </button>
      </div>
    </PanelShell>
  )
}

/* STATE B — Add new agent */
function NewAgentStudio({ onClose, onColorChange, onDeploy }: { onClose?: () => void; onColorChange?: (agentId: string, newColor: string) => void; onDeploy?: (name: string, role: string) => void }) {
  const [builderModel, setBuilderModel] = useState('claude-3.7-sonnet')
  const [draft, setDraft] = useState('')
  const [accentColor, setAccentColor] = useState('#34D399')
  const [agentName, setAgentName] = useState('')
  const [agentRole, setAgentRole] = useState('')

  return (
    <PanelShell onClose={onClose}>
      {/* Compact header — title + accent color */}
      <div className="border-b border-[#16161a] px-5 py-4">
        <div className="flex items-center gap-3">
          <button
            type="button"
            aria-label="Back to room"
            onClick={onClose}
            className="flex size-7 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-[#EBEBEB] hover:text-foreground dark:hover:bg-[#1a1a1a]"
          >
            <ArrowLeft className="size-4" strokeWidth={1.5} />
          </button>
          <span className="text-[15px] font-semibold tracking-tight text-white">Build New Agent</span>
        </div>
        {/* Accent color selector */}
        <div className="mt-10 flex items-center gap-2">
          <span className="text-[10px] font-light uppercase tracking-wider text-white">
            Accent
          </span>
          <div className="flex items-center gap-1.5">
            {AGENT_COLORS.map((color) => (
              <button
                key={color}
                type="button"
                aria-label={`Set accent to ${color}`}
                onClick={() => setAccentColor(color)}
                className={`rounded-full transition-all ${
                  accentColor === color
                    ? 'size-7 scale-110'
                    : 'size-6 hover:scale-110'
                }`}
                style={{ backgroundColor: color }}
              />
            ))}
          </div>
        </div>
      </div>

      {/* Form sections — uniform spacing */}
      <div className="flex flex-col gap-6 px-5 py-6">
        {/* Agent Name — flat minimal input */}
        <div>
          <label className="block text-[10px] font-light uppercase tracking-wider text-white">
            Agent Name
          </label>
          <input
            type="text"
            value={agentName}
            onChange={(e) => setAgentName(e.target.value)}
            className="w-full rounded-lg border border-[#16161a] bg-[#141414] px-3.5 py-2.5 text-[13px] font-medium text-white outline-none transition-colors placeholder:text-zinc-500 focus:border-[#FFF41F]/50"
            placeholder="e.g. Supervisor"
          />
        </div>

        {/* Role Description — flat minimal textarea */}
        <div>
          <label className="block text-[10px] font-light uppercase tracking-wider text-white">
            Role Description
          </label>
          <textarea
            rows={2}
            value={agentRole}
            onChange={(e) => setAgentRole(e.target.value)}
            className="w-full resize-none rounded-lg border border-[#16161a] bg-[#141414] px-3.5 py-2.5 text-[12.5px] font-light text-white outline-none transition-colors placeholder:text-zinc-500 focus:border-[#FFF41F]/50"
            placeholder="Describe this agent's primary responsibility..."
          />
        </div>

        {/* Builder Model — prominent architectural selector */}
        <div>
          <label className="block text-[10px] font-light uppercase tracking-wider text-white mb-3">
            BUILDER MODEL INTELLIGENCE
          </label>
          <div className="w-full">
            <ModelSelect
              value={builderModel}
              onValueChange={(v) => v && setBuilderModel(v)}
              ariaLabel="Builder model intelligence"
            />
          </div>
        </div>
      </div>

      {/* Compact Deploy action */}
      <div className="flex items-center justify-center px-5 py-4">
        <button
          type="button"
          onClick={() => onDeploy?.(agentName, agentRole)}
          className="rounded-lg bg-[#FFF41F] px-5 py-2 text-[13px] font-bold text-black transition-[filter] hover:brightness-90"
        >
          Create
        </button>
      </div>
    </PanelShell>
  )
}

export function AgentPanel({
  selection,
  editingId,
  agents: roomAgents = defaultAgents,
  onClose,
  onColorChange,
  onDeploy,
  onSave,
}: {
  selection: string
  editingId?: string | null
  agents?: typeof defaultAgents
  onClose?: () => void
  onColorChange?: (agentId: string, newColor: string) => void
  onDeploy?: (name: string, role: string) => void
  onSave?: (agentId: string, name: string, role: string) => void
}) {
  const agent = useMemo(() => roomAgents.find((a) => a.id === selection), [selection, roomAgents])
  const isEditing = editingId === agent?.id

  if (selection === '') {
    return <BlankStudio onClose={onClose} />
  }
  if (selection === 'new' || !agent) {
    return <NewAgentStudio onClose={onClose} onColorChange={onColorChange} onDeploy={onDeploy} />
  }
  return <ExistingAgentStudio agent={agent} isEditing={isEditing} onClose={onClose} onColorChange={onColorChange} onSave={onSave} />
}

/* STATE Z — Blank template (new room, no agents) */
function BlankStudio({ onClose }: { onClose?: () => void }) {
  return (
    <PanelShell title="Blank Template" subtitle="No Agent Selected" onClose={onClose}>
      <div className="flex flex-1 flex-col items-center justify-center gap-4 px-6 text-center">
        <div className="flex size-16 items-center justify-center rounded-full border-2 border-dashed border-[#D4D4D8] bg-white dark:border-[#262629] dark:bg-[#0A0A0A]">
          <span className="text-2xl text-[#7A6F00] dark:text-[#FFF41F]">+</span>
        </div>
        <div>
          <p className="text-[16px] font-semibold text-[#111111] dark:text-white">Start Building Your Team</p>
          <p className="mt-1.5 max-w-sm text-[12.5px] font-light leading-relaxed text-[#52525B] dark:text-[#7d7d82]">
            Click the <span className="font-medium text-[#111111] dark:text-white">&quot;➕ Add New Agent&quot;</span> button on
            the left sidebar to add your first agent to this empty room.
          </p>
        </div>
      </div>
    </PanelShell>
  )
}
