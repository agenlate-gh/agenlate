'use client'

/**
 * The root has nothing of its own to show.
 *
 * A signed-in user belongs in the lobby, where their rooms are; everyone else
 * belongs at the login. Deciding that here rather than putting a marketing
 * page at `/` keeps the Beta to one job — there is no public site yet, and a
 * placeholder would be a screen we would have to maintain.
 */

import { useEffect } from 'react'
import { useRouter } from 'next/navigation'

import { useAuth } from '@/components/auth-provider'

export default function RootPage() {
  const router = useRouter()
  const { session, loading } = useAuth()

  useEffect(() => {
    if (loading) return
    router.replace(session ? '/lobby' : '/login')
  }, [loading, session, router])

  return (
    <div className="flex h-screen items-center justify-center bg-[#0a0a0a]">
      <span className="text-[13px] font-light text-[#7d7d82]">Loading…</span>
    </div>
  )
}
