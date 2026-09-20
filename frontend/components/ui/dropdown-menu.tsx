'use client'

import { cn } from '@/lib/utils'
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useId,
  useRef,
  useState,
} from 'react'

/* ─── Context ─────────────────────────────────────────────────────────────── */

type DropdownContext = {
  open: boolean
  setOpen: (v: boolean) => void
  triggerId: string
  contentId: string
}

const Ctx = createContext<DropdownContext | null>(null)

function useDropdown() {
  const ctx = useContext(Ctx)
  if (!ctx) throw new Error('Dropdown components must be used within <DropdownMenu>')
  return ctx
}

/* ─── Root ────────────────────────────────────────────────────────────────── */

function DropdownMenu({ children }: { children: React.ReactNode }) {
  const [open, setOpen] = useState(false)
  const triggerId = useId()
  const contentId = useId()

  return (
    <Ctx.Provider value={{ open, setOpen, triggerId, contentId }}>
      {children}
    </Ctx.Provider>
  )
}

/* ─── Trigger ─────────────────────────────────────────────────────────────── */

function DropdownMenuTrigger({
  children,
  className,
  asChild,
}: {
  children: React.ReactNode
  className?: string
  asChild?: boolean
}) {
  const { open, setOpen, triggerId } = useDropdown()

  if (asChild) {
    return (
      <span
        id={triggerId}
        role="button"
        tabIndex={0}
        aria-haspopup
        aria-expanded={open}
        onClick={(e) => {
          e.stopPropagation()
          setOpen(!open)
        }}
        onKeyDown={(e) => {
          if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault()
            setOpen(!open)
          }
        }}
        className={className}
      >
        {children}
      </span>
    )
  }

  return (
    <button
      id={triggerId}
      type="button"
      aria-haspopup
      aria-expanded={open}
      onClick={(e) => {
        e.stopPropagation()
        setOpen(!open)
      }}
      className={className}
    >
      {children}
    </button>
  )
}

/* ─── Content ──────────────────────────────────────────────────────────────── */

function DropdownMenuContent({
  children,
  className,
  align = 'end',
}: {
  children: React.ReactNode
  className?: string
  align?: 'start' | 'end'
}) {
  const { open, setOpen, triggerId, contentId } = useDropdown()
  const ref = useRef<HTMLDivElement>(null)

  const handleClickOutside = useCallback(
    (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        const trigger = document.getElementById(triggerId)
        if (trigger && !trigger.contains(e.target as Node)) {
          setOpen(false)
        }
      }
    },
    [setOpen, triggerId],
  )

  const handleKeyDown = useCallback(
    (e: KeyboardEvent) => {
      if (e.key === 'Escape') setOpen(false)
    },
    [setOpen],
  )

  useEffect(() => {
    if (open) {
      document.addEventListener('mousedown', handleClickOutside)
      document.addEventListener('keydown', handleKeyDown)
    }
    return () => {
      document.removeEventListener('mousedown', handleClickOutside)
      document.removeEventListener('keydown', handleKeyDown)
    }
  }, [open, handleClickOutside, handleKeyDown])

  if (!open) return null

  return (
    <div
      ref={ref}
      id={contentId}
      role="menu"
      data-align={align}
      className={cn(
        'absolute right-0 top-full z-50 mt-1 min-w-[160px] rounded-lg border border-panel-border bg-white py-1 shadow-lg shadow-black/[0.06] dark:bg-[#141414] dark:shadow-black/40',
        className,
      )}
    >
      {children}
    </div>
  )
}

/* ─── Item ─────────────────────────────────────────────────────────────────── */

function DropdownMenuItem({
  children,
  onClick,
  className,
  variant,
}: {
  children: React.ReactNode
  onClick?: () => void
  className?: string
  variant?: 'default' | 'destructive'
}) {
  const { setOpen } = useDropdown()

  return (
    <button
      type="button"
      role="menuitem"
      onClick={(e) => {
        e.stopPropagation()
        onClick?.()
        setOpen(false)
      }}
      className={cn(
        'flex w-full items-center gap-2 px-3 py-1.5 text-left text-[12.5px] font-light transition-colors',
        variant === 'destructive'
          ? 'text-[#DC2626] hover:bg-[#FEF2F2] dark:text-red-400 dark:hover:bg-red-950/30'
          : 'text-foreground hover:bg-secondary/60',
        className,
      )}
    >
      {children}
    </button>
  )
}

/* ─── Separator ────────────────────────────────────────────────────────────── */

function DropdownMenuSeparator() {
  return <div className="my-1 border-t border-panel-border" />
}

export {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
}