'use client'

import { LayoutDashboard, Key, CreditCard, LogOut } from 'lucide-react'
import Link from 'next/link'
import { usePathname } from 'next/navigation'

const meshLinks = [
  { label: 'Workspaces', icon: LayoutDashboard, href: '/lobby' },
  { label: 'BYOK', icon: Key, href: '/byok' },
  { label: 'Billing', icon: CreditCard, href: '/billing' },
]

export function LobbySidebar() {
  const pathname = usePathname()

  function isActive(href: string) {
    return pathname === href
  }

  return (
    <aside className="flex h-full w-[260px] shrink-0 flex-col border-r border-[#16161a] bg-panel">
      <div className="px-4 pt-4">
        <nav className="space-y-0.5">
          {meshLinks.map((link) => (
            <Link
              key={link.label}
              href={link.href}
              className={`flex items-center gap-3 rounded-md px-3 py-2.5 text-[13px] font-medium transition-all ${
                isActive(link.href)
                  ? 'bg-[#FFF41F]/15 text-[#7A6F00] dark:bg-[#FFF41F]/[0.05] dark:text-primary'
                  : 'text-[#6b6b72] hover:bg-black/[0.04] hover:text-white dark:hover:bg-white/[0.04] dark:hover:text-white'
              }`}
            >
              <link.icon className="size-4" strokeWidth={1.5} />
              {link.label}
            </Link>
          ))}
        </nav>
      </div>

      {/* Spacer */}
      <div className="flex-1" />

      {/* Terminate Session */}
      <div className="border-t border-[#16161a] px-4 py-3">
        <Link
          href="#"
          className="flex items-center gap-3 rounded-md px-3 py-2.5 text-[13px] font-medium text-[#DC2626]/90 transition-all hover:bg-[#FEF2F2] dark:text-[#ef4444]/80 dark:hover:bg-red-950/30"
        >
          <LogOut className="size-4" strokeWidth={1.5} />
          Terminate Session
        </Link>
      </div>
    </aside>
  )
}