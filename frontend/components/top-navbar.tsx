'use client'

import { Hexagon, ChevronDown, Settings, LogOut } from 'lucide-react'
import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { useState } from 'react'

const navLinks = [
  { label: 'Lobby', href: '/lobby', active: true },
  { label: 'Docs', href: '#', active: false },
  { label: 'FAQs', href: '#', active: false },
]

const menuItemClass =
  'flex w-full items-center gap-2.5 rounded-md px-3 py-2 text-left text-[12.5px] text-[#52525B] transition-colors hover:bg-[#EBEBEB] hover:text-[#111111] dark:text-[#7d7d82] dark:hover:bg-[#1a1a1a] dark:hover:text-white'

export function TopNavbar() {
  const [profileOpen, setProfileOpen] = useState(false)
  const pathname = usePathname()

  const isLobby = pathname === '/lobby'

  return (
    <header className="fixed top-0 left-0 right-0 z-50 flex h-[56px] items-center justify-between border-b border-[#E4E4E7] bg-[#F5F5F5] px-5 dark:border-[#262629] dark:bg-[#0A0A0A]">
      {/* Left: Logo */}
      <Link href="/lobby" className="flex items-center gap-3">
        <div className="flex size-8 items-center justify-center rounded-md bg-[#FFF41F] text-[#111111]">
          <Hexagon className="size-4" strokeWidth={2.5} />
        </div>
        <span
          className="text-[17px] font-semibold tracking-tight text-[#111111] dark:text-white"
          style={{ fontFamily: 'var(--font-poppins), ui-sans-serif, sans-serif' }}
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
            JD
          </div>
          <span className="hidden text-[12px] font-medium text-[#111111] sm:inline dark:text-white">
            John Doe
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
                <p className="text-[13px] font-semibold text-[#111111] dark:text-white">John Doe</p>
                <p className="text-[11px] text-[#52525B] dark:text-[#7d7d82]">john@example.com</p>
              </div>

              <div className="mt-1 space-y-0.5">
                <button type="button" className={menuItemClass}>
                  <Settings className="size-4" strokeWidth={1.5} />
                  Account Settings
                </button>
              </div>

            </div>
          </>
        )}
      </div>
    </header>
  )
}

