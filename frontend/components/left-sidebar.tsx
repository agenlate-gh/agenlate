'use client'

/**
 * The room's roster.
 *
 * There is no Supervisor row. The Supervisor is not one of the user's agents —
 * it is the loop that decides which of them speaks — so listing it alongside
 * them would invite editing something that does not exist as a record.
 *
 * There is also no per-agent active switch. An agent's participation in a room
 * *is* the roster: removing it from the room is what "stop using this one"
 * means, and the agent itself survives to be seated again. A second notion of
 * paused would need a column, Supervisor logic to honour it, and an
 * explanation of how it differs from not being in the room.
 */

import { useEffect, useRef, useState } from 'react'
import { MoreVertical, Pencil, Trash2, UserMinus } from 'lucide-react'

import { Switch } from '@/components/ui/switch'
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogTitle,
} from '@/components/ui/dialog'
import { agentColor, agentInitials } from '@/lib/agent-appearance'
import type { Agent, RoomDetail } from '@/lib/agenlate'
import { formatUsd } from '@/lib/format'

export function LeftSidebar({
  room,
  selectedId,
  runCost,
  onSelect,
  onEditAgent,
  onAddAgent,
  onUnseat,
  onStatusChange,
  onDeleteRoom,
}: {
  room: RoomDetail
  selectedId: string | null
  /** Spent on the run happening now, not the room's lifetime total. */
  runCost: number
  onSelect: (id: string) => void
  onEditAgent: (id: string) => void
  onAddAgent: () => void
  onUnseat: (id: string) => void
  onStatusChange: (active: boolean) => void
  onDeleteRoom: () => void
}) {
  const [confirmingDelete, setConfirmingDelete] = useState(false)
  const active = room.status === 'active'

  return (
    <aside className="flex h-full w-[280px] shrink-0 flex-col border-r border-[#16161a] bg-panel">
      <div className="px-4 pt-4">
        <a
          href="/lobby"
          className="flex items-center gap-2 text-[12px] font-light text-[#7d7d82] transition-colors hover:text-white"
        >
          ← Exit to Lobby
        </a>
      </div>

      <div className="border-b border-[#16161a] px-4 pb-3 pt-3.5">
        <div className="flex items-center justify-between">
          <span className="text-[11px] font-medium uppercase tracking-wider text-[#7d7d82]">
            Room Metrics
          </span>
          <div className="flex items-center gap-1.5">
            <span className="text-[10px] font-light text-[#7d7d82]">
              {active ? 'Active' : 'Paused'}
            </span>
            <Switch
              checked={active}
              onCheckedChange={onStatusChange}
              aria-label={active ? 'Pause this room' : 'Resume this room'}
            />
          </div>
        </div>
        <div className="mt-1.5 flex flex-col leading-tight">
          <span className="truncate text-[13px] font-semibold text-[#d4d4d8]">
            {room.name}
          </span>
          <span className="mt-0.5 text-[11.5px] font-light text-[#7d7d82]">
            This run:{' '}
            <span className="font-mono font-medium tabular-nums">
              {formatUsd(runCost)}
            </span>{' '}
            USD
          </span>
        </div>
      </div>

      <div className="flex min-h-0 flex-1 flex-col px-4 pt-5">
        <span className="px-1 pb-2.5 text-[11px] font-medium uppercase tracking-wider text-[#7d7d82]">
          AGENTS
        </span>

        <div className="scrollbar-thin flex-1 space-y-0.5 overflow-y-auto">
          {room.agents.length === 0 && (
            <p className="px-3 pb-2 text-[11.5px] font-light leading-relaxed text-[#7d7d82]">
              No agents seated. Add one below — the Supervisor has nobody to
              hand work to until you do.
            </p>
          )}

          {room.agents.map((agent) => (
            <AgentRow
              key={agent.id}
              agent={agent}
              selected={agent.id === selectedId}
              onSelect={() => onSelect(agent.id)}
              onEdit={() => onEditAgent(agent.id)}
              onUnseat={() => onUnseat(agent.id)}
            />
          ))}

          <div className="mt-2">
            <button
              type="button"
              onClick={onAddAgent}
              className="flex w-full items-center gap-3 rounded-md px-3 py-2.5 text-left transition-all hover:bg-black/[0.04] dark:hover:bg-white/[0.04]"
            >
              <span className="flex size-8 shrink-0 items-center justify-center rounded-md border-2 border-dashed border-[#52525B] text-[#52525B] dark:border-[#7d7d82] dark:text-[#7d7d82]">
                <span className="text-[16px] font-light leading-none">+</span>
              </span>
              <span className="flex min-w-0 flex-1 flex-col leading-tight">
                <span className="truncate text-[13px] font-semibold text-[#d4d4d8]">
                  Add New Agent
                </span>
                <span className="truncate text-[11px] font-light text-[#7d7d82]">
                  Build one, or seat one you already have
                </span>
              </span>
            </button>
          </div>
        </div>
      </div>

      <div className="border-t border-[#16161a] px-4 py-3">
        <button
          type="button"
          onClick={() => setConfirmingDelete(true)}
          className="flex w-full items-center gap-3 rounded-md px-3 py-2.5 text-left text-[13px] font-medium text-[#ef4444]/80 transition-all hover:bg-red-950/30"
        >
          <Trash2 className="size-4" strokeWidth={1.5} />
          Delete Room
        </button>
      </div>

      <Dialog open={confirmingDelete} onOpenChange={setConfirmingDelete}>
        <DialogContent>
          <DialogTitle>Delete {room.name}?</DialogTitle>
          <DialogDescription>
            This deletes the room and its whole transcript. Your agents stay —
            only this room goes. It cannot be undone. To stop it running without
            losing anything, pause it instead.
          </DialogDescription>
          <div className="mt-5 flex justify-end gap-2">
            <DialogClose className="rounded-lg px-4 py-2.5 text-[13px] font-medium text-[#7d7d82] transition-colors hover:text-white">
              Cancel
            </DialogClose>
            <button
              type="button"
              onClick={onDeleteRoom}
              className="rounded-lg bg-red-600 px-4 py-2.5 text-[13px] font-semibold text-white transition-all hover:bg-red-500"
            >
              Delete room
            </button>
          </div>
        </DialogContent>
      </Dialog>
    </aside>
  )
}

