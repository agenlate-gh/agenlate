'use client'

import { AgentPanel } from '@/components/agent-panel'
import { ChatConsole } from '@/components/chat-console'
import { LeftSidebar } from '@/components/left-sidebar'
import { TopNavbar } from '@/components/top-navbar'
import { agents, blankTemplateAgents } from '@/lib/agenlate-data'
import type { Agent } from '@/lib/agenlate-data'
import { useSearchParams } from 'next/navigation'
import { Suspense, useState } from 'react'

// ─── Force dynamic rendering ────────────────────────────────────────────────
// Prevents Next.js from attempting to statically pre-render this page, which
// would fail because useSearchParams() is only available at runtime.
export const dynamic = 'force-dynamic'

// ─── Inner component that uses search params ────────────────────────────────
function PageContent() {
  const searchParams = useSearchParams()
  const isBlankTemplate = searchParams.get('template') === 'blank'

  const initialAgents = isBlankTemplate ? blankTemplateAgents : agents
  const [selectedId, setSelectedId] = useState<string>(initialAgents[0].id)
  const [editingId, setEditingId] = useState<string | null>(null)
  const [agentList, setAgentList] = useState<Agent[]>(initialAgents)
  const [masterActive, setMasterActive] = useState(!isBlankTemplate)
  const [sheetOpen, setSheetOpen] = useState(false)
  const roomCost = isBlankTemplate ? '$0.00' : '$4.271'
  const roomName = 'Production Deployment Analyzer'

  const isInEditorMode = editingId !== null || selectedId === 'new'

  function handleSelect(id: string) {
    setSelectedId(id)
    setEditingId(null)
  }

  function handleEditAgent(id: string) {
    setSelectedId(id)
    setEditingId(id)
  }

  /** Exit editor/creator and return to operational chat view */
  function handleBackFromEditor() {
    setEditingId(null)
    if (selectedId === 'new') {
      setSelectedId(agentList[0].id)
    }
  }

  /** Update an agent's color in the global list — propagates instantly to sidebar avatars */
  function handleAgentColorChange(agentId: string, newColor: string) {
    setAgentList((prev) =>
      prev.map((a) => (a.id === agentId ? { ...a, color: newColor } : a)),
    )
  }

  let _idCounter = initialAgents.length + 1
  /** Deploy a brand-new agent into the room list */
  function handleDeploy(name: string, role: string) {
    const newAgent: Agent = {
      id: `agent-${_idCounter++}`,
      name,
      role,
      color: '#34D399',
      initials: name
        .split(/\s+/)
        .map((w) => w[0])
        .join('')
        .toUpperCase()
        .slice(0, 2),
      model: 'claude-3.7-sonnet',
    }
    setAgentList((prev) => [...prev, newAgent])
    setSelectedId(newAgent.id)
    setEditingId(null)
  }

  /** Persist name / role edits for the currently-edited agent */
  function handleSave(agentId: string, name: string, role: string) {
    setAgentList((prev) =>
      prev.map((a) =>
        a.id === agentId ? { ...a, name, role } : a,
      ),
    )
    setEditingId(null)
  }

  return (
    <div className="flex h-screen max-h-screen w-full flex-col overflow-hidden bg-[#0a0a0a] text-foreground">
      {/* Fixed Top Navbar — OpenRouter style */}
      <TopNavbar />

      {/* Three-column layout below navbar */}
      <div className="flex min-h-0 flex-1 pt-[56px]">
        {/* LEFT COLUMN: Room members */}
        <div className="hidden md:flex">
          <LeftSidebar
              selectedId={selectedId}
              onSelect={handleSelect}
              onEditAgent={handleEditAgent}
              agents={agentList}
              roomName={roomName}
              roomCost={roomCost}
              masterActive={masterActive}
              onMasterToggle={setMasterActive}
              onDeleteRoom={() => console.log('Delete room')}
            />
        </div>

        {/* CENTER COLUMN: Vibe Coding Studio — Agent Builder */}
        <div className="flex min-w-0 flex-1">
          <AgentPanel
            selection={selectedId}
            editingId={editingId}
            agents={agentList}
            onClose={handleBackFromEditor}
            onColorChange={handleAgentColorChange}
            onDeploy={handleDeploy}
            onSave={handleSave}
          />
        </div>

        {/* RIGHT COLUMN: Live Agent Streaming Feed — hidden during edit/create */}
        {!isInEditorMode && (
          <div className="hidden lg:flex">
            <ChatConsole empty={isBlankTemplate} />
          </div>
        )}
      </div>

      {/* Mobile / tablet sliding sheet for agent studio */}
      {sheetOpen && (
        <div className="fixed inset-0 z-50 lg:hidden">
          <div
            className="absolute inset-0 bg-black/30 dark:bg-black/60"
            onClick={() => setSheetOpen(false)}
            aria-hidden
          />
          <div className="absolute right-0 top-0 h-full">
            <AgentPanel selection={selectedId} editingId={editingId} onClose={() => setSheetOpen(false)} />
          </div>
        </div>
      )}
    </div>
  )
}

// ─── Exported page wrapped in Suspense ──────────────────────────────────────
// The Suspense boundary is required by Next.js App Router whenever a
// component uses useSearchParams(). It lets the page stream in dynamically
// without blocking the entire route from rendering.
export default function Page() {
  return (
    <Suspense fallback={<div className="flex h-svh items-center justify-center bg-[#0a0a0a] text-[13px] text-[#52525B] dark:text-[#7d7d82]">Loading workspace…</div>}>
      <PageContent />
    </Suspense>
  )
}
