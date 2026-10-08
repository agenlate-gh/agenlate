/**
 * The backend, as the interface sees it.
 *
 * Types come from `api-types.ts`, which is generated from the backend's own
 * OpenAPI schema (`pnpm gen:types`). They are aliased here because the raw
 * generated shapes read as
 * `components['schemas']['AgentOut']`, which is accurate and unusable.
 *
 * The point of generating them is that this file cannot drift from the API. If
 * the backend renames a field, this stops compiling — which is the whole
 * reason type errors now fail the build.
 */

import { api } from './api'
import type { components } from './api-types'

type Schemas = components['schemas']

export type Agent = Schemas['AgentOut']
export type AgentInput = Schemas['AgentIn']
export type AgentPatch = Schemas['AgentPatch']
export type Room = Schemas['RoomOut']
export type RoomDetail = Schemas['RoomDetailOut']
export type RoomInput = Schemas['RoomIn']
export type RoomPatch = Schemas['RoomPatch']
export type RoomStatus = Schemas['RoomStatus']
export type RoomUsage = Schemas['RoomUsage']
export type Message = Schemas['MessageOut']
export type MessagePage = Schemas['MessagePage']
export type Emitter = Schemas['Emitter']
export type KeyCheck = Schemas['KeyCheckResponse']
export type UsageSummary = Schemas['UsageSummary']
export type DailyUsage = Schemas['DailyUsage']
export type UsageEvent = Schemas['UsageEventOut']
export type BuilderResponse = Schemas['BuilderResponse']
export type BuilderMessage = Schemas['BuilderMessage']
export type ObjectiveResponse = Schemas['ObjectiveResponse']
export type SignupRequest = Schemas['SignupRequest']
export type TrialStatus = Schemas['TrialStatus']

// -- agents -----------------------------------------------------------------

export const agents = {
  list: () => api.get<Agent[]>('/api/agents'),
  get: (id: string) => api.get<Agent>(`/api/agents/${id}`),
  create: (input: AgentInput) => api.post<Agent>('/api/agents', input),
  update: (id: string, patch: AgentPatch) =>
    api.patch<Agent>(`/api/agents/${id}`, patch),
  remove: (id: string) => api.delete<void>(`/api/agents/${id}`),

  /**
   * One turn of the conversation that writes an agent's instructions.
   *
   * Returns a draft. Nothing is saved until the user accepts it and this
   * calls `update` — so what becomes an agent's instructions is always
   * something a person chose.
   */
  build: (
    id: string,
    body: {
      /** Left out, the turn comes from the account's free allowance. */
      api_key?: string
      conversation: BuilderMessage[]
      name?: string | null
      role?: string | null
      instructions?: string | null
      model?: string
    },
  ) => api.post<BuilderResponse>(`/api/agents/${id}/builder`, body),
}

// -- rooms ------------------------------------------------------------------

export const rooms = {
  /** Newest first, each with its roster — the lobby draws both. */
  list: () => api.get<RoomDetail[]>('/api/rooms'),
  get: (id: string) => api.get<RoomDetail>(`/api/rooms/${id}`),
  create: (input: RoomInput) => api.post<RoomDetail>('/api/rooms', input),
  update: (id: string, patch: RoomPatch) =>
    api.patch<Room>(`/api/rooms/${id}`, patch),
  remove: (id: string) => api.delete<void>(`/api/rooms/${id}`),

  /**
   * Pausing is not deleting. A paused room keeps its roster and its
   * transcript; the API just refuses to start a run on it.
   */
  setStatus: (id: string, status: RoomStatus) =>
    api.patch<Room>(`/api/rooms/${id}`, { status }),

  addAgent: (roomId: string, agentId: string) =>
    api.put<void>(`/api/rooms/${roomId}/agents/${agentId}`),
  removeAgent: (roomId: string, agentId: string) =>
    api.delete<void>(`/api/rooms/${roomId}/agents/${agentId}`),

  /**
   * A page of transcript, ordered. Paged by `seq` rather than an offset,
   * because a transcript grows while it is being read.
   */
  /**
   * Adds the user's own words to the transcript — an answer to the
   * Supervisor, or new direction. Does not start a run; the caller does that.
   */
  postMessage: (roomId: string, content: string) =>
    api.post<Message>(`/api/rooms/${roomId}/messages`, { content }),

  /**
   * One turn of the conversation that writes a room's objective. Returns a
   * draft for the form; nothing is saved. Runs before the room exists, so it
   * takes the form's current values rather than a room id.
   */
  draftObjective: (body: {
    /** Left out, the turn comes from the account's free allowance. */
    api_key?: string
    conversation: BuilderMessage[]
    name?: string | null
    objective?: string | null
    model?: string
  }) => api.post<ObjectiveResponse>('/api/rooms/objective-draft', body),

  messages: (roomId: string, options: { afterSeq?: number; limit?: number } = {}) => {
    const query = new URLSearchParams()
    if (options.afterSeq !== undefined) query.set('after_seq', String(options.afterSeq))
    if (options.limit !== undefined) query.set('limit', String(options.limit))
    const suffix = query.toString() ? `?${query}` : ''
    return api.get<MessagePage>(`/api/rooms/${roomId}/messages${suffix}`)
  },
}

// -- accounts ---------------------------------------------------------------

export const accounts = {
  /**
   * Creates an account with an invite code. The only way in during the Beta:
   * public signup is off, so the code is checked and spent on the server.
   * The account comes back confirmed; the caller signs in with it next.
   */
  signUp: (body: SignupRequest) => api.postAnonymous<unknown>('/api/signup', body),

  /**
   * Adds an email to the Beta waitlist from the public landing page. The
   * answer is the same whether or not the address was already on it.
   * `website` is the hidden trap field; people never fill it in.
   */
  joinWaitlist: (body: { email: string; source?: string; website?: string }) =>
    api.postAnonymous<{ message: string }>('/api/waitlist', body),
}

// -- keys and usage ---------------------------------------------------------

export const keys = {
  /** Asks OpenRouter whether the key works. Runs no inference, so it is free. */
  validate: (apiKey: string) =>
    api.post<KeyCheck>('/api/keys/validate', { api_key: apiKey }),
}

export const trial = {
  /**
   * How many free runs this account has left. A new account gets a few runs
   * on Agenlate's key, so it can see a room work before adding its own.
   */
  status: () => api.get<TrialStatus>('/api/trial'),
}

export const usage = {
  summary: (days = 30) => api.get<UsageSummary>(`/api/usage/summary?days=${days}`),

  /**
   * Per-room spending, for the lobby cards. One request for every room
   * rather than one per room. Rooms that have never run are absent, so a
   * caller reads a missing room as nothing spent.
   */
  byRoom: (days = 30) => api.get<RoomUsage[]>(`/api/usage/rooms?days=${days}`),

  /** One point per day, oldest first, with quiet days included as zero. */
  daily: (days = 30) => api.get<DailyUsage[]>(`/api/usage/daily?days=${days}`),

  /** Individual provider calls, newest first — the audit log. */
  events: (days = 30, limit = 100) =>
    api.get<UsageEvent[]>(`/api/usage/events?days=${days}&limit=${limit}`),
}
