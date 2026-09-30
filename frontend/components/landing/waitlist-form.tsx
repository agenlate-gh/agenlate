'use client'

/**
 * The waitlist form on the landing page.
 *
 * One field, because every extra one costs signups and none of them is needed
 * to send someone an invite. The confirmation replaces the form rather than
 * sitting under it, so there is no second submit to wonder about.
 */

import { useState } from 'react'
import { ArrowRight, Check, Loader2 } from 'lucide-react'

import { accounts } from '@/lib/agenlate'
import { ApiError } from '@/lib/api'

export function WaitlistForm({ source = 'landing' }: { source?: string }) {
  const [email, setEmail] = useState('')
  // The trap. Hidden from people and from screen readers; only a bot that
  // fills every field it finds ever puts something here.
  const [website, setWebsite] = useState('')
  const [state, setState] = useState<'idle' | 'sending' | 'done'>('idle')
  const [message, setMessage] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  async function submit(event: React.FormEvent) {
    event.preventDefault()
    setState('sending')
    setError(null)
    try {
      const reply = await accounts.joinWaitlist({ email, source, website })
      setMessage(reply.message)
      setState('done')
    } catch (cause) {
      setError(
        cause instanceof ApiError ? cause.message : 'Something went wrong. Try again.',
      )
      setState('idle')
    }
  }

  if (state === 'done') {
    return (
      <p
        role="status"
        className="flex items-center gap-2.5 rounded-xl border border-[#FFF41F]/25 bg-[#FFF41F]/[0.06] px-4 py-3.5 text-[14px] text-white"
      >
        <span className="flex size-6 shrink-0 items-center justify-center rounded-full bg-[#FFF41F] text-[#0A0A0A]">
          <Check className="size-3.5" strokeWidth={3} />
        </span>
        {message}
      </p>
    )
  }

  return (
    <form onSubmit={submit} className="w-full">
      <div className="flex flex-col gap-2 sm:flex-row">
        <label htmlFor={`waitlist-email-${source}`} className="sr-only">
          Email address
        </label>
        <input
          id={`waitlist-email-${source}`}
          type="email"
          required
          autoComplete="email"
          value={email}
          onChange={(event) => setEmail(event.target.value)}
          placeholder="you@company.com"
          className="min-w-0 flex-1 rounded-xl border border-[#262629] bg-[#141414] px-4 py-3.5 text-[15px] text-white outline-none transition-colors placeholder:text-[#52525B] focus:border-[#FFF41F]/60"
        />
        <div aria-hidden="true" className="absolute -left-[9999px] h-0 w-0 overflow-hidden">
          <label>
            Website
            <input
              tabIndex={-1}
              autoComplete="off"
              value={website}
              onChange={(event) => setWebsite(event.target.value)}
            />
          </label>
        </div>
        <button
          type="submit"
          disabled={state === 'sending'}
          className="inline-flex items-center justify-center gap-2 rounded-xl bg-[#FFF41F] px-5 py-3.5 text-[15px] font-bold text-[#0A0A0A] transition-all hover:brightness-95 disabled:opacity-60"
        >
          {state === 'sending' ? (
            <Loader2 className="size-4 animate-spin" />
          ) : (
            <>
              Join the waitlist
              <ArrowRight className="size-4" strokeWidth={2.5} />
            </>
          )}
        </button>
      </div>
      {error && (
        <p role="alert" className="mt-2 text-[13px] text-[#FCA5A5]">
          {error}
        </p>
      )}
    </form>
  )
}
