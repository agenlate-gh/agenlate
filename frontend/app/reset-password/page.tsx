'use client'

/**
 * Choosing a new password.
 *
 * Two ways in, one screen. The reset email's link lands here with a recovery
 * token, which Supabase turns into a session as the page loads. Someone
 * already signed in comes here from "Change password" in the account menu.
 * Either way there is a session, and changing the password needs nothing else.
 *
 * Without a session the link has expired or was already used. That is said
 * plainly, with the way to get a new one, rather than showing a form that
 * cannot work.
 */

import { useEffect, useState } from 'react'
import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { Check, Eye, EyeOff, KeyRound, Loader2 } from 'lucide-react'

import { useAuth } from '@/components/auth-provider'
import { arrivalHash, supabase } from '@/lib/supabase'

const MIN_LENGTH = 8

export default function ResetPasswordPage() {
  const router = useRouter()
  const { session, loading } = useAuth()

  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [show, setShow] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [done, setDone] = useState(false)
  /** Set when Supabase sent the person back with an error instead of a token. */
  const [linkProblem, setLinkProblem] = useState(false)

  useEffect(() => {
    // An expired or reused link comes back as #error=…&error_code=otp_expired.
    // The client may already have cleared the address, so the fragment as the
    // page first loaded is the fallback.
    const hash = new URLSearchParams((window.location.hash || arrivalHash).replace(/^#/, ''))
    if (hash.get('error') || hash.get('error_code')) setLinkProblem(true)
  }, [])

  useEffect(() => {
    if (!done) return
    const timer = setTimeout(() => router.replace('/lobby'), 2000)
    return () => clearTimeout(timer)
  }, [done, router])

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault()
    setError(null)
    if (password.length < MIN_LENGTH) {
      setError(`Use at least ${MIN_LENGTH} characters.`)
      return
    }
    if (password !== confirm) {
      setError('The two passwords do not match.')
      return
    }
    setBusy(true)
    try {
      const { error } = await supabase.auth.updateUser({ password })
      if (error) {
        setError(
          error.code === 'same_password'
            ? 'Choose a password different from your current one.'
            : error.code === 'weak_password'
              ? 'That password is too weak. Choose a longer one.'
              : error.message,
        )
        return
      }
      setDone(true)
    } catch {
      setError('Could not reach the server. Try again in a moment.')
    } finally {
      setBusy(false)
    }
  }

  if (loading) {
    return (
      <Shell>
        <p className="flex items-center justify-center gap-2 text-[13px] font-light text-[#7d7d82]">
          <Loader2 className="size-4 animate-spin" />
          <span>Checking your link…</span>
        </p>
      </Shell>
    )
  }

  if (done) {
    return (
      <Shell icon={<Check className="size-5" strokeWidth={2} />} title="Password changed">
        <p className="text-center text-[13px] font-light leading-relaxed text-[#7d7d82]">
          You are signed in. Taking you to your rooms…
        </p>
      </Shell>
    )
  }

  if (!session || linkProblem) {
    return (
      <Shell title="This link has expired">
        <p className="text-center text-[13px] font-light leading-relaxed text-[#7d7d82]">
          Reset links work once and only for a short time. Ask for a new one and
          use it straight away.
        </p>
        <Link
          href="/forgot-password"
          className="mt-6 inline-flex w-full items-center justify-center rounded-lg bg-[#FFF41F] px-4 py-2.5 text-[13px] font-semibold text-[#0A0A0A] transition-all hover:brightness-95"
        >
          Send me a new link
        </Link>
      </Shell>
    )
  }

  return (
    <Shell
      title="Choose a new password"
      subtitle={session.user.email ? `For ${session.user.email}` : undefined}
    >
      <form onSubmit={handleSubmit} className="flex flex-col gap-3">
        <label className="flex flex-col gap-1.5">
          <span className="text-[11px] font-medium uppercase tracking-wider text-[#7d7d82]">
            New password
          </span>
          <span className="flex items-center rounded-lg border border-[#16161a] bg-[#141414] transition-colors focus-within:border-[#FFF41F]/50">
            <input
              type={show ? 'text' : 'password'}
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              required
              minLength={MIN_LENGTH}
              autoComplete="new-password"
              className="min-w-0 flex-1 bg-transparent px-3.5 py-2.5 text-[14px] text-white outline-none placeholder:text-[#52525B]"
              placeholder={`At least ${MIN_LENGTH} characters`}
            />
            <button
              type="button"
              onClick={() => setShow((shown) => !shown)}
              aria-label={show ? 'Hide password' : 'Show password'}
              aria-pressed={show}
              className="px-3 text-[#7d7d82] transition-colors hover:text-white"
            >
              {show ? <EyeOff className="size-4" /> : <Eye className="size-4" />}
            </button>
          </span>
        </label>

        <label className="flex flex-col gap-1.5">
          <span className="text-[11px] font-medium uppercase tracking-wider text-[#7d7d82]">
            Confirm new password
          </span>
          <input
            type={show ? 'text' : 'password'}
            value={confirm}
            onChange={(event) => setConfirm(event.target.value)}
            required
            autoComplete="new-password"
            className="rounded-lg border border-[#16161a] bg-[#141414] px-3.5 py-2.5 text-[14px] text-white outline-none transition-colors placeholder:text-[#52525B] focus:border-[#FFF41F]/50"
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
          <span>Save new password</span>
        </button>
      </form>
    </Shell>
  )
}

function Shell({
  icon,
  title,
  subtitle,
  children,
}: {
  icon?: React.ReactNode
  title?: string
  subtitle?: string
  children: React.ReactNode
}) {
  return (
    <div className="flex h-screen w-full items-center justify-center bg-[#0a0a0a] px-6">
      <div className="w-full max-w-sm">
        {title && (
          <div className="mb-8 flex flex-col items-center text-center">
            <span className="mb-4 flex size-11 items-center justify-center rounded-xl bg-[#FFF41F]/10 text-[#FFF41F]">
              {icon ?? <KeyRound className="size-5" strokeWidth={1.5} />}
            </span>
            <h1 className="text-[20px] font-semibold tracking-tight text-white">{title}</h1>
            {subtitle && (
              <p className="mt-1.5 text-[13px] font-light text-[#7d7d82]">{subtitle}</p>
            )}
          </div>
        )}
        {children}
      </div>
    </div>
  )
}
