'use client'

/**
 * One room: its roster on the left, the agent studio in the middle, and the
 * live transcript on the right.
 *
 * The run lives here rather than in the console that displays it. A run is the
 * thing that spends the user's money, so it has to survive the console being
 * collapsed, an agent being selected, or the studio switching into edit mode —
 * all of which unmount parts of this screen. Unmounting the component that
 * held the stream would abandon a run the user is still paying for.
 */

import { useCallback, useEffect, useRef, useState } from 'react'
import Link from 'next/link'
import { useParams, useRouter } from 'next/navigation'

import { AgentPanel } from '@/components/agent-panel'
import { RequireAuth } from '@/components/auth-provider'
import { ChatConsole } from '@/components/chat-console'
import type { RunOutcome } from '@/components/result-dialog'
import { LeftSidebar } from '@/components/left-sidebar'
import { TopNavbar } from '@/components/top-navbar'
import type { Agent, Message, RoomDetail, TrialStatus } from '@/lib/agenlate'
import { agents as agentsApi, rooms as roomsApi, trial as trialApi } from '@/lib/agenlate'
import { ApiError } from '@/lib/api'
import { readKey } from '@/lib/byok'
import { DEFAULT_RUN_MODEL, runModels } from '@/lib/models'
import { runRoom, type RunEvent } from '@/lib/run-stream'

const RUN_MODEL_KEY = 'agenlate.run-model'

/** What the middle column is showing. */
type Studio =
  | { mode: 'none' }
  | { mode: 'agent'; agentId: string }
  | { mode: 'edit'; agentId: string }
  | { mode: 'new' }

export default function RoomPage() {
  return (
    <RequireAuth>
      <Room />
    </RequireAuth>
  )
}

