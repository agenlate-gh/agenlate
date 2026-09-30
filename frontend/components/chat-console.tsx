'use client'

/**
 * The transcript, and the control that starts a run.
 *
 * Everything here is history: messages already written to the database, plus
 * whatever the current run has added. There is no typewriter effect, because
 * the backend streams whole messages rather than tokens — an agent turn
 * arrives complete or not at all, and animating it character by character
 * would be inventing a progress signal that does not exist. What is real is
 * the line saying who is working right now, which comes from the stream.
 */

import { useEffect, useRef, useState } from 'react'
import { Loader2, MessageCircleQuestion, Play, Send, Square, X } from 'lucide-react'

import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from '@/components/ui/collapsible'
import { agentColor, agentInitials, SUPERVISOR_COLOR } from '@/lib/agent-appearance'
import type { Message, RoomDetail } from '@/lib/agenlate'
import { formatUsd } from '@/lib/format'

export function ChatConsole({
  room,
  transcript,
  running,
  activity,
  error,
  cost,
  awaiting,
  onSend,
  onStop,
  onDismissError,
}: {
  room: RoomDetail
  transcript: Message[]
  running: boolean
  /** What is happening right now, or null between runs. */
  activity: string | null
  error: string | null
  cost: number
  /** The Supervisor's question, when the last run stopped to ask one. */
  awaiting: string | null
  /** Sends what was typed (possibly nothing) and runs the room. */
  onSend: (content: string) => Promise<void>
  onStop: () => void
  onDismissError: () => void
}) {
  const feedRef = useRef<HTMLDivElement>(null)
  const [draft, setDraft] = useState('')
  const [sending, setSending] = useState(false)

  async function submit() {
    if (running || sending) return
    setSending(true)
    try {
      await onSend(draft)
      setDraft('')
    } finally {
      setSending(false)
    }
  }

  // Follows the run. Only while something is happening — scrolling the feed
  // out from under someone reading old messages is worse than not following.
  useEffect(() => {
    if (running) feedRef.current?.scrollTo({ top: feedRef.current.scrollHeight })
  }, [transcript, running])

  const paused = room.status === 'paused'
  const empty = room.agents.length === 0

  return (
    <section className="flex h-full w-[420px] shrink-0 flex-col border-l border-[#16161a] bg-panel">
      <Collapsible defaultOpen className="flex min-h-0 flex-1 flex-col">
        <CollapsibleTrigger className="group flex w-full shrink-0 items-center justify-between border-b border-[#16161a] px-5 py-3 text-left transition-colors hover:bg-[#141414]">
          <span className="flex items-center gap-2">
            <span className="text-[12px] font-semibold uppercase tracking-wide text-white">
              Live Orchestration
            </span>
          </span>
          <span className="flex items-center gap-2">
            {running && (
              <span className="flex items-center gap-1.5">
                <span className="size-1.5 rounded-full bg-green-500 pulse-dot" aria-hidden />
                <span className="text-[10px] font-medium uppercase tracking-wider text-[#d4d4d8]">
                  Running
                </span>
              </span>
            )}
            {cost > 0 && (
              <span className="rounded-md border border-[#16161a] bg-[#1a1a1a] px-2 py-0.5 font-mono text-[10px] font-light tabular-nums text-[#d4d4d8]">
                {formatUsd(cost)}
              </span>
            )}
          </span>
        </CollapsibleTrigger>

        <CollapsibleContent className="flex min-h-0 flex-1 flex-col">
          <div
            ref={feedRef}
            className="scrollbar-thin flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto px-4 py-5"
          >
            {transcript.length === 0 && !running && (
              <p className="text-[12.5px] font-light leading-relaxed text-[#7d7d82]">
                Nothing has happened in this room yet. Start a run and the
                Supervisor will work through the objective with the agents you
                have seated.
              </p>
            )}

            {transcript.map((message) => (
              <MessageBlock key={message.id} message={message} room={room} />
            ))}

            {activity && (
              <p className="flex items-center gap-2 text-[12px] font-light text-[#7d7d82]">
                <Loader2 className="size-3.5 animate-spin" />
                {activity}
              </p>
            )}
          </div>

          {error && (
            <div
              role="alert"
              className="flex items-start justify-between gap-3 border-t border-red-500/20 bg-red-950/20 px-5 py-3"
            >
              <p className="text-[12px] font-light leading-relaxed text-[#FCA5A5]">
                {error}
              </p>
              <button
                type="button"
                onClick={onDismissError}
                aria-label="Dismiss"
                className="shrink-0 text-[#FCA5A5] transition-opacity hover:opacity-70"
              >
                <X className="size-3.5" />
              </button>
            </div>
          )}

          {awaiting && !running && (
            <div className="shrink-0 border-t border-[#FFF41F]/20 bg-[#FFF41F]/[0.04] px-5 py-3">
              <p className="flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-wider text-[#FFF41F]">
                <MessageCircleQuestion className="size-3.5" strokeWidth={2} />
                The Supervisor needs your input
              </p>
              <p className="mt-1 whitespace-pre-wrap text-[12.5px] font-light leading-relaxed text-[#d4d4d8]">
                {awaiting}
              </p>
            </div>
          )}

          <div className="shrink-0 border-t border-[#16161a] px-5 py-4">
            {running ? (
              <button
                type="button"
                onClick={onStop}
                className="flex w-full items-center justify-center gap-2 rounded-lg border border-[#262629] px-4 py-2.5 text-[13px] font-semibold text-[#d4d4d8] transition-colors hover:border-red-500/40 hover:text-red-400"
              >
                <Square className="size-3.5" strokeWidth={2} />
                Stop the run
              </button>
            ) : (
              <form
                onSubmit={(event) => {
                  event.preventDefault()
                  void submit()
                }}
                className="flex flex-col gap-2"
              >
                <textarea
                  value={draft}
                  onChange={(event) => setDraft(event.target.value)}
                  onKeyDown={(event) => {
                    // Enter sends, Shift+Enter starts a new line — the
                    // convention in every chat box people already use.
                    if (event.key === 'Enter' && !event.shiftKey) {
                      event.preventDefault()
                      void submit()
                    }
                  }}
                  disabled={paused || empty || sending}
                  rows={2}
                  maxLength={4000}
                  aria-label="Message to the team"
                  placeholder={
                    awaiting
                      ? 'Answer the Supervisor…'
                      : 'Give the team direction, or leave empty to just run…'
                  }
                  className="w-full resize-none rounded-lg border border-[#16161a] bg-[#141414] px-3.5 py-2.5 text-[13px] font-light leading-relaxed text-white outline-none transition-colors placeholder:text-[#52525B] focus:border-[#FFF41F]/50 disabled:opacity-50"
                />
                <button
                  type="submit"
                  disabled={paused || empty || sending}
                  className="flex w-full items-center justify-center gap-2 rounded-lg bg-[#FFF41F] px-4 py-2.5 text-[13px] font-semibold text-[#0A0A0A] transition-all hover:brightness-95 disabled:cursor-not-allowed disabled:opacity-50"
                >
                  {sending ? (
                    <Loader2 className="size-3.5 animate-spin" />
                  ) : draft.trim() ? (
                    <Send className="size-3.5" strokeWidth={2.5} />
                  ) : (
                    <Play className="size-3.5" strokeWidth={2.5} />
                  )}
                  {draft.trim()
                    ? 'Send and continue'
                    : transcript.length === 0
                      ? 'Start the run'
                      : 'Continue the run'}
                </button>
              </form>
            )}

            <p className="mt-2 text-center text-[11px] font-light leading-relaxed text-[#7d7d82]">
              {paused
                ? 'This room is paused. Resume it on the left to run it.'
                : empty
                  ? 'Seat at least one agent before running.'
                  : running
                    ? 'You can reply once the run pauses or finishes.'
                    : 'Runs use your own OpenRouter key and spend your credit.'}
            </p>
          </div>
        </CollapsibleContent>
      </Collapsible>
    </section>
  )
}

