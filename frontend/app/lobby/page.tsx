'use client'

/**
 * The lobby: every room this user owns, and what each has cost.
 *
 * Two requests rather than one per room. The rooms endpoint returns each
 * room's roster with it, and spending comes back for all rooms at once, so the
 * first screen after signing in is two round trips regardless of how many
 * rooms there are.
 */

import { useCallback, useEffect, useState } from 'react'
import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { LayoutDashboard, Loader2, Plus, Sparkles, Trash2 } from 'lucide-react'

import { RequireAuth } from '@/components/auth-provider'
import { LobbySidebar } from '@/components/lobby-sidebar'
import { ObjectiveHelper } from '@/components/objective-helper'
import { TopNavbar } from '@/components/top-navbar'
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogTitle,
} from '@/components/ui/dialog'
import { Switch } from '@/components/ui/switch'
import { agentColor, agentInitials } from '@/lib/agent-appearance'
import type { RoomDetail, RoomUsage } from '@/lib/agenlate'
import { rooms as roomsApi, usage as usageApi } from '@/lib/agenlate'
import { ApiError } from '@/lib/api'
import { formatUsd } from '@/lib/format'

export default function LobbyPage() {
  return (
    <RequireAuth>
      <Lobby />
    </RequireAuth>
  )
}

