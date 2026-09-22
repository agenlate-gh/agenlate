'use client'

/**
 * Who is signed in, and the gate in front of everything else.
 *
 * Sessions live in the browser and refresh themselves. The one case worth
 * handling explicitly is the first paint: until Supabase has read the stored
 * session we do not know whether there is one, and rendering the signed-out
 * state during that moment would bounce a signed-in user to the login screen
 * on every reload.
 */

import { createContext, useContext, useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import type { Session, User } from '@supabase/supabase-js'

import { supabase } from '@/lib/supabase'

type AuthState = {
  user: User | null
  session: Session | null
  /** True until the stored session has been read. Not the same as signed out. */
  loading: boolean
  signOut: () => Promise<void>
}

const AuthContext = createContext<AuthState | null>(null)

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [session, setSession] = useState<Session | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let active = true

    supabase.auth.getSession().then(({ data }) => {
      if (!active) return
      setSession(data.session)
      setLoading(false)
    })

    // Fires on sign-in, sign-out, and every token refresh. Without it a tab
    // left open past the one-hour expiry keeps a stale token in memory.
    const { data: subscription } = supabase.auth.onAuthStateChange(
      (_event, next) => {
        if (!active) return
        setSession(next)
        setLoading(false)
      },
    )

    return () => {
      active = false
      subscription.subscription.unsubscribe()
    }
  }, [])

  async function signOut() {
    await supabase.auth.signOut()
  }

  return (
    <AuthContext.Provider
      value={{ user: session?.user ?? null, session, loading, signOut }}
    >
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth(): AuthState {
  const context = useContext(AuthContext)
  if (!context) {
    throw new Error('useAuth must be used inside AuthProvider')
  }
  return context
}

/**
 * Wraps a page that requires a signed-in user.
 *
 * Client-side rather than middleware: everything behind the login renders in
 * the browser anyway, and the API refuses unauthenticated requests regardless.
 * This is about not showing someone an empty page, not about protecting data —
 * the database does that.
 */
export function RequireAuth({ children }: { children: React.ReactNode }) {
  const { session, loading } = useAuth()
  const router = useRouter()

  useEffect(() => {
    if (!loading && !session) router.replace('/login')
  }, [loading, session, router])

  if (loading) {
    return (
      <div className="flex h-screen items-center justify-center bg-[#0a0a0a]">
        <span className="text-[13px] font-light text-[#7d7d82]">Loading…</span>
      </div>
    )
  }

  if (!session) return null

  return <>{children}</>
}
