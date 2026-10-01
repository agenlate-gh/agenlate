'use client'

/**
 * Sign in and sign up, on one screen.
 *
 * Two screens for what is the same form with a different button is a decision
 * a new user has to make before they have any reason to care about it. The
 * mode is a toggle instead.
 */

import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import { Eye, EyeOff, KeyRound, Loader2 } from 'lucide-react'

import { useAuth } from '@/components/auth-provider'
import { accounts } from '@/lib/agenlate'
import { supabase } from '@/lib/supabase'

type Mode = 'signin' | 'signup'

export default function LoginPage() {
  const router = useRouter()
  const { session, loading: sessionLoading } = useAuth()

  const [mode, setMode] = useState<Mode>('signin')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [inviteCode, setInviteCode] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Someone already signed in has no business here.
  useEffect(() => {
    if (!sessionLoading && session) router.replace('/lobby')
  }, [session, sessionLoading, router])

  // An invite shared as a link — /login?invite=K7QM-4XRT-WN2P — opens straight
  // on sign-up with the code filled in, so the person receiving it does not
  // have to copy a code from one place to another. Read from the location
  // after mount rather than through useSearchParams, which would force this
  // page out of static rendering for one optional value.
  useEffect(() => {
    const params = new URLSearchParams(window.location.search)
    const invite = params.get('invite')
    if (invite) {
      setInviteCode(invite)
      setMode('signup')
    } else if (params.get('mode') === 'signup') {
      // From the landing page's "I have an invite" button.
      setMode('signup')
    }
  }, [])

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault()
    setError(null)
    setBusy(true)

    try {
      if (mode === 'signup') {
        // Through our API, not supabase.auth.signUp: public signup is off, and
        // the code has to be checked and spent on the server to mean anything.
        // The account comes back confirmed, so signing in straight away works.
        await accounts.signUp({ email, password, invite_code: inviteCode })
      }
      const { error } = await supabase.auth.signInWithPassword({ email, password })
      if (error) throw error
      router.replace('/lobby')
    } catch (cause) {
      setError(
        cause instanceof Error ? cause.message : 'Something went wrong. Try again.',
      )
    } finally {
      setBusy(false)
    }
  }

  const isSignUp = mode === 'signup'

  return (
    <div className="flex h-screen w-full items-center justify-center bg-[#0a0a0a] px-6">
      <div className="w-full max-w-sm">
        <div className="mb-8 flex flex-col items-center text-center">
          <span className="mb-4 flex size-11 items-center justify-center rounded-xl bg-[#FFF41F]/10 text-[#FFF41F]">
            <KeyRound className="size-5" strokeWidth={1.5} />
          </span>
          <h1 className="text-[20px] font-semibold tracking-tight text-white">
            {isSignUp ? 'Create your account' : 'Sign in to Agenlate'}
          </h1>
          <p className="mt-1.5 text-[13px] font-light leading-relaxed text-[#7d7d82]">
            {isSignUp
              ? 'Design a team of AI workers and watch them work.'
              : 'Welcome back.'}
          </p>
        </div>

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

          <label className="flex flex-col gap-1.5">
            <span className="text-[11px] font-medium uppercase tracking-wider text-[#7d7d82]">
              Password
            </span>
            {/* The field and its toggle share one border, so the eye button
                reads as part of the field rather than a separate control. */}
            <span className="flex items-center rounded-lg border border-[#16161a] bg-[#141414] transition-colors focus-within:border-[#FFF41F]/50">
              <input
                type={showPassword ? 'text' : 'password'}
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                required
                minLength={8}
                autoComplete={isSignUp ? 'new-password' : 'current-password'}
                className="min-w-0 flex-1 bg-transparent px-3.5 py-2.5 text-[14px] text-white outline-none placeholder:text-[#52525B]"
                placeholder={isSignUp ? 'At least 8 characters' : '••••••••'}
              />
              <button
                type="button"
                onClick={() => setShowPassword((shown) => !shown)}
                aria-label={showPassword ? 'Hide password' : 'Show password'}
                aria-pressed={showPassword}
                className="px-3 text-[#7d7d82] transition-colors hover:text-white"
              >
                {showPassword ? <EyeOff className="size-4" /> : <Eye className="size-4" />}
              </button>
            </span>
          </label>

          {isSignUp && (
            <label className="flex flex-col gap-1.5">
              <span className="text-[11px] font-medium uppercase tracking-wider text-[#7d7d82]">
                Invite code
              </span>
              <input
                type="text"
                value={inviteCode}
                onChange={(event) => setInviteCode(event.target.value)}
                required
                autoComplete="off"
                spellCheck={false}
                className="rounded-lg border border-[#16161a] bg-[#141414] px-3.5 py-2.5 font-mono text-[14px] uppercase tracking-wider text-white outline-none transition-colors placeholder:normal-case placeholder:tracking-normal placeholder:text-[#52525B] focus:border-[#FFF41F]/50"
                placeholder="XXXX-XXXX-XXXX"
              />
              <span className="text-[11px] font-light leading-relaxed text-[#7d7d82]">
                Agenlate is in a small, invite-only Beta.
              </span>
            </label>
          )}

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
            {/* In its own element: a translated page replaces bare text, and
                React then has nowhere to put the spinner beside it. */}
            <span>{isSignUp ? 'Create account' : 'Sign in'}</span>
          </button>
        </form>

        <p className="mt-5 text-center text-[12px] font-light text-[#7d7d82]">
          {isSignUp ? 'Already have an account?' : 'New here?'}{' '}
          <button
            type="button"
            onClick={() => {
              setMode(isSignUp ? 'signin' : 'signup')
              setError(null)
                      }}
            className="font-medium text-[#FFF41F] transition-opacity hover:opacity-80"
          >
            {isSignUp ? 'Sign in' : 'Create one'}
          </button>
        </p>
      </div>
    </div>
  )
}
