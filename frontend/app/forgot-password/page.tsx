'use client'

/**
 * Asking for a password reset link.
 *
 * Supabase sends the email through our own mail service and the link brings
 * the person to /reset-password, signed in for long enough to choose a new
 * password.
 *
 * The answer is the same whether or not the address has an account. Saying
 * "no account with that email" would let anyone find out who uses Agenlate by
 * typing addresses into this form.
 */

import { useEffect, useState } from 'react'
import Link from 'next/link'
import { Loader2, MailCheck, KeyRound } from 'lucide-react'

import { supabase } from '@/lib/supabase'

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState('')
  const [busy, setBusy] = useState(false)
  const [sent, setSent] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Carried over from the sign-in form, so nobody types their address twice.
  useEffect(() => {
    const given = new URLSearchParams(window.location.search).get('email')
    if (given) setEmail(given)
  }, [])

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault()
    setError(null)
    setBusy(true)
    try {
      const { error } = await supabase.auth.resetPasswordForEmail(email.trim(), {
        redirectTo: `${window.location.origin}/reset-password`,
      })
      if (error) {
        // Only a limit is worth reporting: anything else would hint at
        // whether the address has an account.
        if (error.status === 429 || /rate limit/i.test(error.message)) {
          setError('Too many requests. Wait a few minutes and try again.')
          return
        }
      }
      setSent(true)
    } catch {
      setError('Could not reach the server. Try again in a moment.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="flex h-screen w-full items-center justify-center bg-[#0a0a0a] px-6">
      <div className="w-full max-w-sm">
        <div className="mb-8 flex flex-col items-center text-center">
          <span className="mb-4 flex size-11 items-center justify-center rounded-xl bg-[#FFF41F]/10 text-[#FFF41F]">
            {sent ? (
              <MailCheck className="size-5" strokeWidth={1.5} />
            ) : (
              <KeyRound className="size-5" strokeWidth={1.5} />
            )}
          </span>
          <h1 className="text-[20px] font-semibold tracking-tight text-white">
            {sent ? 'Check your email' : 'Reset your password'}
          </h1>
          <p className="mt-1.5 text-[13px] font-light leading-relaxed text-[#7d7d82]">
            {sent
              ? 'If an account exists for that address, a link to choose a new password is on its way. It can take a minute; check your spam folder too.'
              : 'Enter the email you sign in with and we will send you a link to choose a new password.'}
          </p>
        </div>

        {!sent && (
          <form onSubmit={handleSubmit} className="flex flex-col gap-3">
            <label className="flex flex-col gap-1.5">
              <span className="text-[11px] font-medium uppercase tracking-wider text-[#7d7d82]">
                Email
              </span>
              <input
                type="email"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                required
                autoComplete="email"
                className="rounded-lg border border-[#16161a] bg-[#141414] px-3.5 py-2.5 text-[14px] text-white outline-none transition-colors placeholder:text-[#52525B] focus:border-[#FFF41F]/50"
                placeholder="you@example.com"
              />
            </label>

            {error && (
              <p role="alert" className="text-[12px] font-light leading-relaxed text-[#FCA5A5]">
                {error}
              </p>
            )}

            <button
              type="submit"
              disabled={busy}
              className="mt-2 inline-flex items-center justify-center gap-2 rounded-lg bg-[#FFF41F] px-4 py-2.5 text-[13px] font-semibold text-[#0A0A0A] transition-all hover:brightness-95 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {busy && <Loader2 className="size-3.5 animate-spin" />}
              <span>Send reset link</span>
            </button>
          </form>
        )}

        <p className="mt-5 text-center text-[12px] font-light text-[#7d7d82]">
          <Link
            href="/login"
            className="font-medium text-[#FFF41F] transition-opacity hover:opacity-80"
          >
            Back to sign in
          </Link>
        </p>
      </div>
    </div>
  )
}
