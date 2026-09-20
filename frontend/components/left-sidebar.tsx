'use client'

import { useState, useRef, useEffect } from 'react'
import { agents, blankTemplateAgents } from '@/lib/agenlate-data'
import {
  Pencil,
  MoreVertical,
  Trash2,
} from 'lucide-react'
import { Switch } from '@/components/ui/switch'
import type { Agent } from '@/lib/agenlate-data'

export function LeftSidebar({
  selectedId,
  onSelect,
  onEditAgent,
  agents: roomAgents,
  roomName,
  roomCost,
  masterActive,
  onMasterToggle,
  onDeleteRoom,
}: {
  selectedId: string
  onSelect: (id: string) => void
  onEditAgent?: (id: string) => void
  agents: Agent[]
  roomName: string
  roomCost: string
  masterActive: boolean
  onMasterToggle: (active: boolean) => void
  onDeleteRoom: () => void
}) {
  const [agentStates, setAgentStates] = useState<Record<string, boolean>>(
    () => Object.fromEntries(roomAgents.map((a) => [a.id, true])),
  )
  function toggleAgent(id: string) {
    setAgentStates((prev) => ({ ...prev, [id]: !prev[id] }))
  }
  const [openMenuId, setOpenMenuId] = useState<string | null>(null)
  const menuRef = useRef<HTMLDivElement>(null)
  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setOpenMenuId(null)
      }
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [])

  return (
    <aside className="flex h-full w-[280px] shrink-0 flex-col border-r border-[#16161a] bg-panel">
      {/* Exit to Lobby */}
      <div className="px-4 pt-4">
        <a
          href="/lobby"
          className="flex items-center gap-2 text-[12px] font-light text-[#7d7d82] transition-colors hover:text-white"
        >
          ← Exit to Lobby
        </a>
      </div>

      {/* ROOM METRICS */}
      <div className="border-b border-[#16161a] px-4 pb-3 pt-3.5">
        <div className="flex items-center justify-between">
          <span className="text-[11px] font-medium uppercase tracking-wider text-[#7d7d82]">
            Room Metrics
          </span>
          <div className="flex items-center gap-1.5">
            <span className="text-[10px] font-light text-[#7d7d82]">
              {masterActive ? 'Active' : 'Paused'}
            </span>
            <Switch
              checked={masterActive}
              onCheckedChange={onMasterToggle}
            />
          </div>
        </div>
        <div className="mt-1.5 flex flex-col leading-tight">
          <span className="truncate text-[13px] font-semibold text-[#d4d4d8]">{roomName}</span>
          <span className="mt-0.5 text-[11.5px] font-light text-[#7d7d82]">
            Room Cost: <span className="font-mono font-medium tabular-nums">{roomCost}</span> USD
          </span>
        </div>
      </div>

      {/* AGENTS */}
      <div className="flex min-h-0 flex-1 flex-col px-4 pt-5">
        <span className="px-1 pb-2.5 text-[11px] font-medium uppercase tracking-wider text-[#7d7d82]">
          AGENTS
        </span>

        <div className="scrollbar-thin flex-1 space-y-0.5 overflow-y-auto">
          {/* Supervisor */}
          {roomAgents
            .filter((a) => a.id === 'supervisor')
            .map((agent) => {
              const selected = agent.id === selectedId
              const isActive = agentStates[agent.id]
              const menuOpen = openMenuId === agent.id
              return (
                <div key={agent.id} className="relative">
                  <button
                    type="button"
                    onClick={() => onSelect(agent.id)}
                    aria-pressed={selected}
                    className={`flex w-full items-center gap-3 px-3 py-2.5 text-left transition-all hover:bg-black/[0.04] dark:hover:bg-white/[0.04] ${
                        selected
                          ? 'mx-2 rounded-xl bg-[#1a1a1f]'
                          : ''
                      }`}
                  >
                    <span
                      className="flex size-8 shrink-0 items-center justify-center rounded-md text-[11px] font-semibold"
                      style={{
                        backgroundColor: agent.color,
                        color:
                          agent.color.toLowerCase() === '#fff41f'
                            ? '#111111'
                            : '#ffffff',
                      }}
                      aria-hidden
                    >
                      {agent.initials}
                    </span>
                    <span className="flex min-w-0 flex-1 flex-col leading-tight">
                      <span
                        className={`truncate text-[13px] font-semibold ${
                            selected ? 'text-[#FFF41F]' : 'text-[#d4d4d8]'
                        }`}
                      >
                        {agent.name}
                      </span>
                      <span className={`truncate text-[11px] font-light ${selected ? 'text-white' : 'text-[#7d7d82]'}`}>
                        {isActive ? agent.role : 'Paused'}
                      </span>
                    </span>
                    <div className="flex shrink-0 items-center gap-0.5" onClick={(e) => e.stopPropagation()}>
                      <button
                        type="button"
                        aria-label={`Options for ${agent.name}`}
                        onClick={(e) => {
                          e.stopPropagation()
                          setOpenMenuId(menuOpen ? null : agent.id)
                        }}
                        className="flex size-6 items-center justify-center rounded-md text-[#71717A] transition-colors hover:bg-[#EBEEBEB] dark:text-[#7d7d82] dark:hover:bg-[#1a1a1a]"
                      >
                        <MoreVertical className="size-3.5" strokeWidth={1.5} />
                      </button>
                      {menuOpen && (
                        <div
                          ref={menuRef}
                          className="absolute right-2 top-8 z-50 w-60 rounded-lg border border-[#E4E4E7] bg-white p-1.5 shadow-lg shadow-black/5 dark:border-[#262629] dark:bg-[#141414] dark:shadow-black/40"
                          onClick={(e) => e.stopPropagation()}
                        >
                          <button
                            type="button"
                            onClick={() => {
                              onSelect(agent.id)
                              onEditAgent?.(agent.id)
                              setOpenMenuId(null)
                            }}
                            className="flex w-full items-center gap-2.5 rounded-md px-3 py-2 text-left text-[12.5px] text-[#52525B] transition-colors hover:bg-[#EBEBEB] hover:text-[#111111] dark:text-[#7d7d82] dark:hover:bg-[#1a1a1a] dark:hover:text-white"
                          >
                            <Pencil className="size-3.5" strokeWidth={1.5} />
                            Edit Agent
                          </button>
                          <div className="my-1 border-t border-[#E4E4E7] dark:border-[#262629]" />
                          <div className="flex w-full items-center justify-between rounded-md px-3 py-2">
                            <span className="text-[12.5px] text-[#52525B] dark:text-[#7d7d82]">Active State</span>
                            <Switch
                              checked={isActive}
                              onCheckedChange={() => {
                                toggleAgent(agent.id)
                                setOpenMenuId(null)
                              }}
                              className="scale-[0.75]"
                            />
                          </div>
                        </div>
                      )}
                    </div>
                  </button>
                </div>
              )
            })}

          {/* Visual separator */}
          <div className="mb-2 mt-1 border-b border-[#16161a]" />

          {/* Regular agents */}
          {roomAgents
            .filter((a) => a.id !== 'supervisor')
            .map((agent, index) => {
              const selected = agent.id === selectedId
              const isActive = agentStates[agent.id]
              const menuOpen = openMenuId === agent.id
              return (
                <div key={agent.id} className="relative">
                  {index > 0 && (
                    <div className="border-b border-zinc-200 dark:border-zinc-800" />
                  )}
                  <button
                    type="button"
                    onClick={() => onSelect(agent.id)}
                    aria-pressed={selected}
                    className={`flex w-full items-center gap-3 px-3 py-2.5 text-left transition-all hover:bg-black/[0.04] dark:hover:bg-white/[0.04] ${
                        selected
                          ? 'mx-2 rounded-xl bg-[#1a1a1f]'
                          : ''
                      }`}
                  >
                    <span
                      className="flex size-8 shrink-0 items-center justify-center rounded-md text-[11px] font-semibold"
                      style={{
                        backgroundColor: agent.color,
                        color:
                          agent.color.toLowerCase() === '#fff41f'
                            ? '#111111'
                            : '#ffffff',
                      }}
                      aria-hidden
                    >
                      {agent.initials}
                    </span>
                    <span className="flex min-w-0 flex-1 flex-col leading-tight">
                      <span
                        className={`truncate text-[13px] font-semibold ${
                            selected ? 'text-[#FFF41F]' : 'text-[#d4d4d8]'
                        }`}
                      >
                        {agent.name}
                      </span>
                      <span className={`truncate text-[11px] font-light ${selected ? 'text-white' : 'text-[#7d7d82]'}`}>
                        {isActive ? agent.role : 'Paused'}
                      </span>
                    </span>
                    <div className="flex shrink-0 items-center gap-0.5" onClick={(e) => e.stopPropagation()}>
                      <button
                        type="button"
                        aria-label={`Options for ${agent.name}`}
                        onClick={(e) => {
                          e.stopPropagation()
                          setOpenMenuId(menuOpen ? null : agent.id)
                        }}
                        className="flex size-6 items-center justify-center rounded-md text-[#71717A] transition-colors hover:bg-[#EBEEBEB] dark:text-[#7d7d82] dark:hover:bg-[#1a1a1a]"
                      >
                        <MoreVertical className="size-3.5" strokeWidth={1.5} />
                      </button>
{menuOpen && (
                        <div
                          ref={menuRef}
                          className="absolute right-2 top-8 z-50 w-60 rounded-lg border border-[#E4E4E7] bg-white p-1.5 shadow-lg shadow-black/5 dark:border-[#262629] dark:bg-[#141414] dark:shadow-black/40"
                          onClick={(e) => e.stopPropagation()}
                        >
                          <button
                            type="button"
                            onClick={() => {
                              onSelect(agent.id)
                              onEditAgent?.(agent.id)
                              setOpenMenuId(null)
                            }}
                            className="flex w-full items-center gap-2.5 rounded-md px-3 py-2 text-left text-[12.5px] text-[#52525B] transition-colors hover:bg-[#EBEBEB] hover:text-[#111111] dark:text-[#7d7d82] dark:hover:bg-[#1a1a1a] dark:hover:text-white"
                          >
                            <Pencil className="size-3.5" strokeWidth={1.5} />
                            Edit Agent
                          </button>
                          <div className="my-1 border-t border-[#E4E4E7] dark:border-[#262629]" />
                          <div className="flex w-full items-center justify-between rounded-md px-3 py-2">
                            <span className="text-[12.5px] text-[#52525B] dark:text-[#7d7d82]">Active State</span>
                            <Switch
                              checked={isActive}
                              onCheckedChange={() => {
                                toggleAgent(agent.id)
                                setOpenMenuId(null)
                              }}
                              className="scale-[0.75]"
                            />
                          </div>
                          <div className="my-1 border-t border-[#E4E4E7] dark:border-[#262629]" />
                          <button
                            type="button"
                            onClick={() => {
                              setOpenMenuId(null)
                            }}
                            className="flex w-full items-center gap-2.5 rounded-md px-3 py-2 text-left text-[12.5px] text-[#DC2626] transition-colors hover:bg-[#FEF2F2] dark:text-[#ef4444]/80 dark:hover:bg-red-950/30"
                          >
                            <Trash2 className="size-3.5" strokeWidth={1.5} />
                            Delete Agent
                          </button>
                        </div>
                      )}
                    </div>
                  </button>
                </div>
              )
            })}

          {/* Add New Agent */}
          <div className="mt-2">
            <button
              type="button"
              onClick={() => onSelect('new')}
              className="flex w-full items-center gap-3 rounded-md px-3 py-2.5 text-left transition-all hover:bg-black/[0.04] dark:hover:bg-white/[0.04]"
            >
              <span className="flex size-8 shrink-0 items-center justify-center rounded-md border-2 border-dashed border-[#52525B] text-[#52525B] dark:border-[#7d7d82] dark:text-[#7d7d82]">
                <span className="text-[16px] font-light leading-none">+</span>
              </span>
              <span className="flex min-w-0 flex-1 flex-col leading-tight">
                <span className="truncate text-[13px] font-semibold text-[#d4d4d8]">
                  Add New Agent
                </span>
                <span className="truncate text-[11px] font-light text-[#7d7d82]">
                  Build one from scratch
                </span>
              </span>
            </button>
          </div>
        </div>
      </div>
    </aside>
  )
}
