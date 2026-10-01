'use client'

import { ChevronDown, Key, LogOut } from 'lucide-react'
import Link from 'next/link'
import { usePathname, useRouter } from 'next/navigation'
import { useState } from 'react'

import { useAuth } from '@/components/auth-provider'
import { AgenlateTile } from '@/components/brand'

// Docs and FAQs are not here yet because there is nothing behind them yet. A
// link that goes nowhere reads as a broken product; they return with content.
const navLinks = [{ label: 'Lobby', href: '/lobby', active: true }]

const menuItemClass =
  'flex w-full items-center gap-2.5 rounded-md px-3 py-2 text-left text-[12.5px] text-[#52525B] transition-colors hover:bg-[#EBEBEB] hover:text-[#111111] dark:text-[#7d7d82] dark:hover:bg-[#1a1a1a] dark:hover:text-white'

/**
 * What to call someone we only know by email address.
 *
 * Supabase auth gives us an email and nothing else — there is no profile table
 * and no display name to ask for. The local part is the closest thing to a
 * name the user has given us, so it stands in for one rather than showing the
 * whole address in a space sized for a name.
 */
function displayName(email: string | undefined): string {
  return email?.split('@')[0] ?? 'Signed in'
}

function initials(email: string | undefined): string {
  const name = displayName(email)
  const parts = name.split(/[._-]+/).filter(Boolean)
  if (parts.length >= 2) return (parts[0][0] + parts[1][0]).toUpperCase()
  return name.slice(0, 2).toUpperCase()
}

export function TopNavbar() {
  const [profileOpen, setProfileOpen] = useState(false)
  const [signingOut, setSigningOut] = useState(false)
  const pathname = usePathname()
  const router = useRouter()
  const { user, signOut } = useAuth()

  const isLobby = pathname === '/lobby'

  async function handleSignOut() {
    setSigningOut(true)
    await signOut()
    // Replace rather than push: the back button should not return to a screen
    // the user has just signed out of.
    router.replace('/login')
  }

  return (
    <header className="fixed top-0 left-0 right-0 z-50 flex h-[56px] items-center justify-between border-b border-[#E4E4E7] bg-[#F5F5F5] px-5 dark:border-[#262629] dark:bg-[#0A0A0A]">
      {/* Left: Logo */}
      <Link href="/lobby" className="flex items-center gap-3">
        <AgenlateTile />
        <span
          className="text-[17px] font-semibold tracking-tight text-[#111111] dark:text-white"
          style={{ fontFamily: 'var(--font-jakarta), ui-sans-serif, sans-serif' }}
        >
          agenlate
        </span>
        <span className="rounded-md border border-[#FFF41F] bg-[#FFF41F]/40 px-1.5 py-0.5 text-[9px] font-bold tracking-wide text-[#111111] dark:border-[#FFF41F]/40 dark:bg-[#FFF41F]/10 dark:text-[#FFF41F]">
          BETA
        </span>
        <span className="hidden rounded-md border border-[#E4E4E7] bg-white px-2 py-0.5 text-[10px] font-light text-[#52525B] sm:inline-block dark:border-[#262629] dark:bg-[#141414] dark:text-[#7d7d82]">
          Multi-Agent Console
        </span>
      </Link>

      {/* Center: Nav Links */}
      <nav className="hidden items-center gap-1 md:flex">
        {navLinks.map((link) => (
          <Link
            key={link.label}
            href={link.href}
            className={`rounded-md px-3 py-1.5 text-[13px] font-medium tracking-tight transition-colors ${
              (link.href === '/lobby' && isLobby) || (link.href !== '/lobby' && link.active)
                ? 'text-[#7A6F00] dark:text-[#FFF41F]'
                : 'text-[#52525B] hover:text-[#111111] dark:text-[#7d7d82] dark:hover:text-white'
            }`}
          >
            {link.label}
          </Link>
        ))}
      </nav>

      {/* Right: User Profile — the light/dark switch lives inside the menu */}
      <div className="relative">
        <button
          type="button"
          onClick={() => setProfileOpen(!profileOpen)}
          aria-expanded={profileOpen}
          className="flex items-center gap-2 rounded-full border border-[#E4E4E7] bg-white p-1 pr-3 transition-colors hover:border-[#7A6F00]/40 dark:border-[#262629] dark:bg-[#141414] dark:hover:border-[#FFF41F]/50"
        >
          <div className="flex size-7 items-center justify-center rounded-full bg-[#FFF41F] text-[10px] font-bold text-[#111111]">
            {initials(user?.email)}
          </div>
          <span className="hidden max-w-[10rem] truncate text-[12px] font-medium text-[#111111] sm:inline dark:text-white">
            {displayName(user?.email)}
          </span>
          <ChevronDown className="size-3.5 text-[#52525B] dark:text-[#7d7d82]" strokeWidth={2} />
        </button>

        {profileOpen && (
          <>
            <div
              className="fixed inset-0 z-40"
              onClick={() => setProfileOpen(false)}
              aria-hidden
            />
            <div className="absolute right-0 top-full z-50 mt-2 w-60 rounded-lg border border-[#E4E4E7] bg-white p-1.5 shadow-lg shadow-black/5 dark:border-[#262629] dark:bg-[#141414] dark:shadow-black/40">
              <div className="border-b border-[#E4E4E7] px-3 py-2.5 dark:border-[#262629]">
                <p className="truncate text-[13px] font-semibold text-[#111111] dark:text-white">
                  {displayName(user?.email)}
                </p>
                <p className="truncate text-[11px] text-[#52525B] dark:text-[#7d7d82]">
                  {user?.email}
                </p>
              </div>

              <div className="mt-1 space-y-0.5">
                <Link href="/byok" className={menuItemClass}>
                  <Key className="size-4" strokeWidth={1.5} />
                  API key
                </Link>
                <button
                  type="button"
                  onClick={handleSignOut}
                  disabled={signingOut}
                  className={`${menuItemClass} disabled:opacity-60`}
                >
                  <LogOut className="size-4" strokeWidth={1.5} />
                  {signingOut ? 'Signing out…' : 'Sign out'}
                </button>
              </div>

            </div>
          </>
        )}
      </div>
    </header>
  )
}

