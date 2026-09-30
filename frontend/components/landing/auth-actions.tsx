'use client'

/**
 * The top-right buttons, which depend on whether the visitor is signed in.
 *
 * The landing page is public and mostly static; this is the one part that
 * knows about the session. Someone already signed in is offered their
 * workspace rather than a sign-in button they do not need.
 */

import Link from 'next/link'

import { useAuth } from '@/components/auth-provider'

export function AuthActions() {
  const { session, loading } = useAuth()

  // Reserve the space while the session is read, so the header does not jump.
  if (loading) return <span className="h-9 w-40" aria-hidden />

  if (session) {
    return (
      <Link
        href="/lobby"
        className="rounded-lg bg-[#FFF41F] px-4 py-2 text-[13px] font-bold text-[#0A0A0A] transition-all hover:brightness-95"
      >
        Open your workspace
      </Link>
    )
  }

  return (
    <div className="flex items-center gap-1.5 sm:gap-2">
      <Link
        href="/login"
        className="rounded-lg px-3 py-2 text-[13px] font-semibold text-[#d4d4d8] transition-colors hover:text-white"
      >
        Sign in
      </Link>
      <Link
        href="/login?mode=signup"
        className="rounded-lg border border-[#FFF41F]/40 px-3.5 py-2 text-[13px] font-semibold text-[#FFF41F] transition-colors hover:bg-[#FFF41F]/10"
      >
        I have an invite
      </Link>
    </div>
  )
}
