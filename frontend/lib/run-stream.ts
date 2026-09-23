/**
 * Starting a run and reading it as it happens.
 *
 * Not EventSource. That API can only issue a GET, cannot set an Authorization
 * header, and cannot carry a body — and a run needs all three, because it is
 * authenticated and the user's provider key travels in the request. So this is
 * `fetch` with a streamed body, parsed as server-sent events by hand.
 *
 * The frame types below are the one place in this codebase that restates the
 * backend's shapes rather than generating them. The run endpoint returns a
 * stream, so its events do not appear in the OpenAPI schema and cannot be
 * generated from it. They mirror `to_payload` in `backend/src/agenlate/api/
 * sse.py`; changing one means changing the other.
 */

import { api, ApiError, type ApiErrorCode } from './api'
import type { Message } from './agenlate'

// -- what the server sends --------------------------------------------------

/**
 * What the Supervisor may decide. A closed set on the server, so a closed set
 * here: `await_user` means it is blocked and has handed control back, which
 * the interface has to treat differently from finishing.
 */
export type SupervisorAction = 'dispatch' | 'complete' | 'await_user'

export type ObjectiveStatus = 'in_progress' | 'achieved' | 'blocked'

/** The Supervisor chose what happens next, and why. */
export type SupervisorDecisionEvent = {
  type: 'supervisor_decision'
  reasoning: string
  action: SupervisorAction
  objective_status: ObjectiveStatus
  agent_id: string | null
  instruction: string | null
  /** Present when the run ends — what to show the user. */
  message_to_user: string | null
  /** How many attempts the decision took to come back well-formed. */
  attempts: number
  message: Message
}

/**
 * How a run ended. Mirrors `TerminationReason` in
 * `backend/src/agenlate/supervisor/limits.py`.
 */
export type TerminationReason =
  | 'completed'
  | 'completed_empty'
  | 'awaiting_user'
  | 'max_turns'
  | 'spend_cap'
  | 'stalled'
  | 'no_progress'
  | 'unpriced_ceiling'
  | 'provider_failure'
  | 'key_rejected'
  | 'out_of_credit'
  | 'rate_limited'
  | 'supervisor_failure'
  | 'cancelled'

/** An agent has been handed the turn and is working. */
export type AgentStartedEvent = {
  type: 'agent_started'
  agent_id: string
  agent_name: string
  instruction: string
}

export type AgentMessageEvent = {
  type: 'agent_message'
  agent_id: string
  message: Message
}

/** Emitted after every paid call, so spending can be shown as it accrues. */
export type UsageEvent = {
  type: 'usage'
  call: {
    prompt_tokens: number
    completion_tokens: number
    cost_usd: number | null
  }
  total: {
    calls: number
    prompt_tokens: number
    completion_tokens: number
    cost_usd: number | null
    unpriced_calls: number
    has_unknown_cost: boolean
  }
}

export type RunFinishedEvent = {
  type: 'run_finished'
  reason: TerminationReason
  /** The reason in a sentence a user can read. */
  explanation: string
  succeeded: boolean
  turns: number
  messages_added: number
  final_message: string | null
  detail: string | null
  usage: {
    calls: number
    prompt_tokens: number
    completion_tokens: number
    cost_usd: number | null
    unpriced_calls: number
  }
}

export type RunEvent =
  | SupervisorDecisionEvent
  | AgentStartedEvent
  | AgentMessageEvent
  | UsageEvent
  | RunFinishedEvent

export type RunOptions = {
  roomId: string
  apiKey: string
  model?: string
  maxTurns?: number
  spendCapUsd?: number
  /** Aborting this stops the run: the backend cancels when the client leaves. */
  signal?: AbortSignal
}

// -- parsing ----------------------------------------------------------------

/**
 * Splits an SSE byte stream into events.
 *
 * A chunk boundary can fall anywhere, including inside a multi-byte character
 * or halfway through a frame, so bytes are decoded with `stream: true` and the
 * remainder is carried across chunks. Lines beginning with a colon are
 * comments — the heartbeats that keep proxies from dropping a quiet run — and
 * are skipped.
 */