/**
 * One message.
 *
 * `emitter_name` comes from the database rather than being looked up here, so
 * a message keeps the name it was written under even after the agent has been
 * renamed or removed from the room — a transcript that rewrites itself when
 * the roster changes is not a record of what happened.
 */
function MessageBlock({ message, room }: { message: Message; room: RoomDetail }) {
  if (message.emitter === 'system') {
    return (
      <div className="my-1 flex items-center gap-3">
        <span className="h-px flex-1 bg-[#16161a]" />
        <span className="rounded-full border border-[#16161a] bg-[#1a1a1a] px-3 py-1 text-[11px] font-light text-[#7d7d82]">
          {message.content}
        </span>
        <span className="h-px flex-1 bg-[#16161a]" />
      </div>
    )
  }

  // The user's own words, shaped like a sent message rather than another
  // speaker at the table: they are direction to the team, not a turn in it.
  if (message.emitter === 'user') {
    return (
      <div className="flex flex-col items-end gap-1">
        <span className="text-[10px] font-medium uppercase tracking-wide text-[#7d7d82]">
          You
        </span>
        <p className="max-w-[85%] whitespace-pre-wrap rounded-2xl rounded-br-sm bg-[#2F2F33] px-3.5 py-2.5 text-[13px] font-light leading-relaxed text-white">
          {message.content}
        </p>
      </div>
    )
  }

  const isSupervisor = message.emitter === 'supervisor'
  const agent = room.agents.find((a) => a.name === message.emitter_name)
  const color = isSupervisor
    ? SUPERVISOR_COLOR
    : agent
      ? agentColor(agent.id)
      : '#52525B'

  return (
    <div className="flex gap-3">
      <span
        className="mt-0.5 flex size-9 shrink-0 items-center justify-center rounded-lg text-[12px] font-semibold text-[#111111]"
        style={{ backgroundColor: color }}
        aria-hidden
      >
        {agentInitials(message.emitter_name)}
      </span>
      <div className="min-w-0 flex-1">
        <div className="mb-1.5 flex items-start justify-between gap-3">
          <div className="flex flex-col leading-tight">
            <span className="text-[14px] font-semibold text-white">
              {message.emitter_name}
            </span>
            <span className="text-[11px] font-medium uppercase tracking-wide text-[#7d7d82]">
              {isSupervisor ? 'Orchestration' : (agent?.role ?? message.emitter)}
            </span>
          </div>
          <span className="shrink-0 text-[11px] font-light text-[#7d7d82]">
            {new Date(message.created_at).toLocaleTimeString(undefined, {
              hour: '2-digit',
              minute: '2-digit',
            })}
          </span>
        </div>
        <p className="whitespace-pre-wrap text-[13.5px] font-light leading-relaxed text-[#8e8e93]">
          {message.content}
        </p>
      </div>
    </div>
  )
}