function Room() {
  const params = useParams<{ id: string }>()
  const router = useRouter()
  const roomId = params.id

  const [room, setRoom] = useState<RoomDetail | null>(null)
  const [transcript, setTranscript] = useState<Message[]>([])
  const [loadError, setLoadError] = useState<string | null>(null)
  const [notFound, setNotFound] = useState(false)

  const [studio, setStudio] = useState<Studio>({ mode: 'none' })

  // -- run state ------------------------------------------------------------
  const [running, setRunning] = useState(false)
  /** What the Supervisor is doing right now, for the header line. */
  const [activity, setActivity] = useState<string | null>(null)
  const [runError, setRunError] = useState<string | null>(null)
  const [runCost, setRunCost] = useState(0)

  // Which model runs the room. Remembered in this browser, because it is a
  // preference rather than part of the room: the same person usually wants the
  // same trade between speed, quality and cost from one room to the next.
  const [runModel, setRunModel] = useState(DEFAULT_RUN_MODEL)
  useEffect(() => {
    try {
      const saved = window.localStorage.getItem(RUN_MODEL_KEY)
      // Only a model still on offer: a stored id that has since been removed
      // from the list would fail every run with nothing on screen to explain it.
      if (saved && runModels.some((m) => m.value === saved)) setRunModel(saved)
    } catch {
      // Storage blocked: the default is used.
    }
  }, [])

  function chooseRunModel(value: string) {
    setRunModel(value)
    try {
      window.localStorage.setItem(RUN_MODEL_KEY, value)
    } catch {
      // As above.
    }
  }
  /**
   * The Supervisor's question, when the last run stopped to ask one. Not an
   * error: the run did what it should, and the next step is the user's.
   */
  const [awaiting, setAwaiting] = useState<string | null>(null)
  /** How the last run this browser watched ended; drives the result prompt. */
  const [outcome, setOutcome] = useState<RunOutcome>(null)
  const abortRef = useRef<AbortController | null>(null)

  // Without a key of their own, a new account runs on its free allowance.
  // Storage is read after mount: the server renders this first and has none.
  const [hasKey, setHasKey] = useState(true)
  const [trial, setTrial] = useState<TrialStatus | null>(null)
  const refreshTrial = useCallback(async () => {
    try {
      setTrial(await trialApi.status())
    } catch {
      // Not worth an error on screen: the run itself says so if it is refused.
    }
  }, [])
  useEffect(() => {
    const stored = Boolean(readKey())
    setHasKey(stored)
    if (!stored) void refreshTrial()
  }, [refreshTrial])

  const load = useCallback(async () => {
    setLoadError(null)
    try {
      const [detail, page] = await Promise.all([
        roomsApi.get(roomId),
        roomsApi.messages(roomId, { limit: 200 }),
      ])
      setRoom(detail)
      setTranscript(page.items)
      setStudio((current) =>
        current.mode === 'none' && detail.agents.length > 0
          ? { mode: 'agent', agentId: detail.agents[0].id }
          : current,
      )
    } catch (cause) {
      if (cause instanceof ApiError && cause.status === 404) {
        setNotFound(true)
        return
      }
      setLoadError(
        cause instanceof ApiError ? cause.message : 'Could not load this room.',
      )
    }
  }, [roomId])

  useEffect(() => {
    void load()
  }, [load])

  // A run left in flight when the user navigates away is a run nobody is
  // watching and everybody is paying for. Closing the connection stops it.
  useEffect(() => () => abortRef.current?.abort(), [])

  /** Why a run cannot start right now, or null if it can. */
  function blockedReason(): string | null {
    if (!room || room.agents.length === 0) return 'Seat at least one agent before starting a run.'
    // Only when we know there is nothing to run on. While the free allowance
    // is still loading the request is sent anyway, and the server decides.
    if (!readKey() && trial) {
      if (!trial.enabled) return 'Add your OpenRouter key before starting a run.'
      if (trial.runs_remaining <= 0) {
        return 'You have used your free runs. Add your OpenRouter key to keep going.'
      }
    }
    return null
  }

  /**
   * Sends what the user typed, then runs the room so the team acts on it.
   *
   * Checked before posting rather than after: saving a message and then
   * failing to run would leave the user wondering whether anything happened.
   * With nothing typed this simply starts or continues the run.
   */
  async function sendAndRun(content: string) {
    const blocked = blockedReason()
    if (blocked) {
      setRunError(blocked)
      return
    }
    if (content.trim()) {
      try {
        const message = await roomsApi.postMessage(roomId, content.trim())
        setTranscript((prev) => [...prev, message])
      } catch (cause) {
        setRunError(
          cause instanceof ApiError ? cause.message : 'Could not send your message.',
        )
        return
      }
    }
    await start()
  }

  /**
   * Reads the transcript back from the server after a run was cut off.
   *
   * Messages are saved before they are streamed, so the server can hold work
   * this screen never received. Best effort: if this fails too, what is on
   * screen stays as it was.
   */
  async function recoverTranscript() {
    try {
      const page = await roomsApi.messages(roomId, { limit: 200 })
      setTranscript(page.items)
    } catch {
      // Nothing more to do here; the error shown for the run still stands.
    }
  }

  async function start() {
    // No key means a free run, on the one model free runs use.
    const apiKey = readKey() ?? undefined
    const blocked = blockedReason()
    if (blocked) {
      setRunError(blocked)
      return
    }

    const controller = new AbortController()
    abortRef.current = controller
    setRunning(true)
    setRunError(null)
    setAwaiting(null)
    setOutcome(null)
    setRunCost(0)
    setActivity('Supervisor is deciding what happens next…')

    try {
      let counted = false
      let finished = false
      for await (const event of runRoom({
        roomId,
        apiKey,
        model: apiKey ? runModel : undefined,
        signal: controller.signal,
      })) {
        if (!apiKey && !counted) {
          // The first event means the server accepted the run and took one
          // free run for it. Shown straight away; the count is read back from
          // the server when the run ends, which also picks up a refund.
          counted = true
          setTrial((prev) =>
            prev ? { ...prev, runs_remaining: Math.max(0, prev.runs_remaining - 1) } : prev,
          )
        }
        if (event.type === 'run_finished') finished = true
        apply(event)
      }
      if (!finished && !controller.signal.aborted) {
        // The stream closed without saying how the run ended: a dropped
        // connection, or the server restarting underneath it. Left alone the
        // screen just goes quiet, which reads as a run that did nothing.
        await recoverTranscript()
        setRunError(
          'The connection was lost before the run finished. Anything already written is saved — run it again to carry on from there.',
        )
      }
    } catch (cause) {
      if (!controller.signal.aborted) await recoverTranscript()
      setRunError(
        cause instanceof ApiError ? cause.message : 'The run stopped unexpectedly.',
      )
    } finally {
      setRunning(false)
      setActivity(null)
      abortRef.current = null
      if (!apiKey) void refreshTrial()
    }
  }

  /**
   * Folds one streamed event into what the screen shows.
   *
   * Messages are appended as they arrive rather than re-fetched, so the
   * transcript fills in live. They carry a `seq` from the database, so
   * appending cannot reorder anything.
   */
  function apply(event: RunEvent) {
    switch (event.type) {
      case 'supervisor_decision':
        setTranscript((prev) => [...prev, event.message])
        setActivity(
          event.action === 'dispatch'
            ? 'Supervisor is handing off the turn…'
            : 'Supervisor is wrapping up…',
        )
        break
      case 'agent_started':
        setActivity(`${event.agent_name} is working…`)
        break
      case 'agent_message':
        setTranscript((prev) => [...prev, event.message])
        setActivity('Supervisor is deciding what happens next…')
        break
      case 'usage':
        // Null when the provider did not price the call. Leaving the running
        // total where it is understates it, which is better than guessing.
        if (event.total.cost_usd !== null) setRunCost(event.total.cost_usd)
        break
      case 'run_finished':
        setActivity(null)
        if (event.reason === 'awaiting_user') {
          // The question itself is already in the transcript as the
          // Supervisor's last message; this puts it next to the reply box.
          setAwaiting(event.final_message ?? event.explanation)
          setOutcome('awaiting')
        } else if (event.succeeded) {
          setOutcome('completed')
        } else {
          setRunError(event.detail ?? event.explanation)
        }
        break
    }
  }

  function stop() {
    abortRef.current?.abort()
  }

  // -- roster and agents ----------------------------------------------------

  async function toggleRoomStatus(active: boolean) {
    if (!room) return
    const next = active ? 'active' : 'paused'
    const previous = room.status
    setRoom({ ...room, status: next })
    try {
      await roomsApi.setStatus(room.id, next)
    } catch (cause) {
      setRoom({ ...room, status: previous })
      setRunError(
        cause instanceof ApiError ? cause.message : 'Could not change the room.',
      )
    }
  }

  async function unseat(agentId: string) {
    if (!room) return
    const previous = room.agents
    setRoom({ ...room, agents: room.agents.filter((a) => a.id !== agentId) })
    setStudio((current) =>
      'agentId' in current && current.agentId === agentId ? { mode: 'none' } : current,
    )
    try {
      await roomsApi.removeAgent(room.id, agentId)
    } catch (cause) {
      setRoom({ ...room, agents: previous })
      setRunError(
        cause instanceof ApiError
          ? cause.message
          : 'Could not remove the agent from this room.',
      )
    }
  }

  /** Creates an agent and seats it here, then opens it for building. */
  async function createAgent(name: string, role: string): Promise<Agent | null> {
    if (!room) return null
    try {
      const agent = await agentsApi.create({
        name,
        role,
        // A placeholder, because instructions are required and the builder
        // conversation is how they actually get written. The user sees this
        // only if they never talk to the builder at all.
        system_prompt: `You are ${name}. Your role: ${role}.`,
      })
      await roomsApi.addAgent(room.id, agent.id)
      setRoom((prev) => (prev ? { ...prev, agents: [...prev.agents, agent] } : prev))
      setStudio({ mode: 'agent', agentId: agent.id })
      return agent
    } catch (cause) {
      setRunError(
        cause instanceof ApiError ? cause.message : 'Could not create the agent.',
      )
      return null
    }
  }

  async function seatExisting(agent: Agent) {
    if (!room || room.agents.some((a) => a.id === agent.id)) return
    setRoom({ ...room, agents: [...room.agents, agent] })
    setStudio({ mode: 'agent', agentId: agent.id })
    try {
      await roomsApi.addAgent(room.id, agent.id)
    } catch (cause) {
      setRoom({ ...room, agents: room.agents })
      setRunError(
        cause instanceof ApiError ? cause.message : 'Could not seat the agent.',
      )
    }
  }

  /** Replaces one agent wherever this screen holds a copy of it. */
  function replaceAgent(updated: Agent) {
    setRoom((prev) =>
      prev
        ? { ...prev, agents: prev.agents.map((a) => (a.id === updated.id ? updated : a)) }
        : prev,
    )
  }

  async function deleteRoom() {
    if (!room) return
    try {
      await roomsApi.remove(room.id)
      router.replace('/lobby')
    } catch (cause) {
      setRunError(
        cause instanceof ApiError ? cause.message : 'Could not delete the room.',
      )
    }
  }

  // -- render ---------------------------------------------------------------

  if (notFound) {
    return (
      <Centered>
        <p className="text-[15px] font-semibold text-white">Room not found</p>
        <p className="mt-1.5 text-[13px] font-light text-[#7d7d82]">
          It may have been deleted, or it belongs to someone else.
        </p>
        <Link
          href="/lobby"
          className="mt-4 text-[13px] font-medium text-[#FFF41F] transition-opacity hover:opacity-80"
        >
          Back to the lobby
        </Link>
      </Centered>
    )
  }

  if (loadError) {
    return (
      <Centered>
        <p role="alert" className="text-[13px] font-light text-[#FCA5A5]">
          {loadError}
        </p>
        <button
          type="button"
          onClick={() => void load()}
          className="mt-4 text-[13px] font-medium text-[#FFF41F] transition-opacity hover:opacity-80"
        >
          Try again
        </button>
      </Centered>
    )
  }

  if (!room) {
    return (
      <Centered>
        <span className="text-[13px] font-light text-[#7d7d82]">Loading room…</span>
      </Centered>
    )
  }

  const selectedId = 'agentId' in studio ? studio.agentId : null

  return (
    <div className="flex h-screen max-h-screen w-full flex-col overflow-hidden bg-[#0a0a0a] text-foreground">
      <TopNavbar />

      <div className="flex min-h-0 flex-1 pt-[56px]">
        <div className="hidden md:flex">
          <LeftSidebar
            room={room}
            selectedId={selectedId}
            runCost={runCost}
            onSelect={(id) => setStudio({ mode: 'agent', agentId: id })}
            onEditAgent={(id) => setStudio({ mode: 'edit', agentId: id })}
            onAddAgent={() => setStudio({ mode: 'new' })}
            onUnseat={(id) => void unseat(id)}
            onStatusChange={(active) => void toggleRoomStatus(active)}
            onDeleteRoom={() => void deleteRoom()}
          />
        </div>

        <div className="flex min-w-0 flex-1">
          <AgentPanel
            studio={studio}
            room={room}
            onClose={() =>
              setStudio(
                studio.mode === 'edit'
                  ? { mode: 'agent', agentId: studio.agentId }
                  : { mode: 'none' },
              )
            }
            onCreate={createAgent}
            onSeat={seatExisting}
            onAgentChanged={replaceAgent}
          />
        </div>

        {studio.mode !== 'edit' && studio.mode !== 'new' && (
          <div className="hidden lg:flex">
            <ChatConsole
              room={room}
              transcript={transcript}
              running={running}
              activity={activity}
              error={runError}
              cost={runCost}
              awaiting={awaiting}
              outcome={outcome}
              model={runModel}
              freeRuns={
                !hasKey && trial?.enabled
                  ? {
                      remaining: trial.runs_remaining,
                      total: trial.runs_total,
                      model: trial.model ?? DEFAULT_RUN_MODEL,
                    }
                  : null
              }
              onModelChange={chooseRunModel}
              onSend={(content) => sendAndRun(content)}
              onStop={stop}
              onDismissError={() => setRunError(null)}
            />
          </div>
        )}
      </div>
    </div>
  )
}

function Centered({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex h-screen flex-col items-center justify-center bg-[#0a0a0a] px-6 text-center">
      {children}
    </div>
  )
}