function Lobby() {
  const router = useRouter()

  const [rooms, setRooms] = useState<RoomDetail[] | null>(null)
  const [spend, setSpend] = useState<Record<string, RoomUsage>>({})
  const [error, setError] = useState<string | null>(null)
  const [creating, setCreating] = useState(false)
  const [deleting, setDeleting] = useState<RoomDetail | null>(null)

  const load = useCallback(async () => {
    setError(null)
    try {
      // Spending is allowed to fail on its own. A room list with no costs is
      // still a usable lobby; an empty screen because the meter is down is not.
      const [list, byRoom] = await Promise.all([
        roomsApi.list(),
        usageApi.byRoom().catch(() => [] as RoomUsage[]),
      ])
      setRooms(list)
      setSpend(Object.fromEntries(byRoom.map((entry) => [entry.room_id, entry])))
    } catch (cause) {
      setError(
        cause instanceof ApiError ? cause.message : 'Could not load your rooms.',
      )
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  /**
   * Flips a room between active and paused.
   *
   * Applied locally first. The switch is the one control on this screen a user
   * clicks and immediately looks at, and a round trip before it moves reads as
   * a broken control. If the request fails the room goes back to where it was
   * and the failure is shown, so the screen never claims a state the server
   * does not have.
   */
  async function toggle(room: RoomDetail) {
    const next = room.status === 'active' ? 'paused' : 'active'
    setRooms((prev) =>
      prev?.map((r) => (r.id === room.id ? { ...r, status: next } : r)) ?? prev,
    )
    try {
      await roomsApi.setStatus(room.id, next)
    } catch (cause) {
      setRooms((prev) =>
        prev?.map((r) => (r.id === room.id ? { ...r, status: room.status } : r)) ??
        prev,
      )
      setError(
        cause instanceof ApiError
          ? cause.message
          : `Could not ${next === 'paused' ? 'pause' : 'resume'} this room.`,
      )
    }
  }

  return (
    <div className="flex h-screen max-h-screen w-full flex-col overflow-hidden bg-[#0a0a0a] text-foreground">
      <TopNavbar />

      <div className="flex min-h-0 flex-1 pt-[56px]">
        <div className="hidden md:flex">
          <LobbySidebar />
        </div>

        <div className="flex min-w-0 flex-1 flex-col gap-5 overflow-y-auto pl-16 pr-6 pt-12 pb-6">
          <div className="w-full max-w-5xl">
            <div className="mb-10">
              <h1 className="flex items-center gap-2.5 text-[20px] font-semibold tracking-tight text-[#111111] dark:text-white">
                <LayoutDashboard
                  className="size-5 text-[#7A6F00] dark:text-[#FFF41F]"
                  strokeWidth={1.5}
                />
                Multi-Agent Workspaces
              </h1>

              <p className="mt-1.5 max-w-2xl text-[13px] font-light leading-relaxed text-[#52525B] dark:text-[#7d7d82]">
                Configure and manage your autonomous multi-agent environments with
                real-time orchestration loops and live deployment tracking.
              </p>
            </div>

            {error && (
              <div
                role="alert"
                className="mb-6 flex items-center justify-between gap-4 rounded-lg border border-red-500/20 bg-red-950/20 px-4 py-3"
              >
                <p className="text-[13px] font-light text-[#FCA5A5]">{error}</p>
                <button
                  type="button"
                  onClick={() => void load()}
                  className="shrink-0 text-[12px] font-medium text-[#FFF41F] transition-opacity hover:opacity-80"
                >
                  Try again
                </button>
              </div>
            )}

            <section>
              <h2 className="mb-4 text-[16px] font-semibold tracking-tight text-[#111111] dark:text-white">
                Active Agent Workspaces
              </h2>

              <div className="grid grid-cols-1 gap-6 md:grid-cols-2">
                <button
                  type="button"
                  onClick={() => setCreating(true)}
                  className="group flex flex-col items-center justify-center gap-4 rounded-xl border border-dashed border-[#16161a] px-4 py-10 transition-all hover:border-[#7A6F00]/30 hover:bg-black/[0.02] dark:border-[#16161a] dark:hover:border-[#FFF41F]/20 dark:hover:bg-white/[0.02]"
                >
                  <span className="flex size-12 shrink-0 items-center justify-center rounded-xl bg-[#FFF41F]/20 text-[#7A6F00] transition-colors group-hover:bg-[#FFF41F]/30 dark:bg-[#FFF41F]/10 dark:text-[#FFF41F] dark:group-hover:bg-[#FFF41F]/20">
                    <Plus className="size-6" strokeWidth={2.5} />
                  </span>
                  <span className="text-center text-[13px] font-semibold text-[#52525B] transition-colors group-hover:text-[#7A6F00] dark:text-[#7d7d82] dark:group-hover:text-[#FFF41F]">
                    Deploy New Multi-Agent Room
                  </span>
                </button>

                {rooms === null && !error
                  ? [0, 1].map((i) => <RoomCardSkeleton key={i} />)
                  : rooms?.map((room) => (
                      <RoomCard
                        key={room.id}
                        room={room}
                        usage={spend[room.id]}
                        onToggle={() => void toggle(room)}
                        onDelete={() => setDeleting(room)}
                      />
                    ))}
              </div>

              {rooms?.length === 0 && (
                <p className="mt-6 text-[13px] font-light leading-relaxed text-[#52525B] dark:text-[#7d7d82]">
                  No rooms yet. A room is a shared objective and the agents working
                  on it — create one to get started.
                </p>
              )}
            </section>
          </div>
        </div>
      </div>

      <CreateRoomDialog
        open={creating}
        onOpenChange={setCreating}
        onCreated={(room) => router.push(`/rooms/${room.id}`)}
      />

      <DeleteRoomDialog
        room={deleting}
        onOpenChange={(open) => !open && setDeleting(null)}
        onDeleted={(id) => {
          setRooms((prev) => prev?.filter((r) => r.id !== id) ?? prev)
          setDeleting(null)
        }}
      />
    </div>
  )
}

// -- cards ------------------------------------------------------------------

const CARD_CLASS =
  'flex flex-col rounded-xl border border-[#16161a] bg-[#141414] px-5 pb-5 pt-4 transition-all hover:shadow-sm dark:border-[#16161a] dark:bg-[#141414] dark:hover:bg-[#121214]'

function RoomCard({
  room,
  usage,
  onToggle,
  onDelete,
}: {
  room: RoomDetail
  usage: RoomUsage | undefined
  onToggle: () => void
  onDelete: () => void
}) {
  const active = room.status === 'active'
  // A room with no recorded usage is absent from the spending response, which
  // means nothing spent rather than unknown.
  const cost = usage?.cost_usd ?? 0

  return (
    <div className={CARD_CLASS}>
      <div className="mb-3 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span
            className={`size-2 rounded-full ${active ? 'bg-green-500 pulse-dot' : 'bg-[#A1A1AA] dark:bg-[#7d7d82]'}`}
            aria-hidden
          />
          <span className="text-[11px] font-light text-[#52525B] dark:text-[#7d7d82]">
            {active ? 'Active' : 'Paused'}
          </span>
        </div>
        <div className="flex items-center gap-2">
          <Switch
            checked={active}
            onCheckedChange={onToggle}
            aria-label={active ? `Pause ${room.name}` : `Resume ${room.name}`}
          />
          <button
            type="button"
            onClick={onDelete}
            aria-label={`Delete ${room.name}`}
            className="flex size-7 items-center justify-center rounded-md text-[#71717A] transition-colors hover:bg-[#EBEBEB] hover:text-[#DC2626] dark:text-[#7d7d82] dark:hover:bg-[#1a1a1a] dark:hover:text-red-400"
          >
            <Trash2 className="size-3.5" strokeWidth={1.5} />
          </button>
        </div>
      </div>

      <h3 className="mb-4 text-[15px] font-semibold tracking-tight text-[#111111] dark:text-white">
        {room.name}
      </h3>

      <div className="mb-4 flex items-center">
        {room.agents.length === 0 ? (
          <span className="text-[12px] font-light text-[#52525B] dark:text-[#7d7d82]">
            No agents seated yet
          </span>
        ) : (
          <div className="flex -space-x-2">
            {room.agents.map((agent, index) => (
              <span
                key={agent.id}
                title={`${agent.name} — ${agent.role}`}
                className="relative flex size-8 items-center justify-center rounded-full text-[10px] font-bold text-[#111111]"
                style={{
                  backgroundColor: agentColor(agent.id),
                  zIndex: room.agents.length - index,
                }}
              >
                {agentInitials(agent.name)}
              </span>
            ))}
          </div>
        )}
      </div>

      <div className="mb-4 inline-flex items-center gap-2">
        <span className="text-[10px] font-medium uppercase tracking-wider text-[#52525B] dark:text-[#7d7d82]">
          Room Cost
        </span>
        <span className="font-mono text-[13px] font-semibold tabular-nums text-[#111111] dark:text-white">
          {usage && !usage.cost_is_complete && '≥ '}
          {formatUsd(cost)}
        </span>
        <span className="text-[10px] font-light text-[#52525B] dark:text-[#7d7d82]">
          USD
        </span>
      </div>

      <div className="mt-auto">
        <Link
          href={`/rooms/${room.id}`}
          className="inline-flex items-center gap-1.5 text-[13px] font-medium text-[#52525B] transition-colors hover:text-[#7A6F00] dark:text-[#7d7d82] dark:hover:text-[#FFF41F]"
        >
          Enter Room →
        </Link>
      </div>
    </div>
  )
}

/** Holds the grid's shape while the first request is in flight. */
function RoomCardSkeleton() {
  return (
    <div className={`${CARD_CLASS} animate-pulse`} aria-hidden>
      <div className="mb-3 flex items-center justify-between">
        <span className="h-2 w-16 rounded-full bg-[#1f1f23]" />
        <span className="h-5 w-9 rounded-full bg-[#1f1f23]" />
      </div>
      <span className="mb-4 h-4 w-2/3 rounded bg-[#1f1f23]" />
      <span className="mb-4 h-8 w-24 rounded-full bg-[#1f1f23]" />
      <span className="h-3 w-28 rounded bg-[#1f1f23]" />
    </div>
  )
}

// -- dialogs ----------------------------------------------------------------

const FIELD_CLASS =
  'w-full rounded-lg border border-[#16161a] bg-[#0f0f0f] px-3.5 py-2.5 text-[14px] text-white outline-none transition-colors placeholder:text-[#52525B] focus:border-[#FFF41F]/50'

const LABEL_CLASS =
  'text-[11px] font-medium uppercase tracking-wider text-[#7d7d82]'

function CreateRoomDialog({
  open,
  onOpenChange,
  onCreated,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  onCreated: (room: RoomDetail) => void
}) {
  const [name, setName] = useState('')
  const [objective, setObjective] = useState('')
  const [helping, setHelping] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function submit(event: React.FormEvent) {
    event.preventDefault()
    setBusy(true)
    setError(null)
    try {
      // No agents yet. Seating them happens in the room, where the user can
      // see what each one is for — asking here would mean choosing a roster
      // before deciding what the room is even doing.
      const room = await roomsApi.create({
        name: name.trim(),
        objective: objective.trim(),
        agent_ids: [],
      })
      onCreated(room)
    } catch (cause) {
      setError(
        cause instanceof ApiError ? cause.message : 'Could not create the room.',
      )
      setBusy(false)
    }
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        onOpenChange(next)
        if (!next) {
          setName('')
          setObjective('')
          setHelping(false)
          setError(null)
        }
      }}
    >
      <DialogContent className={helping ? 'max-w-xl' : undefined}>
        <DialogTitle>New room</DialogTitle>
        <DialogDescription>
          A room is one objective and the agents working on it. Say what it should
          achieve — the Supervisor works from this.
        </DialogDescription>

        <form onSubmit={submit} className="mt-5 flex flex-col gap-3">
          <label className="flex flex-col gap-1.5">
            <span className={LABEL_CLASS}>Name</span>
            <input
              value={name}
              onChange={(event) => setName(event.target.value)}
              required
              maxLength={200}
              autoFocus
              className={FIELD_CLASS}
              placeholder="Production deployment review"
            />
          </label>

          <div className="flex flex-col gap-1.5">
            <div className="flex items-center justify-between">
              <label htmlFor="room-objective" className={LABEL_CLASS}>
                Objective
              </label>
              <button
                type="button"
                onClick={() => setHelping((open) => !open)}
                aria-expanded={helping}
                className="inline-flex items-center gap-1 text-[11.5px] font-medium text-[#FFF41F] transition-opacity hover:opacity-80"
              >
                <Sparkles className="size-3.5" />
                {helping ? 'Hide helper' : 'Write it with AI'}
              </button>
            </div>
            <textarea
              id="room-objective"
              value={objective}
              onChange={(event) => setObjective(event.target.value)}
              required
              maxLength={4000}
              rows={4}
              className={`${FIELD_CLASS} resize-none leading-relaxed`}
              placeholder="Review the release candidate for blocking issues and report what must be fixed before it ships."
            />
          </div>

          {helping && (
            <ObjectiveHelper
              name={name}
              objective={objective}
              onUse={(written, suggestedName) => {
                setObjective(written)
                // Only fill an empty name. Overwriting one the user typed
                // would undo a decision they already made.
                if (suggestedName && !name.trim()) setName(suggestedName)
              }}
            />
          )}

          {error && (
            <p role="alert" className="text-[12px] font-light text-[#FCA5A5]">
              {error}
            </p>
          )}

          <div className="mt-2 flex justify-end gap-2">
            <DialogClose className="rounded-lg px-4 py-2.5 text-[13px] font-medium text-[#7d7d82] transition-colors hover:text-white">
              Cancel
            </DialogClose>
            <button
              type="submit"
              disabled={busy || !name.trim() || !objective.trim()}
              className="inline-flex items-center justify-center gap-2 rounded-lg bg-[#FFF41F] px-4 py-2.5 text-[13px] font-semibold text-[#0A0A0A] transition-all hover:brightness-95 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {busy && <Loader2 className="size-3.5 animate-spin" />}
              Create room
            </button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  )
}

function DeleteRoomDialog({
  room,
  onOpenChange,
  onDeleted,
}: {
  room: RoomDetail | null
  onOpenChange: (open: boolean) => void
  onDeleted: (id: string) => void
}) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function confirm() {
    if (!room) return
    setBusy(true)
    setError(null)
    try {
      await roomsApi.remove(room.id)
      onDeleted(room.id)
    } catch (cause) {
      setError(
        cause instanceof ApiError ? cause.message : 'Could not delete the room.',
      )
    } finally {
      setBusy(false)
    }
  }

  return (
    <Dialog
      open={room !== null}
      onOpenChange={(next) => {
        onOpenChange(next)
        if (!next) setError(null)
      }}
    >
      <DialogContent>
        <DialogTitle>Delete {room?.name}?</DialogTitle>
        <DialogDescription>
          This deletes the room and its whole transcript. The agents in it are
          yours and stay — only this room goes. It cannot be undone.
          {' '}
          To stop it running without losing anything, pause it instead.
        </DialogDescription>

        {error && (
          <p role="alert" className="mt-3 text-[12px] font-light text-[#FCA5A5]">
            {error}
          </p>
        )}

        <div className="mt-5 flex justify-end gap-2">
          <DialogClose className="rounded-lg px-4 py-2.5 text-[13px] font-medium text-[#7d7d82] transition-colors hover:text-white">
            Cancel
          </DialogClose>
          <button
            type="button"
            onClick={() => void confirm()}
            disabled={busy}
            className="inline-flex items-center justify-center gap-2 rounded-lg bg-red-600 px-4 py-2.5 text-[13px] font-semibold text-white transition-all hover:bg-red-500 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {busy && <Loader2 className="size-3.5 animate-spin" />}
            Delete room
          </button>
        </div>
      </DialogContent>
    </Dialog>
  )
}
