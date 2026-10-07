'use client'

/**
 * The result of a room's work, where a person can read it and take it away.
 *
 * A tester ran a room, watched the agents talk, and then asked the obvious
 * question: "how do I get the work they performed?" It was there, in a narrow
 * panel, as one message among many, with nothing to copy it by. This is the
 * answer to that question.
 *
 * What counts as "the result" is not one fixed message. The Supervisor's
 * closing message is a summary and is short by design; in a room that writes
 * anything long, the work itself is what the last agent produced. So both are
 * shown: the closing message as context, and the last agent output as the
 * main piece. Earlier outputs sit below, because sometimes the last agent to
 * speak was a reviewer and the thing the user wants is the draft before it.
 */

import { useState } from 'react'
import { Check, Copy, Download, FileText, X } from 'lucide-react'

import { Markdown } from '@/components/markdown'
import { Dialog, DialogClose, DialogContent, DialogDescription, DialogTitle } from '@/components/ui/dialog'
import { agentColor, agentInitials } from '@/lib/agent-appearance'
import type { Message, RoomDetail } from '@/lib/agenlate'
import { copyText, downloadText, fileSlug, transcriptToMarkdown } from '@/lib/export'

/** How the last run ended, when this browser saw it end. */
export type RunOutcome = 'completed' | 'awaiting' | null

export function ResultDialog({
  open,
  onOpenChange,
  room,
  transcript,
  outcome,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  room: RoomDetail
  transcript: Message[]
  outcome: RunOutcome
}) {
  const outputs = transcript.filter((m) => m.emitter === 'agent')
  const final = outputs.at(-1) ?? null
  const earlier = outputs.slice(0, -1).reverse()

  // The Supervisor's closing words, if it has spoken since the last output.
  const last = transcript.at(-1) ?? null
  const closing = last && last.emitter === 'supervisor' && final && last.seq > final.seq ? last : null

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="flex h-[88vh] max-w-3xl flex-col gap-0 p-0">
        <header className="flex shrink-0 items-start justify-between gap-4 border-b border-[#16161a] px-6 py-4">
          <div className="min-w-0">
            <DialogTitle className="text-[17px]">Result</DialogTitle>
            <DialogDescription className="mt-0.5 truncate text-[12.5px]">
              {room.name}
            </DialogDescription>
          </div>
          <div className="flex shrink-0 items-center gap-1.5">
            <button
              type="button"
              onClick={() =>
                downloadText(
                  `${fileSlug(room.name)}-conversation.md`,
                  transcriptToMarkdown(room, transcript),
                )
              }
              className="inline-flex items-center gap-1.5 rounded-md border border-[#262629] px-2.5 py-1.5 text-[12px] font-medium text-[#d4d4d8] transition-colors hover:text-white"
            >
              <FileText className="size-3.5" strokeWidth={1.75} />
              <span>Download whole conversation</span>
            </button>
            <DialogClose
              aria-label="Close result"
              className="flex size-8 items-center justify-center rounded-md text-[#7d7d82] transition-colors hover:bg-[#1a1a1a] hover:text-white"
            >
              <X className="size-4" />
            </DialogClose>
          </div>
        </header>

        <div className="scrollbar-thin min-h-0 flex-1 space-y-6 overflow-y-auto px-6 py-6">
          {!final && (
            <p className="text-[13.5px] font-light leading-relaxed text-[#7d7d82]">
              No agent has produced anything in this room yet. Start a run and the
              work will appear here.
            </p>
          )}

          {closing && (
            <section
              className={`rounded-xl border px-4 py-3.5 ${
                outcome === 'awaiting'
                  ? 'border-[#FFF41F]/25 bg-[#FFF41F]/[0.04]'
                  : 'border-[#16161a] bg-[#141414]'
              }`}
            >
              <div className="mb-1.5 flex items-center justify-between gap-3">
                <h3 className="text-[10.5px] font-semibold uppercase tracking-wider text-[#FFF41F]">
                  {outcome === 'awaiting'
                    ? 'The Supervisor is waiting for your answer'
                    : 'From the Supervisor'}
                </h3>
                <CopyButton text={closing.content} label="Copy" quiet />
              </div>
              <Markdown size="compact">{closing.content}</Markdown>
            </section>
          )}

          {final && (
            <section aria-label="Final output">
              <OutputHeader message={final} room={room} badge="Final output">
                <CopyButton text={final.content} label="Copy" />
                <button
                  type="button"
                  onClick={() =>
                    downloadText(
                      `${fileSlug(room.name)}-${fileSlug(final.emitter_name)}.md`,
                      final.content,
                    )
                  }
                  className="inline-flex items-center gap-1.5 rounded-md border border-[#262629] px-2.5 py-1.5 text-[12px] font-medium text-[#d4d4d8] transition-colors hover:text-white"
                >
                  <Download className="size-3.5" strokeWidth={1.75} />
                  <span>Download</span>
                </button>
              </OutputHeader>
              <div className="mt-4 rounded-xl border border-[#16161a] bg-[#111113] px-5 py-5">
                <Markdown>{final.content}</Markdown>
              </div>
            </section>
          )}

          {earlier.length > 0 && (
            <section>
              <h3 className="mb-2 text-[10.5px] font-semibold uppercase tracking-wider text-[#7d7d82]">
                Earlier work in this room
              </h3>
              <div className="space-y-2">
                {earlier.map((message) => (
                  <details
                    key={message.id}
                    className="group rounded-xl border border-[#16161a] bg-[#141414] open:bg-[#111113]"
                  >
                    <summary className="flex cursor-pointer list-none items-center justify-between gap-3 px-4 py-3">
                      <OutputHeader message={message} room={room} compact />
                      <span className="shrink-0 text-[11.5px] text-[#7d7d82] group-open:hidden">
                        Show
                      </span>
                      <span className="hidden shrink-0 text-[11.5px] text-[#7d7d82] group-open:inline">
                        Hide
                      </span>
                    </summary>
                    <div className="border-t border-[#16161a] px-4 py-4">
                      <div className="mb-3 flex justify-end">
                        <CopyButton text={message.content} label="Copy" quiet />
                      </div>
                      <Markdown size="compact">{message.content}</Markdown>
                    </div>
                  </details>
                ))}
              </div>
            </section>
          )}
        </div>
      </DialogContent>
    </Dialog>
  )
}

