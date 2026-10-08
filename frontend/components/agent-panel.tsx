'use client'

/**
 * The agent studio: the middle column.
 *
 * Its main job is the building conversation — the user says what they want an
 * agent to do and the builder writes the instructions. The conversation is
 * stateless on the server: the client sends it each time and gets a draft
 * back, and nothing is saved until the user presses Use these instructions.
 * That is deliberate. An agent's instructions decide what it does with the
 * user's money, so they are never written on the user's behalf while they are
 * still reading.
 */

import { useEffect, useMemo, useRef, useState } from 'react'
import { ArrowLeft, Check, Loader2, Send } from 'lucide-react'

import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
} from '@/components/ui/select'
import { agentColor, agentInitials } from '@/lib/agent-appearance'
import type { Agent, BuilderMessage, RoomDetail } from '@/lib/agenlate'
import { agents as agentsApi } from '@/lib/agenlate'
import { ApiError } from '@/lib/api'
import { readKey } from '@/lib/byok'
import { formatUsd } from '@/lib/format'
import { useDraft, useStored } from '@/lib/use-draft'
import {
  DEFAULT_BUILDER_MODEL,
  builderModels,
  labelFor,
  type ModelChoice,
} from '@/lib/models'

const MAX_INSTRUCTIONS = 8000

type Studio =
  | { mode: 'none' }
  | { mode: 'agent'; agentId: string }
  | { mode: 'edit'; agentId: string }
  | { mode: 'new' }

export function AgentPanel({
  studio,
  room,
  onClose,
  onCreate,
  onSeat,
  onAgentChanged,
}: {
  studio: Studio
  room: RoomDetail
  onClose: () => void
  onCreate: (name: string, role: string) => Promise<Agent | null>
  onSeat: (agent: Agent) => void
  onAgentChanged: (agent: Agent) => void
}) {
  const agent =
    'agentId' in studio
      ? room.agents.find((a) => a.id === studio.agentId) ?? null
      : null

  if (studio.mode === 'new') {
    return <NewAgentStudio room={room} onClose={onClose} onCreate={onCreate} onSeat={onSeat} />
  }
  if (!agent) return <EmptyStudio hasAgents={room.agents.length > 0} />
  if (studio.mode === 'edit') {
    return (
      <EditAgent
        key={agent.id}
        agent={agent}
        onClose={onClose}
        onSaved={onAgentChanged}
      />
    )
  }
  return <BuildAgent key={agent.id} agent={agent} onSaved={onAgentChanged} />
}

// -- shell ------------------------------------------------------------------

function PanelShell({ children }: { children: React.ReactNode }) {
  return (
    <aside className="flex h-full min-w-0 flex-1 flex-col bg-panel">{children}</aside>
  )
}

function EmptyStudio({ hasAgents }: { hasAgents: boolean }) {
  return (
    <PanelShell>
      <div className="flex flex-1 flex-col items-center justify-center gap-4 px-6 text-center">
        <div className="flex size-16 items-center justify-center rounded-full border-2 border-dashed border-[#262629] bg-[#0A0A0A]">
          <span className="text-2xl text-[#FFF41F]">+</span>
        </div>
        <div>
          <p className="text-[16px] font-semibold text-white">
            {hasAgents ? 'Pick an agent' : 'Start building your team'}
          </p>
          <p className="mt-1.5 max-w-sm text-[12.5px] font-light leading-relaxed text-[#7d7d82]">
            {hasAgents
              ? 'Choose one from the left to refine what it does.'
              : 'Use “Add New Agent” on the left to put your first worker in this room.'}
          </p>
        </div>
      </div>
    </PanelShell>
  )
}

