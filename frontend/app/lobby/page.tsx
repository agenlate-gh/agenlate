'use client'

import { TopNavbar } from '@/components/top-navbar'
import { LobbySidebar } from '@/components/lobby-sidebar'
import { Switch } from '@/components/ui/switch'
import { agents } from '@/lib/agenlate-data'
import { Plus, Trash2, LayoutDashboard } from 'lucide-react'
import Link from 'next/link'
import { useState } from 'react'

export default function LobbyPage() {
  const [roomStates, setRoomStates] = useState<Record<string, boolean>>({
    '1': true,
    '2': false,
  })

  function toggleRoom(id: string) {
    setRoomStates((prev) => ({ ...prev, [id]: !prev[id] }))
  }

  const featuredRooms = [
    { id: '1', name: 'Production Deployment Analyzer', active: true, cost: '$4.271' },
    { id: '2', name: 'Smart Contract Auditor', active: false, cost: '$12.04' },
  ]

  return (
    <div className="flex h-screen max-h-screen w-full flex-col overflow-hidden bg-[#0a0a0a] text-foreground">
      {/* Top Navbar — Active lobby */}
      <TopNavbar />

      {/* Two-column layout: Sidebar + Main Content */}
      <div className="flex min-h-0 flex-1 pt-[56px]">
        <div className="hidden md:flex">
          <LobbySidebar />
        </div>

        <div className="flex min-w-0 flex-1 flex-col gap-5 overflow-y-auto pl-16 pr-6 pt-12 pb-6">
          <div className="w-full max-w-5xl">
            {/* Premium Header */}
            <div className="mb-10">
              <h1 className="flex items-center gap-2.5 text-[20px] font-semibold tracking-tight text-[#111111] dark:text-white">
                <LayoutDashboard className="size-5 text-[#7A6F00] dark:text-[#FFF41F]" strokeWidth={1.5} />
                Multi-Agent Workspaces
              </h1>

              <p className="mt-1.5 max-w-2xl text-[13px] font-light leading-relaxed text-[#52525B] dark:text-[#7d7d82]">
                Configure and manage your autonomous multi-agent environments with real-time orchestration loops and live deployment tracking.
              </p>
            </div>

            {/* ========== WORKSPACES GRID ========== */}
            <section>
              <h2 className="mb-4 text-[16px] font-semibold tracking-tight text-[#111111] dark:text-white">
                Active Agent Workspaces
              </h2>

              <div className="grid grid-cols-1 gap-6 md:grid-cols-2">
                {/* Create Room Card — dashed card trigger */}
                <Link
                  href="/?template=blank"
                  className="group flex flex-col items-center justify-center gap-4 rounded-xl border border-dashed border-[#16161a] px-4 py-10 transition-all hover:border-[#7A6F00]/30 hover:bg-black/[0.02] dark:border-[#16161a] dark:hover:border-[#FFF41F]/20 dark:hover:bg-white/[0.02]"
                >
                  <span className="flex size-12 shrink-0 items-center justify-center rounded-xl bg-[#FFF41F]/20 text-[#7A6F00] transition-colors group-hover:bg-[#FFF41F]/30 dark:bg-[#FFF41F]/10 dark:text-[#FFF41F] dark:group-hover:bg-[#FFF41F]/20">
                    <Plus className="size-6" strokeWidth={2.5} />
                  </span>
                  <span className="text-center text-[13px] font-semibold text-[#52525B] transition-colors group-hover:text-[#7A6F00] dark:text-[#7d7d82] dark:group-hover:text-[#FFF41F]">
                    Deploy New Multi-Agent Room
                  </span>
                </Link>

                {/* Existing Room Cards */}
                {featuredRooms.map((room) => (
                  <div
                    key={room.id}
                    className="flex flex-col rounded-xl border border-[#16161a] bg-[#141414] px-5 pb-5 pt-4 transition-all hover:shadow-sm dark:border-[#16161a] dark:bg-[#141414] dark:hover:bg-[#121214]"
                  >
                    {/* Room status dot & controls */}
                    <div className="mb-3 flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <span
                          className={`size-2 rounded-full ${roomStates[room.id] ? 'bg-green-500 pulse-dot' : 'bg-[#A1A1AA] dark:bg-[#7d7d82]'}`}
                          aria-hidden
                        />
                        <span className="text-[11px] font-light text-[#52525B] dark:text-[#7d7d82]">
                          {roomStates[room.id] ? 'Active' : 'Paused'}
                        </span>
                      </div>
                      <div className="flex items-center gap-2">
                        <Switch
                          checked={roomStates[room.id]}
                          onCheckedChange={() => toggleRoom(room.id)}
                        />
                        <button
                          type="button"
                          aria-label="Delete room"
                          className="flex size-7 items-center justify-center rounded-md text-[#71717A] transition-colors hover:bg-[#EBEBEB] hover:text-[#DC2626] dark:text-[#7d7d82] dark:hover:bg-[#1a1a1a] dark:hover:text-red-400"
                        >
                          <Trash2 className="size-3.5" strokeWidth={1.5} />
                        </button>
                      </div>
                    </div>

                    {/* Room title */}
                    <h3 className="mb-4 text-[15px] font-semibold tracking-tight text-[#111111] dark:text-white">
                      {room.name}
                    </h3>

                    {/* Agent badges row */}
                    <div className="mb-4 flex items-center">
                      <div className="flex -space-x-2">
                        {agents.map((agent) => (
                          <span
                            key={agent.id}
                            className="relative flex size-8 items-center justify-center rounded-full text-[10px] font-bold text-[#111111] dark:text-white"
                            style={{ backgroundColor: agent.color, zIndex: agents.length - agents.indexOf(agent) }}
                          >
                            {agent.initials}
                          </span>
                        ))}
                      </div>
                    </div>

                    {/* Room cost — white text */}
                    <div className="mb-4 inline-flex items-center gap-2">
                      <span className="text-[10px] font-medium uppercase tracking-wider text-[#52525B] dark:text-[#7d7d82]">
                        Room Cost
                      </span>
                      <span className="font-mono text-[13px] font-semibold tabular-nums text-[#111111] dark:text-white">
                        {room.cost}
                      </span>
                      <span className="text-[10px] font-light text-[#52525B] dark:text-[#7d7d82]">USD</span>
                    </div>

                    {/* Enter Room */}
                    <div className="mt-auto">
                      <Link
                        href="/"
                        className="inline-flex items-center gap-1.5 text-[13px] font-medium text-[#52525B] transition-colors hover:text-[#7A6F00] dark:text-[#7d7d82] dark:hover:text-[#FFF41F]"
                      >
                        Enter Room →
                      </Link>
                    </div>
                  </div>
                ))}
              </div>
            </section>
          </div>
        </div>
      </div>
    </div>
  )
}
