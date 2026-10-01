'use client'

/**
 * What a user sees when a screen crashes.
 *
 * Without this, Next.js shows a bare "This page couldn't load" with Reload and
 * Back, which tells the person nothing and tells us less: the first crash in
 * the Beta was found only because a tester happened to describe that page.
 *
 * Two jobs. Report the error, so it reaches the server log with enough detail
 * to act on. And say what is true about the user's work: text typed into the
 * builder, the reply box and the new-room form is kept in this tab, so trying
 * again does not mean starting again.
 */

import { useEffect } from 'react'
import Link from 'next/link'
import { RotateCcw } from 'lucide-react'

import { AgenlateTile } from '@/components/brand'
import { env } from '@/lib/env'

export default function ErrorScreen({
  error,
  reset,
}: {
  error: Error & { digest?: string }
  reset: () => void
}) {
  useEffect(() => {
    // Best effort, and never allowed to throw: this runs while the page is
    // already in trouble. keepalive lets it finish if the user reloads at once.
    try {
      void fetch(`${env.apiBaseUrl}/api/client-errors`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        keepalive: true,
        body: JSON.stringify({
          message: `${error.name}: ${error.message}`.slice(0, 500),
          stack: (error.stack ?? '').slice(0, 2000),
          path: window.location.pathname.slice(0, 300),
          digest: error.digest ?? '',
        }),
      }).catch(() => {})
    } catch {
      // Nothing more to do.
    }
  }, [error])

  return (
    <div className="flex h-screen flex-col items-center justify-center bg-[#0a0a0a] px-6 text-center">
      <AgenlateTile className="size-12" />
      <h1 className="mt-6 text-[20px] font-semibold tracking-tight text-white">
        This screen ran into a problem
      </h1>
      <p className="mt-2 max-w-md text-[13.5px] font-light leading-relaxed text-[#a1a1aa]">
        Anything you were typing has been kept, and the problem has been
        reported to us. Try again — if it keeps happening, go back to your
        workspace and carry on from there.
      </p>
      <div className="mt-6 flex items-center gap-2">
        <button
          type="button"
          onClick={reset}
          className="inline-flex items-center gap-2 rounded-lg bg-[#FFF41F] px-4 py-2.5 text-[13px] font-semibold text-[#0A0A0A] transition-all hover:brightness-95"
        >
          <RotateCcw className="size-3.5" strokeWidth={2.5} />
          <span>Try again</span>
        </button>
        <Link
          href="/lobby"
          className="rounded-lg border border-[#262629] px-4 py-2.5 text-[13px] font-medium text-[#d4d4d8] transition-colors hover:text-white"
        >
          Back to your workspace
        </Link>
      </div>
      {error.digest && (
        <p className="mt-5 font-mono text-[11px] text-[#52525B]">Reference: {error.digest}</p>
      )}
    </div>
  )
}