function ModelSelect({
  value,
  onChange,
  options,
  ariaLabel,
  className,
}: {
  value: string
  onChange: (value: string) => void
  options: ModelChoice[]
  ariaLabel: string
  className?: string
}) {
  return (
    <Select value={value} onValueChange={(next) => next && onChange(next)}>
      <SelectTrigger
        aria-label={ariaLabel}
        className={
          className ??
          'h-12 w-full rounded-lg border border-[#16161a] bg-[#141414] text-[15px] font-medium tracking-tight text-white focus:border-[#FFF41F]/50 focus:ring-0'
        }
      >
        <span className="truncate">{labelFor(options, value)}</span>
      </SelectTrigger>
      <SelectContent className="border-[#16161a] bg-[#141414]">
        {options.map((model) => (
          <SelectItem key={model.value} value={model.value} className="py-2.5 text-[14px]">
            <span className="flex flex-col gap-0.5">
              <span className="font-semibold text-white">{model.label}</span>
              <span className="text-[11px] font-light text-[#7d7d82]">{model.tier}</span>
            </span>
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  )
}

// -- the building conversation ----------------------------------------------

/** One turn as the screen shows it, which is not quite what the API takes. */
type Turn = BuilderMessage & { draft?: string | null }

function BuildAgent({
  agent,
  onSaved,
}: {
  agent: Agent
  onSaved: (agent: Agent) => void
}) {
  // Kept across a reload of this tab. The conversation is not stored on the
  // server — it is rebuilt from what the client sends each time — so if the
  // screen crashed mid-conversation it would otherwise simply be gone.
  const [turns, setTurns] = useStored<Turn[]>(`builder-turns:${agent.id}`, [])
  const [draft, setDraft] = useDraft(`builder:${agent.id}`)
  const [model, setModel] = useState(DEFAULT_BUILDER_MODEL)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [spent, setSpent] = useState(0)
  /** The most recent instructions the builder proposed, pending acceptance. */
  const [proposal, setProposal] = useStored<string | null>(
    `builder-proposal:${agent.id}`,
    null,
  )
  const [saving, setSaving] = useState(false)
  const [justSaved, setJustSaved] = useState(false)

  const feedRef = useRef<HTMLDivElement>(null)
  useEffect(() => {
    feedRef.current?.scrollTo({ top: feedRef.current.scrollHeight })
  }, [turns, busy])

  async function send() {
    const text = draft.trim()
    if (!text || busy) return

    // No key means the turn comes from the account's free allowance; the
    // server says so if there is none left.
    const apiKey = readKey() ?? undefined

    const conversation: BuilderMessage[] = [
      ...turns.map(({ role, content }) => ({ role, content })),
      { role: 'user', content: text },
    ]

    setTurns((prev) => [...prev, { role: 'user', content: text }])
    setDraft('')
    setBusy(true)
    setError(null)
    setJustSaved(false)

    try {
      const reply = await agentsApi.build(agent.id, {
        api_key: apiKey,
        conversation,
        model: apiKey ? model : undefined,
        // Sent explicitly so the builder works from what is on screen rather
        // than what was last saved.
        name: agent.name,
        role: agent.role,
        instructions: agent.system_prompt,
      })
      setTurns((prev) => [
        ...prev,
        { role: 'assistant', content: reply.reply, draft: reply.instructions },
      ])
      if (reply.instructions) setProposal(reply.instructions)
      if (reply.cost_usd !== null && reply.cost_usd !== undefined) {
        setSpent((prev) => prev + reply.cost_usd!)
      }
    } catch (cause) {
      setError(
        cause instanceof ApiError ? cause.message : 'The builder did not reply.',
      )
      // Back into the box, so trying again is one click rather than retyping.
      // Left in the feed it would look sent, with nothing to resend it.
      setTurns((prev) => prev.slice(0, -1))
      setDraft(text)
    } finally {
      setBusy(false)
    }
  }

  async function accept() {
    if (!proposal) return
    setSaving(true)
    setError(null)
    try {
      const updated = await agentsApi.update(agent.id, { system_prompt: proposal })
      onSaved(updated)
      setProposal(null)
      setJustSaved(true)
    } catch (cause) {
      setError(
        cause instanceof ApiError
          ? cause.message
          : 'Could not save these instructions.',
      )
    } finally {
      setSaving(false)
    }
  }

  const color = agentColor(agent.id)

  return (
    <PanelShell>
      <div className="border-b border-[#16161a] px-5 py-4">
        <div className="flex items-center gap-3">
          <span
            className="flex size-9 shrink-0 items-center justify-center rounded-md text-[12px] font-semibold text-[#111111]"
            style={{ backgroundColor: color }}
            aria-hidden
          >
            {agentInitials(agent.name)}
          </span>
          <div className="min-w-0 flex-1 leading-tight">
            <div className="truncate text-[14px] font-semibold text-white">
              {agent.name}
            </div>
            <div className="truncate text-[11px] font-light text-[#7d7d82]">
              {agent.role}
            </div>
          </div>
          {spent > 0 && (
            <span className="shrink-0 rounded-md border border-[#16161a] bg-[#1a1a1a] px-2 py-0.5 font-mono text-[10px] font-light tabular-nums text-[#d4d4d8]">
              {formatUsd(spent)}
            </span>
          )}
        </div>
      </div>

      <div ref={feedRef} className="scrollbar-thin flex-1 space-y-3.5 overflow-y-auto px-5 py-4">
        {turns.length === 0 && (
          <div className="rounded-lg border border-[#16161a] bg-[#141414] px-4 py-3.5">
            <p className="text-[12.5px] font-light leading-relaxed text-[#d4d4d8]">
              Describe what {agent.name} should do and how it should behave. The
              builder will ask about anything it needs and then write the
              instructions — you decide whether to keep them.
            </p>
          </div>
        )}

        {turns.map((turn, index) =>
          turn.role === 'user' ? (
            <div key={index} className="flex justify-end">
              <p className="max-w-[85%] rounded-2xl rounded-br-sm bg-[#2F2F33] px-3.5 py-2.5 text-[12.5px] font-light leading-relaxed text-white">
                {turn.content}
              </p>
            </div>
          ) : (
            <div key={index}>
              <p className="whitespace-pre-wrap px-3.5 py-2.5 text-[12.5px] font-light leading-relaxed text-[#d4d4d8]">
                {turn.content}
              </p>
              {turn.draft && (
                <pre className="mx-3.5 mt-1 max-h-64 overflow-y-auto whitespace-pre-wrap rounded-lg border border-[#16161a] bg-[#0f0f0f] px-3.5 py-3 font-sans text-[12px] font-light leading-relaxed text-[#8e8e93]">
                  {turn.draft}
                </pre>
              )}
            </div>
          ),
        )}

        {busy && (
          <p className="flex items-center gap-2 px-3.5 text-[12px] font-light text-[#7d7d82]">
            <Loader2 className="size-3.5 animate-spin" />
            Thinking…
          </p>
        )}

        {error && (
          <p role="alert" className="px-3.5 text-[12px] font-light text-[#FCA5A5]">
            {error}
          </p>
        )}
      </div>

      {(proposal || justSaved) && (
        <div className="flex items-center justify-between gap-3 border-t border-[#16161a] bg-[#111111] px-5 py-3">
          {justSaved ? (
            <span className="flex items-center gap-2 text-[12px] font-light text-green-500">
              <Check className="size-3.5" />
              Instructions saved.
            </span>
          ) : (
            <>
              <span className="text-[12px] font-light text-[#7d7d82]">
                The builder drafted new instructions.
              </span>
              <button
                type="button"
                onClick={() => void accept()}
                disabled={saving}
                className="inline-flex shrink-0 items-center gap-2 rounded-lg bg-[#FFF41F] px-3.5 py-2 text-[12px] font-semibold text-[#0A0A0A] transition-all hover:brightness-95 disabled:opacity-60"
              >
                {saving && <Loader2 className="size-3.5 animate-spin" />}
                <span>Use these instructions</span>
              </button>
            </>
          )}
        </div>
      )}

      <div className="border-t border-[#16161a]">
        <BuilderInput
          draft={draft}
          setDraft={setDraft}
          model={model}
          setModel={setModel}
          busy={busy}
          onSend={() => void send()}
          instructionsLength={agent.system_prompt.length}
          placeholder={`Tell the builder what ${agent.name} should do…`}
        />
      </div>
    </PanelShell>
  )
}

function BuilderInput({
  draft,
  setDraft,
  model,
  setModel,
  busy,
  onSend,
  instructionsLength,
  placeholder,
}: {
  draft: string
  setDraft: (value: string) => void
  model: string
  setModel: (value: string) => void
  busy: boolean
  onSend: () => void
  instructionsLength: number
  placeholder: string
}) {
  return (
    <div className="relative px-5 pb-3 pt-2">
      <span
        aria-hidden
        className="pointer-events-none absolute right-6 top-0 select-none font-mono text-[11px] font-light tabular-nums text-[#7d7d82]"
      >
        Instructions: {instructionsLength.toLocaleString()} /{' '}
        {MAX_INSTRUCTIONS.toLocaleString()}
      </span>
      <form
        onSubmit={(event) => {
          event.preventDefault()
          onSend()
        }}
        className="mt-3 flex items-center gap-2"
      >
        <input
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          placeholder={placeholder}
          maxLength={4000}
          className="min-w-0 flex-1 rounded-lg border border-[#16161a] bg-[#141414] px-3.5 py-2.5 text-[13px] font-light text-white outline-none transition-colors placeholder:text-zinc-500 focus:border-[#FFF41F]/50"
        />

        <div className="shrink-0">
          <ModelSelect
            value={model}
            onChange={setModel}
            options={builderModels}
            ariaLabel="Builder model"
            className="h-10 w-[145px] rounded-lg border border-[#16161a] bg-[#141414] px-3 text-[12px] font-light text-[#7d7d82] transition-colors hover:text-white focus:border-[#FFF41F]/50 focus:ring-0"
          />
        </div>

        <button
          type="submit"
          aria-label="Send to the builder"
          disabled={busy || !draft.trim()}
          className="flex size-10 shrink-0 items-center justify-center rounded-lg bg-[#FFF41F] text-[#111111] transition-all hover:brightness-95 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {busy ? <Loader2 className="size-4 animate-spin" /> : <Send className="size-4" />}
        </button>
      </form>
    </div>
  )
}

// -- editing an agent directly ----------------------------------------------

const FIELD_CLASS =
  'w-full rounded-lg border border-[#16161a] bg-[#141414] px-3.5 py-2.5 text-[13px] text-white outline-none transition-colors placeholder:text-zinc-500 focus:border-[#FFF41F]/50'

const LABEL_CLASS = 'block text-[10px] font-light uppercase tracking-wider text-white'

function EditAgent({
  agent,
  onClose,
  onSaved,
}: {
  agent: Agent
  onClose: () => void
  onSaved: (agent: Agent) => void
}) {
  const [name, setName] = useState(agent.name)
  const [role, setRole] = useState(agent.role)
  const [instructions, setInstructions] = useState(agent.system_prompt)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const changed =
    name !== agent.name ||
    role !== agent.role ||
    instructions !== agent.system_prompt

  async function save() {
    setSaving(true)
    setError(null)
    try {
      const updated = await agentsApi.update(agent.id, {
        name: name.trim(),
        role: role.trim(),
        system_prompt: instructions.trim(),
      })
      onSaved(updated)
      onClose()
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : 'Could not save the agent.')
      setSaving(false)
    }
  }

  return (
    <PanelShell>
      <div className="flex items-center gap-3 border-b border-[#16161a] px-5 py-4">
        <button
          type="button"
          aria-label="Back to the builder"
          onClick={onClose}
          className="flex size-7 items-center justify-center rounded-md text-[#7d7d82] transition-colors hover:bg-[#1a1a1a] hover:text-white"
        >
          <ArrowLeft className="size-4" strokeWidth={1.5} />
        </button>
        <span className="text-[15px] font-semibold tracking-tight text-white">
          Edit Agent
        </span>
      </div>

      <div className="scrollbar-thin flex flex-1 flex-col gap-6 overflow-y-auto px-5 py-6">
        <div>
          <label className={LABEL_CLASS} htmlFor="agent-name">
            Agent Name
          </label>
          <input
            id="agent-name"
            value={name}
            onChange={(event) => setName(event.target.value)}
            maxLength={100}
            className={`mt-1.5 ${FIELD_CLASS} font-medium`}
          />
        </div>

        <div>
          <label className={LABEL_CLASS} htmlFor="agent-role">
            Role Description
          </label>
          <textarea
            id="agent-role"
            value={role}
            onChange={(event) => setRole(event.target.value)}
            rows={2}
            maxLength={200}
            className={`mt-1.5 ${FIELD_CLASS} resize-none font-light`}
            placeholder="What this agent is responsible for."
          />
        </div>

        <div>
          <label className={LABEL_CLASS} htmlFor="agent-instructions">
            Instructions
          </label>
          <p className="mt-1 text-[11px] font-light leading-relaxed text-[#7d7d82]">
            What the agent is told before every turn. The builder writes these
            for you, but you can edit them directly here.
          </p>
          <textarea
            id="agent-instructions"
            value={instructions}
            onChange={(event) => setInstructions(event.target.value)}
            rows={14}
            maxLength={MAX_INSTRUCTIONS}
            className={`mt-1.5 ${FIELD_CLASS} resize-none font-light leading-relaxed`}
          />
          <span className="mt-1 block text-right font-mono text-[11px] font-light tabular-nums text-[#7d7d82]">
            {instructions.length.toLocaleString()} /{' '}
            {MAX_INSTRUCTIONS.toLocaleString()}
          </span>
        </div>

        {error && (
          <p role="alert" className="text-[12px] font-light text-[#FCA5A5]">
            {error}
          </p>
        )}
      </div>

      <div className="flex items-center justify-center border-t border-[#16161a] px-5 py-4">
        <button
          type="button"
          onClick={() => void save()}
          disabled={saving || !changed || !name.trim() || !role.trim() || !instructions.trim()}
          className="inline-flex items-center gap-2 rounded-lg bg-[#FFF41F] px-5 py-2 text-[13px] font-bold text-black transition-[filter] hover:brightness-90 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {saving && <Loader2 className="size-3.5 animate-spin" />}
          <span>Save</span>
        </button>
      </div>
    </PanelShell>
  )
}

// -- adding an agent --------------------------------------------------------

/**
 * Two ways in: build a new agent, or seat one the user already has.
 *
 * The second matters more than it looks. Agents belong to the user rather than
 * to a room, so the same Researcher can sit in several rooms — and without
 * this, a user would rebuild it each time and end up with four near-identical
 * agents and no idea which is which.
 */
function NewAgentStudio({
  room,
  onClose,
  onCreate,
  onSeat,
}: {
  room: RoomDetail
  onClose: () => void
  onCreate: (name: string, role: string) => Promise<Agent | null>
  onSeat: (agent: Agent) => void
}) {
  const [name, setName] = useState('')
  const [role, setRole] = useState('')
  const [creating, setCreating] = useState(false)
  const [existing, setExisting] = useState<Agent[] | null>(null)

  useEffect(() => {
    let active = true
    agentsApi
      .list()
      .then((all) => active && setExisting(all))
      // A failure here costs the user the shortcut, not the screen. Building
      // a new agent still works.
      .catch(() => active && setExisting([]))
    return () => {
      active = false
    }
  }, [])

  const seated = useMemo(
    () => new Set(room.agents.map((a) => a.id)),
    [room.agents],
  )
  const available = existing?.filter((a) => !seated.has(a.id)) ?? []

  async function create() {
    setCreating(true)
    const agent = await onCreate(name.trim(), role.trim())
    if (!agent) setCreating(false)
  }

  return (
    <PanelShell>
      <div className="flex items-center gap-3 border-b border-[#16161a] px-5 py-4">
        <button
          type="button"
          aria-label="Back to the room"
          onClick={onClose}
          className="flex size-7 items-center justify-center rounded-md text-[#7d7d82] transition-colors hover:bg-[#1a1a1a] hover:text-white"
        >
          <ArrowLeft className="size-4" strokeWidth={1.5} />
        </button>
        <span className="text-[15px] font-semibold tracking-tight text-white">
          Add an Agent
        </span>
      </div>

      <div className="scrollbar-thin flex flex-1 flex-col gap-6 overflow-y-auto px-5 py-6">
        <form
          onSubmit={(event) => {
            event.preventDefault()
            void create()
          }}
          className="flex flex-col gap-5"
        >
          <div>
            <label className={LABEL_CLASS} htmlFor="new-agent-name">
              Agent Name
            </label>
            <input
              id="new-agent-name"
              value={name}
              onChange={(event) => setName(event.target.value)}
              maxLength={100}
              required
              className={`mt-1.5 ${FIELD_CLASS} font-medium`}
              placeholder="e.g. Researcher"
            />
          </div>

          <div>
            <label className={LABEL_CLASS} htmlFor="new-agent-role">
              Role Description
            </label>
            <textarea
              id="new-agent-role"
              value={role}
              onChange={(event) => setRole(event.target.value)}
              rows={2}
              maxLength={200}
              required
              className={`mt-1.5 ${FIELD_CLASS} resize-none font-light`}
              placeholder="Finds and checks sources."
            />
          </div>

          <p className="text-[11.5px] font-light leading-relaxed text-[#7d7d82]">
            You only need a name and a role to start. The builder conversation
            opens next and writes the instructions with you.
          </p>

          <button
            type="submit"
            disabled={creating || !name.trim() || !role.trim()}
            className="inline-flex items-center justify-center gap-2 self-start rounded-lg bg-[#FFF41F] px-5 py-2 text-[13px] font-bold text-black transition-[filter] hover:brightness-90 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {creating && <Loader2 className="size-3.5 animate-spin" />}
            <span>Create and build</span>
          </button>
        </form>

        {available.length > 0 && (
          <div className="border-t border-[#16161a] pt-6">
            <span className={LABEL_CLASS}>Or seat one you already have</span>
            <div className="mt-3 space-y-1">
              {available.map((agent) => (
                <button
                  key={agent.id}
                  type="button"
                  onClick={() => onSeat(agent)}
                  className="flex w-full items-center gap-3 rounded-md px-3 py-2.5 text-left transition-colors hover:bg-white/[0.04]"
                >
                  <span
                    className="flex size-8 shrink-0 items-center justify-center rounded-md text-[11px] font-semibold text-[#111111]"
                    style={{ backgroundColor: agentColor(agent.id) }}
                    aria-hidden
                  >
                    {agentInitials(agent.name)}
                  </span>
                  <span className="flex min-w-0 flex-1 flex-col leading-tight">
                    <span className="truncate text-[13px] font-semibold text-[#d4d4d8]">
                      {agent.name}
                    </span>
                    <span className="truncate text-[11px] font-light text-[#7d7d82]">
                      {agent.role}
                    </span>
                  </span>
                </button>
              ))}
            </div>
          </div>
        )}
      </div>
    </PanelShell>
  )
}