async function* parseEvents(
  body: ReadableStream<Uint8Array>,
): AsyncGenerator<RunEvent> {
  const reader = body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  try {
    while (true) {
      const { done, value } = await reader.read()
      if (done) break

      buffer += decoder.decode(value, { stream: true })

      let boundary = buffer.indexOf('\n\n')
      while (boundary !== -1) {
        const frame = buffer.slice(0, boundary)
        buffer = buffer.slice(boundary + 2)
        const parsed = parseFrame(frame)
        if (parsed) yield parsed
        boundary = buffer.indexOf('\n\n')
      }
    }
  } finally {
    // Releases the connection. Without this an abandoned run holds a socket
    // open until the browser decides otherwise.
    reader.releaseLock()
  }
}

function parseFrame(frame: string): RunEvent | null {
  let eventType: string | null = null
  const data: string[] = []

  for (const line of frame.split('\n')) {
    if (line.startsWith(':')) continue // heartbeat
    if (line.startsWith('event:')) eventType = line.slice(6).trim()
    else if (line.startsWith('data:')) data.push(line.slice(5).trim())
  }

  if (!eventType || data.length === 0) return null

  try {
    return { type: eventType, ...JSON.parse(data.join('\n')) } as RunEvent
  } catch {
    // A frame we cannot parse is not worth killing a run over. Dropping one
    // event loses a line of transcript; throwing loses the rest of the run,
    // which the user is paying for.
    return null
  }
}

// -- the call ---------------------------------------------------------------

/**
 * Runs a room, yielding events until it finishes.
 *
 * Throws before yielding anything if the request itself is refused — a paused
 * room, a rejected key, a rate limit — so a caller can tell "this did not
 * start" from "this started and then went wrong".
 */
export async function* runRoom(options: RunOptions): AsyncGenerator<RunEvent> {
  const body = {
    api_key: options.apiKey,
    ...(options.model ? { model: options.model } : {}),
    ...(options.maxTurns ? { max_turns: options.maxTurns } : {}),
    ...(options.spendCapUsd ? { spend_cap_usd: options.spendCapUsd } : {}),
  }

  let response: Response
  try {
    response = await fetch(`${api.baseUrl}/api/rooms/${options.roomId}/run`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Accept: 'text/event-stream',
        ...(await api.authHeaders()),
      },
      body: JSON.stringify(body),
      signal: options.signal,
    })
  } catch (cause) {
    // An abort is the user's own doing, not a failure to report as one.
    if (cause instanceof DOMException && cause.name === 'AbortError') return
    throw new ApiError(
      'Could not reach the server. It may be waking up — try again in a moment.',
      'network',
      0,
    )
  }

  if (!response.ok) throw await toApiError(response)
  if (!response.body) {
    throw new ApiError('The server sent no run stream.', 'internal_error', 500)
  }

  try {
    yield* parseEvents(response.body)
  } catch (cause) {
    if (cause instanceof DOMException && cause.name === 'AbortError') return
    throw cause
  }
}

/**
 * Turns a refused run into the same error shape the rest of the client uses.
 *
 * Duplicated from `api.ts` rather than exported from it because this path
 * cannot go through `request()`: that helper reads the whole body as JSON,
 * which for a successful run would mean waiting for it to finish before
 * showing anything.
 */
async function toApiError(response: Response): Promise<ApiError> {
  const requestId = response.headers.get('X-Request-ID')
  try {
    const body = await response.json()
    return new ApiError(
      body?.error?.message ?? 'The run could not be started.',
      (body?.error?.code as ApiErrorCode) ?? 'internal_error',
      response.status,
      requestId,
    )
  } catch {
    return new ApiError(
      `The server returned ${response.status}.`,
      'internal_error',
      response.status,
      requestId,
    )
  }
}