/**
 * One agent.
 *
 * The row is a button and the menu trigger is a button, so they are siblings
 * rather than nested — a button inside a button is invalid markup that
 * browsers resolve by dropping one of them, and the one they drop is not
 * always the one you expected.
 */
function AgentRow({
  agent,
  selected,
  onSelect,
  onEdit,
  onUnseat,
}: {
  agent: Agent
  selected: boolean
  onSelect: () => void
  onEdit: () => void
  onUnseat: () => void
}) {
  const [menuOpen, setMenuOpen] = useState(false)
  const menuRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!menuOpen) return

    function onPointerDown(event: MouseEvent) {
      if (!menuRef.current?.contains(event.target as Node)) setMenuOpen(false)
    }
    function onEscape(event: KeyboardEvent) {
      if (event.key === 'Escape') setMenuOpen(false)
    }

    document.addEventListener('mousedown', onPointerDown)
    document.addEventListener('keydown', onEscape)
    return () => {
      document.removeEventListener('mousedown', onPointerDown)
      document.removeEventListener('keydown', onEscape)
    }
  }, [menuOpen])

  const color = agentColor(agent.id)

  return (
    <div
      className={`relative flex items-center gap-1 transition-all ${
        selected ? 'mx-2 rounded-xl bg-[#1a1a1f]' : ''
      }`}
    >
      <button
        type="button"
        onClick={onSelect}
        aria-pressed={selected}
        className="flex min-w-0 flex-1 items-center gap-3 rounded-md px-3 py-2.5 text-left transition-all hover:bg-black/[0.04] dark:hover:bg-white/[0.04]"
      >
        <span
          className="flex size-8 shrink-0 items-center justify-center rounded-md text-[11px] font-semibold text-[#111111]"
          style={{ backgroundColor: color }}
          aria-hidden
        >
          {agentInitials(agent.name)}
        </span>
        <span className="flex min-w-0 flex-1 flex-col leading-tight">
          <span
            className={`truncate text-[13px] font-semibold ${
              selected ? 'text-[#FFF41F]' : 'text-[#d4d4d8]'
            }`}
          >
            {agent.name}
          </span>
          <span
            className={`truncate text-[11px] font-light ${
              selected ? 'text-white' : 'text-[#7d7d82]'
            }`}
          >
            {agent.role}
          </span>
        </span>
      </button>

      <button
        type="button"
        aria-label={`Options for ${agent.name}`}
        aria-expanded={menuOpen}
        onClick={() => setMenuOpen((open) => !open)}
        className="mr-2 flex size-6 shrink-0 items-center justify-center rounded-md text-[#7d7d82] transition-colors hover:bg-[#1a1a1a] hover:text-white"
      >
        <MoreVertical className="size-3.5" strokeWidth={1.5} />
      </button>

      {menuOpen && (
        <div
          ref={menuRef}
          className="absolute right-2 top-9 z-50 w-56 rounded-lg border border-[#262629] bg-[#141414] p-1.5 shadow-lg shadow-black/40"
        >
          <button
            type="button"
            onClick={() => {
              onEdit()
              setMenuOpen(false)
            }}
            className="flex w-full items-center gap-2.5 rounded-md px-3 py-2 text-left text-[12.5px] text-[#7d7d82] transition-colors hover:bg-[#1a1a1a] hover:text-white"
          >
            <Pencil className="size-3.5" strokeWidth={1.5} />
            Edit agent
          </button>
          <div className="my-1 border-t border-[#262629]" />
          <button
            type="button"
            onClick={() => {
              onUnseat()
              setMenuOpen(false)
            }}
            className="flex w-full items-center gap-2.5 rounded-md px-3 py-2 text-left text-[12.5px] text-[#ef4444]/80 transition-colors hover:bg-red-950/30"
          >
            <UserMinus className="size-3.5" strokeWidth={1.5} />
            Remove from room
          </button>
        </div>
      )}
    </div>
  )
}
