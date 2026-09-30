'use client'

/**
 * Writes a room's objective from a plain description.
 *
 * The objective is the one field a new user must fill in before anything
 * happens, and the Supervisor reads it before every decision. People who know
 * exactly what they want still rarely write it the way a coordinator needs —
 * what the finished result is and how to tell it is finished — and would
 * otherwise go and have another chat assistant write it for them.
 *
 * Nothing here is saved. A draft goes into the form only when the user presses
 * "Use this", and the room is created only when they submit the form: what the
 * team works toward is always something a person chose.
 */

import { useEffect, useRef, useState } from 'react'
import Link from 'next/link'
import { Check, Loader2, Send, Sparkles } from 'lucide-react'

import type { BuilderMessage } from '@/lib/agenlate'
import { rooms as roomsApi } from '@/lib/agenlate'
import { ApiError } from '@/lib/api'
import { readKey } from '@/lib/byok'
import { DEFAULT_BUILDER_MODEL } from '@/lib/models'

type Turn = BuilderMessage & { draft?: string | null; name?: string | null }

export function ObjectiveHelper({
  name,
  objective,
  onUse,
}: {
  /** What the form holds now, so a revision keeps what the user did not change. */
  name: string
  objective: string
  onUse: (objective: string, suggestedName: string | null) => void
}) {
  const [turns, setTurns] = useState<Turn[]>([])
  const [draft, setDraft] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [usedIndex, setUsedIndex] = useState<number | null>(null)
  const [hasKey, setHasKey] = useState(true)
  const feedRef = useRef<HTMLDivElement>(null)

  // Storage is read after mount: the server renders this first and has none.
  useEffect(() => setHasKey(Boolean(readKey())), [])

  useEffect(() => {
    feedRef.current?.scrollTo({ top: feedRef.current.scrollHeight })
  }, [turns, busy])

  async function send() {
    const text = draft.trim()
    const apiKey = readKey()
    if (!text || busy || !apiKey) return

    const conversation: BuilderMessage[] = [
      ...turns.map(({ role, content }) => ({ role, content })),
      { role: 'user', content: text },
    ]
    setTurns((prev) => [...prev, { role: 'user', content: text }])
    setDraft('')
    setBusy(true)
    setError(null)

    try {
      const reply = await roomsApi.draftObjective({
        api_key: apiKey,
        conversation,
        name: name.trim() || null,
        objective: objective.trim() || null,
        model: DEFAULT_BUILDER_MODEL,
      })
      setTurns((prev) => [
        ...prev,
        {
          role: 'assistant',
          content: reply.reply,
          draft: reply.objective,
          name: reply.name ?? null,
        },
      ])
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : 'The helper did not reply.')
    } finally {
      setBusy(false)
    }
  }

  if (!hasKey) {
    return (
      <p className="rounded-lg border border-[#16161a] bg-[#0f0f0f] px-3.5 py-3 text-[12px] font-light leading-relaxed text-[#7d7d82]">
        The writing helper runs on your own OpenRouter key.{' '}
        <Link href="/byok" className="font-medium text-[#FFF41F] hover:opacity-80">
          Add your key
        </Link>{' '}
        to use it, or write the objective yourself above.
      </p>
    )
  }

  return (
    <div className="flex flex-col rounded-lg border border-[#FFF41F]/15 bg-[#0f0f0f]">
      <div
        ref={feedRef}
        className="scrollbar-thin flex max-h-56 flex-col gap-2.5 overflow-y-auto px-3.5 py-3"
      >
        {turns.length === 0 && (
          <p className="flex items-start gap-2 text-[12px] font-light leading-relaxed text-[#d4d4d8]">
            <Sparkles className="mt-0.5 size-3.5 shrink-0 text-[#FFF41F]" />
            Tell me what you want this room to achieve, in your own words. I&apos;ll
            write the objective and you decide whether to use it.
          </p>
        )}

        {turns.map((turn, index) =>
          turn.role === 'user' ? (
            <p
              key={index}
              className="max-w-[85%] self-end rounded-2xl rounded-br-sm bg-[#2F2F33] px-3 py-2 text-[12px] font-light leading-relaxed text-white"
            >
              {turn.content}
            </p>
          ) : (
            <div key={index} className="flex flex-col gap-1.5">
              <p className="text-[12px] font-light leading-relaxed text-[#d4d4d8]">
                {turn.content}
              </p>
              {turn.draft && (
                <div className="rounded-md border border-[#16161a] bg-[#141414] px-3 py-2.5">
                  {turn.name && (
                    <p className="mb-1 text-[10px] font-medium uppercase tracking-wider text-[#7d7d82]">
                      Suggested name: <span className="text-[#d4d4d8]">{turn.name}</span>
                    </p>
                  )}
                  <p className="whitespace-pre-wrap text-[12px] font-light leading-relaxed text-[#d4d4d8]">
                    {turn.draft}
                  </p>
                  <button
                    type="button"
                    onClick={() => {
                      onUse(turn.draft!, turn.name ?? null)
                      setUsedIndex(index)
                    }}
                    className="mt-2 inline-flex items-center gap-1.5 rounded-md bg-[#FFF41F] px-2.5 py-1.5 text-[11.5px] font-semibold text-[#0A0A0A] transition-all hover:brightness-95"
                  >
                    <Check className="size-3.5" strokeWidth={2.5} />
                    {usedIndex === index ? 'Used' : 'Use this'}
                  </button>
                </div>
              )}
            </div>
          ),
        )}

        {busy && (
          <p className="flex items-center gap-2 text-[11.5px] font-light text-[#7d7d82]">
            <Loader2 className="size-3.5 animate-spin" />
            Writing…
          </p>
        )}
        {error && (
          <p role="alert" className="text-[11.5px] font-light text-[#FCA5A5]">
            {error}
          </p>
        )}
      </div>

      <div className="flex items-center gap-2 border-t border-[#16161a] px-2.5 py-2">
        <input
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          onKeyDown={(event) => {
            // Inside the room form: Enter here must send to the helper, not
            // submit the form and create a room from a half-written objective.
            if (event.key === 'Enter') {
              event.preventDefault()
              void send()
            }
          }}
          maxLength={4000}
          aria-label="Describe what the room should achieve"
          placeholder={turns.length ? 'Ask for a change…' : 'e.g. a weekly summary of AI news for my team'}
          className="min-w-0 flex-1 bg-transparent px-1.5 py-1.5 text-[12.5px] font-light text-white outline-none placeholder:text-[#52525B]"
        />
        <button
          type="button"
          onClick={() => void send()}
          disabled={busy || !draft.trim()}
          aria-label="Send to the writing helper"
          className="flex size-8 shrink-0 items-center justify-center rounded-md bg-[#FFF41F] text-[#0A0A0A] transition-all hover:brightness-95 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {busy ? <Loader2 className="size-3.5 animate-spin" /> : <Send className="size-3.5" />}
        </button>
      </div>
    </div>
  )
}