function OutputHeader({
  message,
  room,
  badge,
  compact,
  children,
}: {
  message: Message
  room: RoomDetail
  badge?: string
  compact?: boolean
  children?: React.ReactNode
}) {
  // By name, as the transcript does: a message keeps the name it was written
  // under even if the agent has since been renamed or removed.
  const agent = room.agents.find((a) => a.name === message.emitter_name)
  const size = compact ? 'size-7 text-[10px]' : 'size-9 text-[12px]'

  return (
    <div className="flex min-w-0 flex-1 items-center justify-between gap-3">
      <div className="flex min-w-0 items-center gap-3">
        <span
          className={`flex shrink-0 items-center justify-center rounded-lg font-semibold text-[#111111] ${size}`}
          style={{ backgroundColor: agent ? agentColor(agent.id) : '#52525B' }}
          aria-hidden
        >
          {agentInitials(message.emitter_name)}
        </span>
        <div className="min-w-0 leading-tight">
          <p className={`truncate font-semibold text-white ${compact ? 'text-[13px]' : 'text-[15px]'}`}>
            {message.emitter_name}
            {badge && (
              <span className="ml-2 rounded-md bg-[#FFF41F]/10 px-1.5 py-0.5 align-middle text-[10px] font-semibold uppercase tracking-wide text-[#FFF41F]">
                {badge}
              </span>
            )}
          </p>
          <p className="truncate text-[11.5px] font-light text-[#7d7d82]">
            {agent?.role ? `${agent.role} · ` : ''}
            {new Date(message.created_at).toLocaleString(undefined, {
              dateStyle: 'medium',
              timeStyle: 'short',
            })}
          </p>
        </div>
      </div>
      {children && <div className="flex shrink-0 items-center gap-1.5">{children}</div>}
    </div>
  )
}

/**
 * Copies, and says whether it worked.
 *
 * The confirmation matters more than it looks: copying has no visible effect,
 * so without it the only way to find out is to paste somewhere and see.
 */
function CopyButton({ text, label, quiet }: { text: string; label: string; quiet?: boolean }) {
  const [state, setState] = useState<'idle' | 'copied' | 'failed'>('idle')

  async function copy(event: React.MouseEvent) {
    // Inside a <summary> a click would also toggle the section.
    event.preventDefault()
    setState((await copyText(text)) ? 'copied' : 'failed')
    setTimeout(() => setState('idle'), 2000)
  }

  return (
    <button
      type="button"
      onClick={copy}
      className={
        quiet
          ? 'inline-flex items-center gap-1.5 rounded-md px-2 py-1 text-[11.5px] font-medium text-[#a1a1aa] transition-colors hover:bg-[#1a1a1a] hover:text-white'
          : 'inline-flex items-center gap-1.5 rounded-md bg-[#FFF41F] px-3 py-1.5 text-[12px] font-semibold text-[#0A0A0A] transition-all hover:brightness-95'
      }
    >
      {state === 'copied' ? (
        <Check className="size-3.5" strokeWidth={2.5} />
      ) : (
        <Copy className="size-3.5" strokeWidth={1.75} />
      )}
      <span>{state === 'copied' ? 'Copied' : state === 'failed' ? 'Could not copy' : label}</span>
    </button>
  )
}
